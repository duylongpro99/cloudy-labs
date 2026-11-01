"""Checks for Lab 020. The VPC is found by its Name tag; subnets by their CIDR in that VPC.

Each tier has one /24 per AZ: public 10.200.{1,2,3}, app 10.200.{11,12,13} and data
10.200.{21,22,23}, in ap-southeast-2a, 2b and 2c in that order.
"""

from botocore.exceptions import ClientError

from cloudy_labs.checks import CheckContext, CheckResult

VPC_NAME = "lab020-vpc"
SUBNET_GROUP = "lab020-dbsubnet-group"
DEFAULT = "0.0.0.0/0"
LIVE_NAT_STATES = {"pending", "available"}
AZS = ["ap-southeast-2a", "ap-southeast-2b", "ap-southeast-2c"]
TIERS = {"public": 1, "app": 11, "data": 21}


def _layout(tier: str) -> dict[str, str]:
    """AZ -> the CIDR the tier's subnet has there."""
    return {az: f"10.200.{TIERS[tier] + n}.0/24" for n, az in enumerate(AZS)}


def _vpc(ctx: CheckContext) -> dict | None:
    vpcs = ctx.client("ec2").describe_vpcs(Filters=[{"Name": "tag:Name", "Values": [VPC_NAME]}])["Vpcs"]
    return vpcs[0] if vpcs else None


def _no_vpc() -> CheckResult:
    return CheckResult(False, f"no VPC named {VPC_NAME} yet; create the VPC first")


def _by_vpc(vpc_id: str) -> list[dict]:
    return [{"Name": "vpc-id", "Values": [vpc_id]}]


def _subnets(ctx: CheckContext, vpc_id: str) -> list[dict]:
    return ctx.client("ec2").describe_subnets(Filters=_by_vpc(vpc_id))["Subnets"]


def _tier(subnets: list[dict], tier: str) -> dict[str, dict]:
    """AZ -> the tier's subnet there, for the AZs where it has the expected CIDR."""
    want = _layout(tier)
    return {s["AvailabilityZone"]: s for s in subnets if want.get(s["AvailabilityZone"]) == s["CidrBlock"]}


def _tables(ctx: CheckContext, vpc_id: str) -> list[dict]:
    return ctx.client("ec2").describe_route_tables(Filters=_by_vpc(vpc_id))["RouteTables"]


def _table_of(tables: list[dict], subnet_id: str) -> dict | None:
    return next((t for t in tables for a in t.get("Associations") or [] if a.get("SubnetId") == subnet_id), None)


def _default_target(table: dict) -> str:
    route = next((r for r in table.get("Routes") or [] if r.get("DestinationCidrBlock") == DEFAULT), {})
    return str(route.get("GatewayId") or route.get("NatGatewayId") or "")


def _nats(ctx: CheckContext, vpc_id: str) -> list[dict]:
    nats = ctx.client("ec2").describe_nat_gateways(Filters=_by_vpc(vpc_id))["NatGateways"]
    return [n for n in nats if n.get("State") in LIVE_NAT_STATES]


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


