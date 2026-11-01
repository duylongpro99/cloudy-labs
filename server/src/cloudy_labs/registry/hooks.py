"""Named hooks for rules the registry's data cannot express.

A registry entry refers to a hook by its key in `HOOKS`; nothing is imported by string. Each hook's
docstring says why data was not enough. Signatures by stage:

- list:    fn(ctx, args) -> list[item]
- enrich:  fn(ctx, client, item, args) -> dict merged into the item
- filter:  fn(ctx, item, args) -> bool (keep the item)
- props:   fn(ctx, item, args) -> dict of props

`ctx` is the collector's CollectContext: `listed(service, method, items)` returns what a list call
gave (calling it once if no kind listed it yet), `now`, `host_ports()`, `warnings` and `region`.
"""

from __future__ import annotations

import ipaddress
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import jmespath
from botocore.exceptions import ClientError

LOOPBACK_PUBLIC_IP = "127.0.0.1"  # what Floci reports on Docker Desktop; the host ports are what works
S3_NULL_LOCATION_REGION = "us-east-1"  # AWS answers a null LocationConstraint for this one region
USER_DATA_WINDOW = timedelta(minutes=6)
USER_DATA_NOTE = "UserData có thể còn chạy tới vài phút sau running"
GONE_INSTANCE_STATES = {"terminated", "shutting-down"}


def _time(value: Any) -> datetime | None:
    """LaunchTime is a datetime from boto3 and an ISO string in the CLI's JSON."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        return _time(datetime.fromisoformat(value.replace("Z", "+00:00")))
    return None


def tags(ctx, item: dict, args: dict) -> dict:
    """Tags other than Name as a dict: JMESPath cannot build an object with keys taken from data.
    `field` names the list when a service does not call it Tags (ENI: TagSet, RDS: TagList)."""
    pairs = item.get(args.get("field", "Tags")) or []
    return {"tags": {t["Key"]: t.get("Value", "") for t in pairs
                     if isinstance(t, dict) and isinstance(t.get("Key"), str) and t["Key"] != "Name"}}


def s3_in_region(ctx, item: dict, args: dict) -> bool:
    """ListBuckets answers every bucket of the account whatever the region; where a bucket lives
    takes one more call per bucket, and a null LocationConstraint names S3_NULL_LOCATION_REGION."""
    if item.get("BucketRegion"):
        return item["BucketRegion"] == ctx.region
    try:
        location = ctx.clients("s3").get_bucket_location(Bucket=item["Name"]).get("LocationConstraint")
    except ClientError:
        return False  # deleted between the two calls
    return (location or S3_NULL_LOCATION_REGION) == ctx.region


def _route_tables(ctx) -> list[dict]:
    return ctx.listed("ec2", "describe_route_tables", "RouteTables")


def _effective_tables(subnets: list[dict], route_tables: list[dict]) -> dict[str, dict]:
    """The route table each subnet uses: its explicit association, else its VPC's main table."""
    explicit = {a["SubnetId"]: rt for rt in route_tables for a in rt.get("Associations") or [] if a.get("SubnetId")}
    main = {rt["VpcId"]: rt for rt in route_tables if any(a.get("Main") for a in rt.get("Associations") or [])}
    return {s["SubnetId"]: explicit.get(s["SubnetId"]) or main.get(s["VpcId"]) for s in subnets}


def _is_public(route_table: dict | None) -> bool:
    return bool(route_table) and any(
        r.get("DestinationCidrBlock") == "0.0.0.0/0" and str(r.get("GatewayId", "")).startswith("igw-")
        for r in route_table.get("Routes") or []
    )


def subnet_visibility(ctx, item: dict, args: dict) -> bool:
    """Public when the subnet's effective route table (explicit, else the VPC main table) sends
    0.0.0.0/0 to an IGW. Needs a lookup across two responses with a fallback, beyond a path."""
    table = _effective_tables([item], _route_tables(ctx)).get(item["SubnetId"])
    return _is_public(table) == bool(args.get("public"))


