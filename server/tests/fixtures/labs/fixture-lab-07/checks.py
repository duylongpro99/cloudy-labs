"""Setup and checks for the Lab 7 fixture. The VPC is found by its lab tag; everything else by that VPC.

`setup_network` rebuilds the part of Lab 6 that Lab 7 runs in, since `labctl start` wipes the
emulator. A subnet counts as public when its route table sends 0.0.0.0/0 to an Internet Gateway.
"""

import urllib.error
import urllib.request

from cloudy_labs.checks import CheckContext, CheckResult
from cloudy_labs.graph.host_ports import host_ports

LAB = "fixture-lab-07"
LAB_TAG = [{"Name": "tag:lab", "Values": [LAB]}]
WORLD = "0.0.0.0/0"
LOOPBACK_PUBLIC_IP = "127.0.0.1"  # Floci on Docker Desktop: reach the instance through its host port
LIVE_STATES = {"pending", "running"}


def _tags(resource_type: str, name: str) -> list[dict]:
    return [{"ResourceType": resource_type, "Tags": [{"Key": "Name", "Value": name}, {"Key": "lab", "Value": LAB}]}]


def setup_network(ctx: CheckContext) -> None:
    ec2 = ctx.client("ec2")
    vpc = ec2.create_vpc(CidrBlock="10.67.0.0/16", TagSpecifications=_tags("vpc", "lab07-vpc"))["Vpc"]["VpcId"]
    ec2.modify_vpc_attribute(VpcId=vpc, EnableDnsHostnames={"Value": True})
    az = sorted(z["ZoneName"] for z in ec2.describe_availability_zones()["AvailabilityZones"])[0]
    subnet = ec2.create_subnet(VpcId=vpc, CidrBlock="10.67.1.0/24", AvailabilityZone=az,
                               TagSpecifications=_tags("subnet", "lab07-public"))["Subnet"]["SubnetId"]
    ec2.modify_subnet_attribute(SubnetId=subnet, MapPublicIpOnLaunch={"Value": True})
    igw = ec2.create_internet_gateway(TagSpecifications=_tags("internet-gateway", "lab07-igw"))["InternetGateway"]["InternetGatewayId"]
    ec2.attach_internet_gateway(InternetGatewayId=igw, VpcId=vpc)
    table = ec2.create_route_table(VpcId=vpc, TagSpecifications=_tags("route-table", "lab07-rt-public"))["RouteTable"]["RouteTableId"]
    ec2.create_route(RouteTableId=table, DestinationCidrBlock=WORLD, GatewayId=igw)
    ec2.associate_route_table(RouteTableId=table, SubnetId=subnet)


def _vpc(ctx: CheckContext) -> dict | None:
    vpcs = ctx.client("ec2").describe_vpcs(Filters=LAB_TAG)["Vpcs"]
    return vpcs[0] if vpcs else None


def _no_vpc() -> CheckResult:
    return CheckResult(False, f"no VPC tagged lab={LAB}; run `labctl reset {LAB}` to rebuild the network")


def _by_vpc(vpc_id: str) -> list[dict]:
    return [{"Name": "vpc-id", "Values": [vpc_id]}]


def _groups(ctx: CheckContext, vpc_id: str) -> list[dict]:
    return ctx.client("ec2").describe_security_groups(Filters=_by_vpc(vpc_id))["SecurityGroups"]


def _opens(rule: dict, port: int, cidr: str) -> bool:
    """The rule lets `cidr` reach `port` over TCP: all traffic, or a TCP range holding the port."""
    if cidr not in [r.get("CidrIp") for r in rule.get("IpRanges") or []]:
        return False
    if rule.get("IpProtocol") == "-1":
        return True
    return rule.get("IpProtocol") == "tcp" and (rule.get("FromPort") or 0) <= port <= (rule.get("ToPort") or 0)


def _web_groups(groups: list[dict]) -> list[str]:
    return [g["GroupId"] for g in groups if any(_opens(r, 80, WORLD) for r in g.get("IpPermissions") or [])]


def _instances(ctx: CheckContext, vpc_id: str) -> list[dict]:
    reservations = ctx.client("ec2").describe_instances(Filters=_by_vpc(vpc_id))["Reservations"]
    return [i for r in reservations for i in r.get("Instances") or [] if (i.get("State") or {}).get("Name") in LIVE_STATES]


