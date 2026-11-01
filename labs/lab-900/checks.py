"""Checks for Lab 900. The VPC, subnets, security group, key pair and instances are found by the
names the lab gives them; the subnets also by their CIDR in each AZ.

A web page is read through the instance's host port when Floci reports the loopback public IP,
and at its public IP otherwise.
"""

import urllib.error
import urllib.request

from cloudy_labs.checks import CheckContext, CheckResult
from cloudy_labs.graph.host_ports import host_ports

VPC_NAME = "lab900-vpc"
SG_NAME = "lab900-web-sg"
KEY_NAME = "lab900-key"
WEB_NAMES = ("lab900-web-1", "lab900-web-2")
# The page asks for t3.micro; on an Arm machine the builder offers the Graviton twin t4g.micro instead.
INSTANCE_TYPES = ("t3.micro", "t4g.micro")
AL2023 = "al2023-ami-"
WORLD = "0.0.0.0/0"
LOOPBACK_PUBLIC_IP = "127.0.0.1"  # Floci on Docker Desktop: reach the instance through its host port
LIVE_STATES = {"pending", "running"}
SUBNETS = {"ap-southeast-1a": "10.90.1.0/24", "ap-southeast-1b": "10.90.2.0/24"}


def _vpc(ctx: CheckContext) -> dict | None:
    vpcs = ctx.client("ec2").describe_vpcs(Filters=[{"Name": "tag:Name", "Values": [VPC_NAME]}])["Vpcs"]
    return vpcs[0] if vpcs else None


def _no_vpc() -> CheckResult:
    return CheckResult(False, f"no VPC named {VPC_NAME} yet; create the VPC first")


def _by_vpc(vpc_id: str) -> list[dict]:
    return [{"Name": "vpc-id", "Values": [vpc_id]}]


def _subnets(ctx: CheckContext, vpc_id: str) -> dict[str, dict]:
    """AZ -> the lab's subnet there, for the AZs where it has the expected CIDR."""
    subnets = ctx.client("ec2").describe_subnets(Filters=_by_vpc(vpc_id))["Subnets"]
    return {s["AvailabilityZone"]: s for s in subnets if SUBNETS.get(s["AvailabilityZone"]) == s["CidrBlock"]}


def _groups(ctx: CheckContext, vpc_id: str) -> list[dict]:
    return ctx.client("ec2").describe_security_groups(Filters=_by_vpc(vpc_id))["SecurityGroups"]


def _web_group(groups: list[dict]) -> dict | None:
    return next((g for g in groups if g.get("GroupName") == SG_NAME), None)


def _sources(group: dict, port: int) -> list[str]:
    """The CIDRs a group lets reach tcp `port`: all-traffic rules and TCP ranges holding the port."""
    return [
        r.get("CidrIp")
        for rule in group.get("IpPermissions") or []
        if rule.get("IpProtocol") == "-1"
        or (rule.get("IpProtocol") == "tcp" and (rule.get("FromPort") or 0) <= port <= (rule.get("ToPort") or 0))
        for r in rule.get("IpRanges") or []
    ]


def _instance(ctx: CheckContext, vpc_id: str, name: str) -> dict | None:
    reservations = ctx.client("ec2").describe_instances(
        Filters=[*_by_vpc(vpc_id), {"Name": "tag:Name", "Values": [name]}]
    )["Reservations"]
    live = [i for r in reservations for i in r.get("Instances") or [] if (i.get("State") or {}).get("Name") in LIVE_STATES]
    return live[0] if live else None


def vpc_exists(ctx: CheckContext, cidr: str) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    if vpc["CidrBlock"] != cidr:
        return CheckResult(False, f"VPC {vpc['VpcId']} has CIDR {vpc['CidrBlock']}, expected {cidr}", [vpc["VpcId"]])
    return CheckResult(True, f"VPC {vpc['VpcId']} has CIDR {cidr}", [vpc["VpcId"]])