def az_groups(ctx, args: dict) -> list[dict]:
    """One synthetic item per (VPC, AZ) that holds a subnet: EC2 has no such resource to list."""
    subnets = ctx.listed("ec2", "describe_subnets", "Subnets")
    pairs = sorted({(s["VpcId"], s["AvailabilityZone"]) for s in subnets if s.get("VpcId") and s.get("AvailabilityZone")})
    return [{"Id": f"{vpc}/{az}", "VpcId": vpc, "ZoneName": az} for vpc, az in pairs]


def _sg_rules(permissions: list[dict]) -> list[dict]:
    """Rules sorted by (protocol, from, to) with None first: JMESPath's sort_by takes one key of one
    type. Sources keep what a rule names, unresolved: CIDR blocks first (IPv4, then IPv6), then
    security group ids, then prefix list ids, each sorted. In an egress rule `sources` are the
    destinations: one shape for both directions keeps the reachability reader simple."""
    rules = [
        {"protocol": p.get("IpProtocol"), "from": p.get("FromPort"), "to": p.get("ToPort"),
         "sources": sorted(r["CidrIp"] for r in p.get("IpRanges") or [] if r.get("CidrIp"))
         + sorted(r["CidrIpv6"] for r in p.get("Ipv6Ranges") or [] if r.get("CidrIpv6"))
         + sorted(u["GroupId"] for u in p.get("UserIdGroupPairs") or [] if u.get("GroupId"))
         + sorted(pl["PrefixListId"] for pl in p.get("PrefixListIds") or [] if pl.get("PrefixListId"))}
        for p in permissions or []
    ]
    rules.sort(key=lambda r: (str(r["protocol"]), r["from"] if r["from"] is not None else -1, r["to"] if r["to"] is not None else -1))
    return rules


def sg_ingress(ctx, item: dict, args: dict) -> dict:
    """Inbound rules of a security group (see _sg_rules)."""
    return {"ingress": _sg_rules(item.get("IpPermissions"))}


def sg_egress(ctx, item: dict, args: dict) -> dict:
    """Outbound rules of a security group (see _sg_rules)."""
    return {"egress": _sg_rules(item.get("IpPermissionsEgress"))}


def user_data(ctx, client, item: dict, args: dict) -> dict:
    """UserData is only visible through describe_instance_attribute; ask only for instances launched
    in the last few minutes, because the note it feeds only matters then."""
    launched = _time(item.get("LaunchTime"))
    if not launched or ctx.now - launched >= USER_DATA_WINDOW or (item.get("State") or {}).get("Name") in GONE_INSTANCE_STATES:
        return {}
    try:
        attr = client.describe_instance_attribute(InstanceId=item["InstanceId"], Attribute="userData")
    except ClientError:  # terminated between the two calls: leave the hint out
        return {}
    return {"_HasUserData": bool((attr.get("UserData") or {}).get("Value"))}


def user_data_note(ctx, item: dict, args: dict) -> dict:
    """A note while UserData may still run: depends on the collect time, which data cannot see."""
    launched = _time(item.get("LaunchTime"))
    if item.get("_HasUserData") and launched and ctx.now - launched < USER_DATA_WINDOW:
        return {"note": USER_DATA_NOTE}
    return {}


def public_ip(ctx, item: dict, args: dict) -> dict:
    """Floci on Docker Desktop reports 127.0.0.1 as the public IP; the host ports Docker publishes
    are what works, and they come from `docker ps`, not from the API."""
    ip = item.get("PublicIpAddress")
    if not ip:
        return {}
    if ip == LOOPBACK_PUBLIC_IP:
        return {"hostPorts": ctx.host_ports().get(item["InstanceId"]), "hasPublicIp": True}
    return {"publicIp": ip, "hasPublicIp": True}