def _public_subnets(ctx: CheckContext, vpc_id: str) -> set[str]:
    tables = ctx.client("ec2").describe_route_tables(Filters=_by_vpc(vpc_id))["RouteTables"]
    return {
        a["SubnetId"]
        for t in tables
        if any(r.get("DestinationCidrBlock") == WORLD and str(r.get("GatewayId") or "").startswith("igw-") for r in t.get("Routes") or [])
        for a in t.get("Associations") or []
        if a.get("SubnetId")
    }


def sg_web_80(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    web = _web_groups(_groups(ctx, vpc["VpcId"]))
    if not web:
        return CheckResult(False, f"no security group in {vpc['VpcId']} opens tcp 80 to {WORLD} yet")
    return CheckResult(True, f"{web[0]} opens tcp 80 to {WORLD}", web)


def ssh_not_open_to_world(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    groups = [g for g in _groups(ctx, vpc["VpcId"]) if g.get("GroupName") != "default"]
    if not groups:
        return CheckResult(False, f"no security group of your own in {vpc['VpcId']} yet; create the web group first")
    open_ = [g["GroupId"] for g in groups if any(_opens(r, 22, WORLD) for r in g.get("IpPermissions") or [])]
    if open_:
        return CheckResult(False, f"{', '.join(open_)} lets anyone on the Internet try to log in on port 22; "
                                  "allow SSH from your own address (/32) only", open_)
    return CheckResult(True, "no security group opens port 22 to the whole Internet", [g["GroupId"] for g in groups])


def key_pair_exists(ctx: CheckContext) -> CheckResult:
    keys = ctx.client("ec2").describe_key_pairs()["KeyPairs"]
    if not keys:
        return CheckResult(False, "no key pair yet")
    return CheckResult(True, f"key pair {keys[0]['KeyName']} exists", [k.get("KeyPairId") or k["KeyName"] for k in keys])


def instance_running(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    instances = _instances(ctx, vpc["VpcId"])
    if not instances:
        return CheckResult(False, f"no instance in {vpc['VpcId']} yet")
    public, web = _public_subnets(ctx, vpc["VpcId"]), set(_web_groups(_groups(ctx, vpc["VpcId"])))
    for i in instances:
        groups = {g["GroupId"] for g in i.get("SecurityGroups") or []}
        if i["State"]["Name"] == "running" and i.get("SubnetId") in public and i.get("KeyName") and groups & web:
            return CheckResult(True, f"{i['InstanceId']} runs in public subnet {i['SubnetId']} with key pair "
                                     f"{i['KeyName']} and port 80 open", [i["InstanceId"]])
    return CheckResult(False, "an instance must be running in the public subnet, with a key pair and a security "
                              "group that opens port 80", [i["InstanceId"] for i in instances])


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def web_server_answers(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    running = [i for i in _instances(ctx, vpc["VpcId"]) if i["State"]["Name"] == "running"]
    if not running:
        return CheckResult(False, "no running instance to ask; launch the instance first")
    ports = host_ports() if any(i.get("PublicIpAddress") == LOOPBACK_PUBLIC_IP for i in running) else {}
    for i in running:
        if i.get("PublicIpAddress") == LOOPBACK_PUBLIC_IP:
            port = ports.get(i["InstanceId"], {}).get("80/tcp")
            url = f"http://127.0.0.1:{port}/" if port else None
        else:
            url = f"http://{i['PublicIpAddress']}/" if i.get("PublicIpAddress") else None
        if url and _http_ok(url):
            return CheckResult(True, f"{i['InstanceId']} answers HTTP at {url}", [i["InstanceId"]])
    return CheckResult(False, "no instance answers HTTP on port 80 yet. UserData keeps running for a while after the "
                              "instance reports running, so wait a minute and check again; if it still fails, check "
                              "that a security group opens port 80 and that the server binds every address of the instance but lo",
                       [i["InstanceId"] for i in running])


def instance_has_two_sgs(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    instances = _instances(ctx, vpc["VpcId"])
    for i in instances:
        groups = [g["GroupId"] for g in i.get("SecurityGroups") or []]
        if len(groups) >= 2:
            return CheckResult(True, f"{i['InstanceId']} has security groups {', '.join(groups)}", [i["InstanceId"], *groups])
    if not instances:
        return CheckResult(False, f"no instance in {vpc['VpcId']} yet")
    return CheckResult(False, "attach a second security group to the instance", [i["InstanceId"] for i in instances])