def vpc_dns_hostnames(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    attr = ctx.client("ec2").describe_vpc_attribute(VpcId=vpc["VpcId"], Attribute="enableDnsHostnames")
    if (attr.get("EnableDnsHostnames") or {}).get("Value"):
        return CheckResult(True, f"VPC {vpc['VpcId']} has DNS hostnames enabled", [vpc["VpcId"]])
    return CheckResult(False, f"VPC {vpc['VpcId']} does not have DNS hostnames enabled", [vpc["VpcId"]])


def public_subnet(ctx: CheckContext, az: str, cidr: str) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    s = _subnets(ctx, vpc["VpcId"]).get(az)
    if s is None:
        return CheckResult(False, f"no subnet {cidr} in {az} yet")
    if not s.get("MapPublicIpOnLaunch"):
        return CheckResult(False, f"{s['SubnetId']} does not give instances a public IP on launch", [s["SubnetId"]])
    return CheckResult(True, f"{s['SubnetId']} ({cidr}, {az}) gives instances a public IP on launch", [s["SubnetId"]])


def igw_attached(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    igws = ctx.client("ec2").describe_internet_gateways(
        Filters=[{"Name": "attachment.vpc-id", "Values": [vpc["VpcId"]]}]
    )["InternetGateways"]
    if not igws:
        return CheckResult(False, f"no Internet Gateway attached to {vpc['VpcId']}")
    return CheckResult(True, f"{igws[0]['InternetGatewayId']} is attached to {vpc['VpcId']}", [igws[0]["InternetGatewayId"]])


def public_route_table(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    subnets = _subnets(ctx, vpc["VpcId"])
    if len(subnets) < len(SUBNETS):
        return CheckResult(False, "create both public subnets first")
    tables = ctx.client("ec2").describe_route_tables(Filters=_by_vpc(vpc["VpcId"]))["RouteTables"]
    served = {
        s["SubnetId"]: next((t for t in tables for a in t.get("Associations") or [] if a.get("SubnetId") == s["SubnetId"]), None)
        for s in subnets.values()
    }
    wrong = [sid for sid, t in served.items() if t is None or not any(
        r.get("DestinationCidrBlock") == WORLD and str(r.get("GatewayId") or "").startswith("igw-") for r in t.get("Routes") or []
    )]
    if wrong:
        return CheckResult(False, "subnets whose route table does not send 0.0.0.0/0 to the Internet Gateway: "
                           + ", ".join(wrong), wrong)
    ids = sorted({t["RouteTableId"] for t in served.values()})
    if len(ids) > 1:
        return CheckResult(False, f"the public subnets use {len(ids)} route tables; one is enough", ids)
    return CheckResult(True, f"{ids[0]} sends 0.0.0.0/0 to the Internet Gateway for both subnets", [*ids, *served])


def sg_http_open(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    g = _web_group(_groups(ctx, vpc["VpcId"]))
    if g is None:
        return CheckResult(False, f"no security group {SG_NAME} in {vpc['VpcId']} yet")
    if WORLD not in _sources(g, 80):
        return CheckResult(False, f"{g['GroupId']} does not open tcp 80 to {WORLD}", [g["GroupId"]])
    return CheckResult(True, f"{g['GroupId']} opens tcp 80 to {WORLD}", [g["GroupId"]])


def sg_ssh_admin_only(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    groups = _groups(ctx, vpc["VpcId"])
    g = _web_group(groups)
    if g is None:
        return CheckResult(False, f"no security group {SG_NAME} in {vpc['VpcId']} yet")
    world = [x["GroupId"] for x in groups if WORLD in _sources(x, 22)]
    if world:
        return CheckResult(False, f"{', '.join(world)} lets anyone on the Internet try to log in on port 22; "
                                  "allow SSH from the admin address (/32) only", world)
    ssh = _sources(g, 22)
    if not ssh:
        return CheckResult(False, f"{g['GroupId']} does not open tcp 22 to the admin address yet", [g["GroupId"]])
    wide = [c for c in ssh if not str(c).endswith("/32")]
    if wide:
        return CheckResult(False, f"{g['GroupId']} opens tcp 22 to {', '.join(wide)}; use one address (/32)", [g["GroupId"]])
    return CheckResult(True, f"{g['GroupId']} opens tcp 22 to {', '.join(ssh)} only", [g["GroupId"]])


def key_pair_exists(ctx: CheckContext) -> CheckResult:
    keys = [k for k in ctx.client("ec2").describe_key_pairs()["KeyPairs"] if k.get("KeyName") == KEY_NAME]
    if not keys:
        return CheckResult(False, f"no key pair {KEY_NAME} yet")
    return CheckResult(True, f"key pair {KEY_NAME} exists", [keys[0].get("KeyPairId") or KEY_NAME])


def _image_name(ctx: CheckContext, image_id: str) -> str:
    images = ctx.client("ec2").describe_images(ImageIds=[image_id])["Images"]
    return str(images[0].get("Name") or "") if images else ""


def instance_placed(ctx: CheckContext, name: str, az: str) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    i = _instance(ctx, vpc["VpcId"], name)
    if i is None:
        return CheckResult(False, f"no instance named {name} in {vpc['VpcId']} yet")
    ids = [i["InstanceId"]]
    subnet = _subnets(ctx, vpc["VpcId"]).get(az)
    groups = {g.get("GroupName") for g in i.get("SecurityGroups") or []}
    wrong = []
    if i["State"]["Name"] != "running":
        wrong.append(f"it is {i['State']['Name']}")
    if subnet is None or i.get("SubnetId") != subnet["SubnetId"]:
        wrong.append(f"it is not in the subnet {SUBNETS[az]} of {az}")
    if i.get("InstanceType") not in INSTANCE_TYPES:
        wrong.append(f"its type is {i.get('InstanceType')}, not {' or '.join(INSTANCE_TYPES)}")
    if not _image_name(ctx, i["ImageId"]).startswith(AL2023):
        wrong.append(f"its image {i['ImageId']} is not Amazon Linux 2023")
    if i.get("KeyName") != KEY_NAME:
        wrong.append(f"its key pair is {i.get('KeyName') or 'none'}, not {KEY_NAME}")
    if SG_NAME not in groups:
        wrong.append(f"it does not have the security group {SG_NAME}")
    if wrong:
        return CheckResult(False, f"{name} ({i['InstanceId']}): " + "; ".join(wrong), ids)
    return CheckResult(True, f"{name} ({i['InstanceId']}) runs AL2023 on {i['InstanceType']} in {az} with {KEY_NAME} "
                             f"and {SG_NAME}", ids)


def imdsv2_required(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    found = {n: _instance(ctx, vpc["VpcId"], n) for n in WEB_NAMES}
    missing = [n for n, i in found.items() if i is None]
    if missing:
        return CheckResult(False, f"launch {', '.join(missing)} first")
    ids = [i["InstanceId"] for i in found.values()]
    loose = [n for n, i in found.items() if (i.get("MetadataOptions") or {}).get("HttpTokens") != "required"]
    if loose:
        return CheckResult(False, f"{', '.join(loose)} still answer metadata requests without a token; "
                                  "set HttpTokens to required", ids)
    return CheckResult(True, "both web instances require IMDSv2 tokens", ids)


def _page(url: str) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.read(65536).decode("utf-8", "replace") if response.status == 200 else None
    except (urllib.error.URLError, OSError):
        return None


def page_names_instance(ctx: CheckContext, name: str) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    i = _instance(ctx, vpc["VpcId"], name)
    if i is None or i["State"]["Name"] != "running":
        return CheckResult(False, f"{name} is not running yet; launch it first")
    ids = [i["InstanceId"]]
    if i.get("PublicIpAddress") == LOOPBACK_PUBLIC_IP:
        port = host_ports().get(i["InstanceId"], {}).get("80/tcp")
        url = f"http://127.0.0.1:{port}/" if port else None
    else:
        url = f"http://{i['PublicIpAddress']}/" if i.get("PublicIpAddress") else None
    if url is None:
        return CheckResult(False, f"{name} has no public address to reach on port 80; check the subnet gives a public "
                                  "IP and the security group opens port 80", ids)
    body = _page(url)
    if body is None:
        return CheckResult(False, f"{name} does not answer HTTP at {url} yet. UserData keeps running for a while after "
                                  "the instance reports running, so wait a minute and check again; if it still fails, "
                                  "check that the UserData starts a server on port 80", ids)
    if i["InstanceId"] not in body:
        return CheckResult(False, f"{name} answers at {url}, but the page does not name {i['InstanceId']}", ids)
    return CheckResult(True, f"{name} answers at {url} with a page naming {i['InstanceId']}", ids)