def nine_subnets(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    subnets = _subnets(ctx, vpc["VpcId"])
    found, missing = [], []
    for tier in TIERS:
        have = _tier(subnets, tier)
        found += [s["SubnetId"] for s in have.values()]
        missing += [f"{tier} {cidr} in {az}" for az, cidr in _layout(tier).items() if az not in have]
    if missing:
        return CheckResult(False, "missing subnets: " + ", ".join(missing), found)
    return CheckResult(True, "nine subnets: public, app and data in each of the three AZs", found)


def three_az_ids(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    subnets = [s for tier in TIERS for s in _tier(_subnets(ctx, vpc["VpcId"]), tier).values()]
    ids = sorted({s.get("AvailabilityZoneId") or s["AvailabilityZone"] for s in subnets})
    if len(ids) < 3:
        return CheckResult(False, f"the lab subnets span {len(ids)} AZ ID(s) ({', '.join(ids) or 'none'}), expected 3",
                           [s["SubnetId"] for s in subnets])
    return CheckResult(True, f"the lab subnets span the AZ IDs {', '.join(ids)}", [s["SubnetId"] for s in subnets])


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
    public = _tier(_subnets(ctx, vpc["VpcId"]), "public")
    if len(public) < 3:
        return CheckResult(False, "create the three public subnets first")
    tables = _tables(ctx, vpc["VpcId"])
    served = {az: _table_of(tables, s["SubnetId"]) for az, s in public.items()}
    wrong = [az for az, t in served.items() if t is None or not _default_target(t).startswith("igw-")]
    if wrong:
        return CheckResult(False, "public subnets whose route table does not send 0.0.0.0/0 to the Internet Gateway: "
                           + ", ".join(public[az]["SubnetId"] for az in wrong), [public[az]["SubnetId"] for az in wrong])
    ids = sorted({t["RouteTableId"] for t in served.values()})
    if len(ids) > 1:
        return CheckResult(False, f"the public subnets use {len(ids)} route tables; one is enough", ids)
    return CheckResult(True, f"{ids[0]} sends 0.0.0.0/0 to the Internet Gateway for the three public subnets",
                       [*ids, *(s["SubnetId"] for s in public.values())])


def nat_in_az(ctx: CheckContext, az: str) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    public = _tier(_subnets(ctx, vpc["VpcId"]), "public").get(az)
    if public is None:
        return CheckResult(False, f"create the public subnet of {az} first")
    for n in _nats(ctx, vpc["VpcId"]):
        eips = [a["AllocationId"] for a in n.get("NatGatewayAddresses") or [] if a.get("AllocationId")]
        if n["SubnetId"] == public["SubnetId"] and eips:
            return CheckResult(True, f"{n['NatGatewayId']} has an Elastic IP and sits in {public['SubnetId']} of {az}",
                               [n["NatGatewayId"], public["SubnetId"], *eips])
    return CheckResult(False, f"no NAT Gateway with an Elastic IP in the public subnet {public['SubnetId']} of {az}",
                       [public["SubnetId"]])


def app_route_zonal(ctx: CheckContext, az: str) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    subnets = _subnets(ctx, vpc["VpcId"])
    app = _tier(subnets, "app")
    s = app.get(az)
    if s is None:
        return CheckResult(False, f"create the app subnet of {az} first")
    t = _table_of(_tables(ctx, vpc["VpcId"]), s["SubnetId"])
    if t is None:
        return CheckResult(False, f"{s['SubnetId']} has no route table of its own", [s["SubnetId"]])
    ids = [t["RouteTableId"], s["SubnetId"]]
    target = _default_target(t)
    if not target.startswith("nat-"):
        return CheckResult(False, f"{t['RouteTableId']} does not send 0.0.0.0/0 to a NAT Gateway", ids)
    az_of = {x["SubnetId"]: x["AvailabilityZone"] for x in subnets}
    nat_az = next((az_of.get(n["SubnetId"]) for n in _nats(ctx, vpc["VpcId"]) if n["NatGatewayId"] == target), None)
    if nat_az != az:
        return CheckResult(False, f"{s['SubnetId']} in {az} leaves through {target} in {nat_az or 'no live subnet'}", ids)
    others = [x["SubnetId"] for z, x in app.items() if z != az and _table_of([t], x["SubnetId"])]
    if others:
        return CheckResult(False, f"{t['RouteTableId']} also serves {', '.join(others)}; give each AZ its own", ids)
    return CheckResult(True, f"{s['SubnetId']} leaves through {target} of its own AZ on {t['RouteTableId']}", [*ids, target])


def data_route_table_local(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    data = _tier(_subnets(ctx, vpc["VpcId"]), "data")
    if len(data) < 3:
        return CheckResult(False, "create the three data subnets first")
    tables = _tables(ctx, vpc["VpcId"])
    served = {s["SubnetId"]: _table_of(tables, s["SubnetId"]) for s in data.values()}
    loose = [sid for sid, t in served.items() if t is None]
    if loose:
        return CheckResult(False, "data subnets without a route table of their own: " + ", ".join(loose), loose)
    ids = sorted({t["RouteTableId"] for t in served.values()})
    if len(ids) > 1:
        return CheckResult(False, f"the data subnets use {len(ids)} route tables; one is enough", ids)
    routes = next(iter(served.values())).get("Routes") or []
    extra = [r.get("DestinationCidrBlock") or r.get("DestinationPrefixListId") or "?" for r in routes if r.get("GatewayId") != "local"]
    if extra:
        return CheckResult(False, f"{ids[0]} routes more than the VPC itself: {', '.join(extra)}", ids)
    return CheckResult(True, f"{ids[0]} has only the local route and serves the three data subnets", [*ids, *served])


def db_subnet_group_three_azs(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    try:
        group = ctx.client("rds").describe_db_subnet_groups(DBSubnetGroupName=SUBNET_GROUP)["DBSubnetGroups"][0]
    except ClientError:
        return CheckResult(False, f"no DB subnet group {SUBNET_GROUP} yet")
    data = {s["SubnetId"] for s in _tier(_subnets(ctx, vpc["VpcId"]), "data").values()}
    members = {s["SubnetIdentifier"] for s in group.get("Subnets") or []}
    azs = {s["SubnetAvailabilityZone"]["Name"] for s in group.get("Subnets") or []}
    if len(data) < 3 or members != data:
        return CheckResult(False, f"{SUBNET_GROUP} should hold exactly the three data subnets", sorted(members))
    return CheckResult(True, f"{SUBNET_GROUP} holds the three data subnets across {len(azs)} AZs", [group["DBSubnetGroupArn"], *sorted(members)])
