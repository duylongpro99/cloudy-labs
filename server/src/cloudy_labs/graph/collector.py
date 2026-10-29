"""Read the EC2 state Floci holds into a ResourceGraph.

`build_graph` is pure: it takes the raw `describe_*` responses, so tests feed it
fixtures without Docker. `collect` does the calls, straight to Floci (not through
api-tap, so collecting never shows up as learner activity).
"""

import ipaddress
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError

from ..config import REGION
from ..providers.aws import AwsProvider
from .host_ports import host_ports as docker_host_ports
from .schema import Contains, Edge, Node, ResourceGraph

# Response key of each describe call, in the order build_graph reads them.
DESCRIBE = {
    "describe_vpcs": "Vpcs",
    "describe_subnets": "Subnets",
    "describe_internet_gateways": "InternetGateways",
    "describe_nat_gateways": "NatGateways",
    "describe_route_tables": "RouteTables",
    "describe_security_groups": "SecurityGroups",
    "describe_key_pairs": "KeyPairs",
    "describe_instances": "Reservations",
    "describe_addresses": "Addresses",
}
LOOPBACK_PUBLIC_IP = "127.0.0.1"  # what Floci reports on Docker Desktop; the host ports are what works
USER_DATA_WINDOW = timedelta(minutes=6)
USER_DATA_NOTE = "UserData có thể còn chạy tới vài phút sau running"
GONE_INSTANCE_STATES = {"terminated", "shutting-down"}
GONE_NAT_STATES = {"deleted", "deleting", "failed"}
CLIENT_CONFIG = Config(connect_timeout=2, read_timeout=5, retries={"max_attempts": 1, "mode": "standard"})


def _label(resource: dict, fallback: str) -> str:
    for tag in resource.get("Tags") or []:
        if tag.get("Key") == "Name" and tag.get("Value"):
            return tag["Value"]
    return fallback


def _tags(resource: dict) -> dict[str, str]:
    return {t["Key"]: t.get("Value", "") for t in resource.get("Tags") or [] if t.get("Key") != "Name"}


def _time(value: Any) -> datetime | None:
    """LaunchTime is a datetime from boto3 and an ISO string in the CLI's JSON."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        return _time(datetime.fromisoformat(value.replace("Z", "+00:00")))
    return None


def _main_tables(route_tables: list[dict]) -> dict[str, dict]:
    return {
        rt["VpcId"]: rt
        for rt in route_tables
        if any(a.get("Main") for a in rt.get("Associations") or [])
    }


def _effective_tables(subnets: list[dict], route_tables: list[dict]) -> dict[str, dict]:
    """The route table each subnet uses: its explicit association, else its VPC's main table."""
    explicit = {
        a["SubnetId"]: rt
        for rt in route_tables
        for a in rt.get("Associations") or []
        if a.get("SubnetId")
    }
    main = _main_tables(route_tables)
    return {
        s["SubnetId"]: explicit.get(s["SubnetId"]) or main.get(s["VpcId"])
        for s in subnets
        if explicit.get(s["SubnetId"]) or main.get(s["VpcId"])
    }


def _is_public(route_table: dict | None) -> bool:
    return bool(route_table) and any(
        r.get("DestinationCidrBlock") == "0.0.0.0/0" and str(r.get("GatewayId", "")).startswith("igw-")
        for r in route_table.get("Routes") or []
    )