def private_ip_guard(ctx, item: dict, args: dict) -> dict:
    """Floci gives instances an IP from the Docker network; flag one outside its subnet's CIDR and
    warn. Needs the subnet's item and an address check, beyond a path."""
    cidrs = {s["SubnetId"]: s.get("CidrBlock", "") for s in ctx.listed("ec2", "describe_subnets", "Subnets")}
    cidr, ip, iid = cidrs.get(item.get("SubnetId")), item.get("PrivateIpAddress"), item["InstanceId"]
    try:
        outside = bool(cidr and ip) and ipaddress.ip_address(ip) not in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return {}  # a malformed address says nothing about Floci's Docker network
    if outside:
        ctx.warnings.append(f"{iid}: IP riêng {ip} nằm ngoài CIDR {cidr} của {item['SubnetId']} (Floci cấp IP từ mạng Docker)")
        return {"privateIpOutOfCidr": True}
    return {}


def test_only_items(ctx, args: dict) -> list[dict]:
    """Items for the test-only kind: a fixed list from its args, so no service is needed."""
    return list(args.get("items", [])) if args else [{"Id": "test-only-1", "Name": "test-only"}]


def rds_arns(ctx, client, item: dict, args: dict) -> dict:
    """RDS names what an item sits in or refers to (cluster, subnet group, source instance) by name
    only, while nodes are ARNs; the ARN is rebuilt from the item's own ARN prefix (partition, region,
    account). `own`: the item's ARN field; `refs`: {merged key: [ARN resource type, JMESPath]}."""
    own = item.get(args["own"])
    if not isinstance(own, str) or own.count(":") < 5:
        return {}
    prefix = ":".join(own.split(":")[:5])
    out: dict[str, Any] = {}
    for key, (rtype, path) in args["refs"].items():
        value = jmespath.search(path, item)
        if isinstance(value, list):
            out[key] = [f"{prefix}:{rtype}:{v}" for v in value if isinstance(v, str) and v]
        elif isinstance(value, str) and value:
            out[key] = f"{prefix}:{rtype}:{value}"
    return out


def last_segment(ctx, client, item: dict, args: dict) -> dict:
    """The name at the end of an ARN or URL: SQS ListQueues answers queue URLs and SNS ListTopics topic
    ARNs only, and JMESPath cannot split a string. `field`: JMESPath to the ARN or URL; `sep`: ':' or
    '/'; `as`: the key merged into the item."""
    value = jmespath.search(args["field"], item)
    if not isinstance(value, str) or not value:
        return {}
    return {args.get("as", "_Name"): value.rsplit(args.get("sep", ":"), 1)[-1]}


def s3_uri_bucket(ctx, client, item: dict, args: dict) -> dict:
    """The bucket ARN of each `s3://bucket/prefix` URI: DataSync locations, Athena result locations and
    crawler targets name a bucket only inside a URI, and JMESPath cannot split a string. `field`:
    JMESPath to a URI or a list of them; `as`: the key merged into the item. Other schemes are skipped."""
    value = jmespath.search(args["field"], item)
    uris = value if isinstance(value, list) else [value]
    arns = []
    for uri in uris:
        if isinstance(uri, str) and uri.startswith("s3://"):
            bucket = uri[len("s3://"):].split("/", 1)[0]
            if bucket and f"arn:aws:s3:::{bucket}" not in arns:
                arns.append(f"arn:aws:s3:::{bucket}")
    return {args.get("as", "_Buckets"): arns} if arns else {}


HOOKS: dict[str, Callable[..., Any]] = {
    "common.tags": tags,
    "ec2.subnet_visibility": subnet_visibility,
    "ec2.az_groups": az_groups,
    "ec2.sg_ingress": sg_ingress,
    "ec2.sg_egress": sg_egress,
    "ec2.user_data": user_data,
    "s3.in_region": s3_in_region,
    "rds.arns": rds_arns,
    "ec2.user_data_note": user_data_note,
    "ec2.public_ip": public_ip,
    "ec2.private_ip_guard": private_ip_guard,
    "test.items": test_only_items,
    "common.last_segment": last_segment,
    "common.s3_uri_bucket": s3_uri_bucket,
}