def build_graph(
    raw: dict[str, list[dict]],
    *,
    host_ports: dict[str, dict[str, int]] | None = None,
    user_data: dict[str, bool] | None = None,
    dns_hostnames: dict[str, bool] | None = None,
    now: datetime,
    region: str = REGION,
) -> ResourceGraph:
    """Graph from describe responses keyed by DESCRIBE's response keys (lists, any order)."""
    host_ports = host_ports or {}
    user_data = user_data or {}
    dns_hostnames = dns_hostnames or {}
    nodes: dict[str, Node] = {}
    contains: list[Contains] = []
    edges: dict[str, Edge] = {}
    warnings: list[str] = []

    def add(node_id: str, kind: str, label: str, parent: str | None, **props: Any) -> None:
        nodes[node_id] = Node(id=node_id, kind=kind, label=label, props={k: v for k, v in props.items() if v not in (None, {}, [])})
        if parent is not None:
            contains.append(Contains(parent=parent, child=node_id))

    def link(kind: str, src: str, dst: str, label: str = "") -> None:
        if src in nodes and dst in nodes:
            edge_id = f"{kind}:{src}->{dst}" + (f":{label}" if label else "")
            edges[edge_id] = Edge(id=edge_id, kind=kind, from_=src, to=dst, label=label)

    add(region, "region", region, None)

    vpcs = raw.get("Vpcs", [])
    for v in vpcs:
        add(v["VpcId"], "vpc", _label(v, v["VpcId"]), region, cidr=v.get("CidrBlock"), isDefault=v.get("IsDefault") or None,
            enableDnsHostnames=dns_hostnames.get(v["VpcId"]), tags=_tags(v))

    route_tables = raw.get("RouteTables", [])
    subnets = [s for s in raw.get("Subnets", []) if s.get("VpcId") in nodes]
    effective = _effective_tables(subnets, route_tables)
    for vpc_id, az in sorted({(s["VpcId"], s["AvailabilityZone"]) for s in subnets}):
        add(f"{vpc_id}/{az}", "az", az, vpc_id)
    subnet_cidrs: dict[str, str] = {}
    for s in subnets:
        sid = s["SubnetId"]
        public = _is_public(effective.get(sid))
        subnet_cidrs[sid] = s.get("CidrBlock", "")
        add(sid, "subnet-public" if public else "subnet-private", _label(s, sid), f"{s['VpcId']}/{s['AvailabilityZone']}",
            cidr=s.get("CidrBlock"), az=s["AvailabilityZone"], mapPublicIpOnLaunch=s.get("MapPublicIpOnLaunch"), tags=_tags(s))

    for g in raw.get("InternetGateways", []):
        attached = [a["VpcId"] for a in g.get("Attachments") or [] if a.get("VpcId") in nodes]
        add(g["InternetGatewayId"], "igw", _label(g, g["InternetGatewayId"]), attached[0] if attached else region,
            attachedVpc=attached[0] if attached else None, tags=_tags(g))

    nat_eips: dict[str, str] = {}
    for n in raw.get("NatGateways", []):
        if n.get("State") in GONE_NAT_STATES or n.get("SubnetId") not in nodes:
            continue
        addresses = n.get("NatGatewayAddresses") or []
        add(n["NatGatewayId"], "nat", _label(n, n["NatGatewayId"]), n["SubnetId"],
            state=n.get("State"), publicIp=next((a.get("PublicIp") for a in addresses if a.get("PublicIp")), None), tags=_tags(n))
        for a in addresses:
            if a.get("AllocationId"):
                nat_eips[a["AllocationId"]] = n["NatGatewayId"]

    for rt in route_tables:
        if rt.get("VpcId") not in nodes:
            continue
        rid = rt["RouteTableId"]
        main = any(a.get("Main") for a in rt.get("Associations") or [])
        add(rid, "route-table", _label(rt, rid), rt["VpcId"], main=main or None, tags=_tags(rt))

    for g in raw.get("SecurityGroups", []):
        if g.get("VpcId") not in nodes:
            continue
        rules = [
            {"protocol": p.get("IpProtocol"), "from": p.get("FromPort"), "to": p.get("ToPort"),
             "sources": sorted(r["CidrIp"] for r in p.get("IpRanges") or [] if r.get("CidrIp"))
             + sorted(u["GroupId"] for u in p.get("UserIdGroupPairs") or [] if u.get("GroupId"))}
            for p in g.get("IpPermissions") or []
        ]
        rules.sort(key=lambda r: (str(r["protocol"]), r["from"] if r["from"] is not None else -1, r["to"] if r["to"] is not None else -1))
        add(g["GroupId"], "security-group", _label(g, g.get("GroupName") or g["GroupId"]), g["VpcId"],
            groupName=g.get("GroupName"), ingress=rules, tags=_tags(g))

    key_ids: dict[str, str] = {}
    for k in raw.get("KeyPairs", []):
        kid = k.get("KeyPairId") or k["KeyName"]
        key_ids[k["KeyName"]] = kid
        add(kid, "key-pair", k["KeyName"], region, fingerprint=k.get("KeyFingerprint"), tags=_tags(k))

    instances = [i for r in raw.get("Reservations", []) for i in r.get("Instances") or []]
    for i in instances:
        iid = i["InstanceId"]
        state = (i.get("State") or {}).get("Name")
        if state in GONE_INSTANCE_STATES or i.get("SubnetId") not in nodes:
            continue
        props: dict[str, Any] = {
            "state": state, "instanceType": i.get("InstanceType"), "imageId": i.get("ImageId"),
            "privateIp": i.get("PrivateIpAddress"), "keyName": i.get("KeyName"), "tags": _tags(i),
        }
        public_ip = i.get("PublicIpAddress")
        if public_ip == LOOPBACK_PUBLIC_IP:
            props["hostPorts"] = host_ports.get(iid)
        else:
            props["publicIp"] = public_ip
        cidr, private_ip = subnet_cidrs.get(i["SubnetId"]), i.get("PrivateIpAddress")
        if cidr and private_ip and ipaddress.ip_address(private_ip) not in ipaddress.ip_network(cidr, strict=False):
            props["privateIpOutOfCidr"] = True
            warnings.append(f"{iid}: IP riêng {private_ip} nằm ngoài CIDR {cidr} của {i['SubnetId']} (Floci cấp IP từ mạng Docker)")
        launched = _time(i.get("LaunchTime"))
        if user_data.get(iid) and launched and now - launched < USER_DATA_WINDOW:
            props["note"] = USER_DATA_NOTE
        add(iid, "instance", _label(i, iid), i["SubnetId"], **props)
        for g in i.get("SecurityGroups") or []:
            link("attached", g["GroupId"], iid)
        if i.get("KeyName") in key_ids:
            link("uses-key", iid, key_ids[i["KeyName"]])

    for a in raw.get("Addresses", []):
        aid = a.get("AllocationId") or a["PublicIp"]
        add(aid, "elastic-ip", _label(a, a.get("PublicIp") or aid), region, publicIp=a.get("PublicIp"), tags=_tags(a))
        target = a.get("InstanceId") or nat_eips.get(aid)
        if target:
            link("attached", aid, target)

    for rt in route_tables:
        rid = rt["RouteTableId"]
        for r in rt.get("Routes") or []:
            target = r.get("GatewayId") if r.get("GatewayId") != "local" else None
            target = target or r.get("NatGatewayId")
            if target:
                link("route", rid, target, r.get("DestinationCidrBlock") or r.get("DestinationIpv6CidrBlock") or "")
        for a in rt.get("Associations") or []:
            if a.get("SubnetId"):
                link("association", rid, a["SubnetId"])

    return ResourceGraph(
        taken_at=now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        nodes=sorted(nodes.values(), key=lambda n: n.id),
        contains=sorted(contains, key=lambda c: (c.child, c.parent)),
        edges=sorted(edges.values(), key=lambda e: e.id),
        warnings=sorted(warnings),
    )


def emulator_down(now: datetime, region: str = REGION, reason: str = "") -> ResourceGraph:
    return ResourceGraph(
        taken_at=now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        status="emulator-down",
        nodes=[Node(id=region, kind="region", label=region)],
        contains=[],
        edges=[],
        warnings=[f"Floci không trả lời: {reason}"] if reason else [],
    )


def fetch(ec2: Any) -> dict[str, list[dict]]:
    """All describe calls at once; one boto3 client is safe to share between threads."""
    def call(method: str) -> list[dict]:
        return ec2.get_paginator(method).paginate().build_full_result().get(DESCRIBE[method], []) \
            if ec2.can_paginate(method) else getattr(ec2, method)().get(DESCRIBE[method], [])

    with ThreadPoolExecutor(max_workers=len(DESCRIBE)) as pool:
        results = dict(zip(DESCRIBE.values(), pool.map(call, DESCRIBE)))
    return results


def vpc_dns_hostnames(ec2: Any, raw: dict[str, list[dict]]) -> dict[str, bool]:
    """enableDnsHostnames per VPC: describe_vpcs leaves it out, so one call per VPC, in parallel."""
    def attr(vpc_id: str) -> tuple[str, bool | None]:
        try:
            value = ec2.describe_vpc_attribute(VpcId=vpc_id, Attribute="enableDnsHostnames")
        except ClientError:  # deleted between the two calls: leave the prop out
            return vpc_id, None
        return vpc_id, (value.get("EnableDnsHostnames") or {}).get("Value")

    ids = [v["VpcId"] for v in raw.get("Vpcs", [])]
    if not ids:
        return {}
    with ThreadPoolExecutor(max_workers=min(len(ids), 8)) as pool:
        return {vpc_id: value for vpc_id, value in pool.map(attr, ids) if value is not None}


def recent_user_data(ec2: Any, raw: dict[str, list[dict]], now: datetime) -> dict[str, bool]:
    """UserData is only visible through describe_instance_attribute; ask only for fresh instances."""
    found = {}
    for r in raw.get("Reservations", []):
        for i in r.get("Instances") or []:
            launched = _time(i.get("LaunchTime"))
            if launched and now - launched < USER_DATA_WINDOW and (i.get("State") or {}).get("Name") not in GONE_INSTANCE_STATES:
                try:
                    attr = ec2.describe_instance_attribute(InstanceId=i["InstanceId"], Attribute="userData")
                except ClientError:  # terminated between the two calls: leave the hint out
                    continue
                found[i["InstanceId"]] = bool((attr.get("UserData") or {}).get("Value"))
    return found


def collect(
    provider: AwsProvider | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ports: Callable[[], dict[str, dict[str, int]]] = docker_host_ports,
) -> ResourceGraph:
    provider = provider or AwsProvider("floci")
    ec2 = provider.client("ec2", direct=True, config=CLIENT_CONFIG)
    now = clock()
    try:
        raw = fetch(ec2)
        user_data = recent_user_data(ec2, raw, now)
        dns_hostnames = vpc_dns_hostnames(ec2, raw)
    except EndpointConnectionError as e:  # connection refused: Floci is stopped or being recreated
        return emulator_down(now, reason=type(e).__name__)
    # Timeouts and other errors propagate: they can be one slow answer, and the hub decides.
    needs_ports = any(
        i.get("PublicIpAddress") == LOOPBACK_PUBLIC_IP for r in raw["Reservations"] for i in r.get("Instances") or []
    )
    return build_graph(raw, host_ports=ports() if needs_ports else {}, user_data=user_data,
                       dns_hostnames=dns_hostnames, now=now)


def region_azs(provider: AwsProvider | None = None) -> list[str]:
    """Availability Zones of the region as the emulator reports them; empty when it does not answer."""
    ec2 = (provider or AwsProvider("floci")).client("ec2", direct=True, config=CLIENT_CONFIG)
    try:
        zones = ec2.describe_availability_zones()["AvailabilityZones"]
    except (BotoCoreError, ClientError):
        return []
    return sorted(z["ZoneName"] for z in zones if z.get("State", "available") == "available")
