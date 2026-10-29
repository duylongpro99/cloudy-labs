"""Checks for the Lab 6 fixture. The VPC is found by its lab tag; everything else by that VPC.

A subnet counts as public when its explicit route table sends 0.0.0.0/0 to an Internet
Gateway, and private when it sends 0.0.0.0/0 to a NAT Gateway, as in Lab 6.
"""

from cloudy_labs.checks import CheckContext, CheckResult

LAB_TAG = [{"Name": "tag:lab", "Values": ["fixture-lab-06"]}]
DEFAULT = "0.0.0.0/0"
LIVE_NAT_STATES = {"pending", "available"}


def _vpc(ctx: CheckContext) -> dict | None:
    vpcs = ctx.client("ec2").describe_vpcs(Filters=LAB_TAG)["Vpcs"]
    return vpcs[0] if vpcs else None


def _no_vpc() -> CheckResult:
    return CheckResult(False, "no VPC tagged lab=fixture-lab-06 yet; create the VPC first")


def _by_vpc(vpc_id: str) -> list[dict]:
    return [{"Name": "vpc-id", "Values": [vpc_id]}]


def _tables_to(ctx: CheckContext, vpc_id: str, prefix: str) -> list[dict]:
    """Route tables of the VPC whose default route points at a gateway id starting with `prefix`."""
    tables = ctx.client("ec2").describe_route_tables(Filters=_by_vpc(vpc_id))["RouteTables"]
    return [
        t for t in tables
        if any(r.get("DestinationCidrBlock") == DEFAULT and str(r.get("GatewayId") or r.get("NatGatewayId") or "").startswith(prefix)
               for r in t.get("Routes") or [])
    ]


def _associated(tables: list[dict]) -> list[str]:
    return sorted({a["SubnetId"] for t in tables for a in t.get("Associations") or [] if a.get("SubnetId")})


def _subnets(ctx: CheckContext, vpc_id: str) -> dict[str, dict]:
    return {s["SubnetId"]: s for s in ctx.client("ec2").describe_subnets(Filters=_by_vpc(vpc_id))["Subnets"]}


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


def _pair(ctx: CheckContext, vpc_id: str, prefix: str) -> tuple[list[str], set[str]]:
    subnets = _subnets(ctx, vpc_id)
    ids = [s for s in _associated(_tables_to(ctx, vpc_id, prefix)) if s in subnets]
    return ids, {subnets[s]["AvailabilityZone"] for s in ids}


def subnets_two_azs(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    public, public_azs = _pair(ctx, vpc["VpcId"], "igw-")
    private, private_azs = _pair(ctx, vpc["VpcId"], "nat-")
    missing = []
    if len(public) < 2 or len(public_azs) < 2:
        missing.append(f"public subnets in two AZs (found {len(public)} in {len(public_azs)} AZ)")
    if len(private) < 2 or len(private_azs) < 2:
        missing.append(f"private subnets in two AZs (found {len(private)} in {len(private_azs)} AZ)")
    if missing:
        return CheckResult(False, "missing " + " and ".join(missing) + "; a subnet counts once its route table is set up",
                           public + private)
    return CheckResult(True, "two public and two private subnets across two AZs", public + private)


def public_ip_on_launch(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    subnets = _subnets(ctx, vpc["VpcId"])
    public = [s for s in _associated(_tables_to(ctx, vpc["VpcId"], "igw-")) if s in subnets]
    if not public:
        return CheckResult(False, "no public subnet yet (one whose route table sends 0.0.0.0/0 to an Internet Gateway)")
    off = [s for s in public if not subnets[s].get("MapPublicIpOnLaunch")]
    if off:
        return CheckResult(False, f"public subnets without MapPublicIpOnLaunch: {', '.join(off)}", off)
    return CheckResult(True, "every public subnet maps a public IP on launch", public)


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


def nat_in_public_subnet(ctx: CheckContext) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    ec2 = ctx.client("ec2")
    nats = [n for n in ec2.describe_nat_gateways(Filters=_by_vpc(vpc["VpcId"]))["NatGateways"] if n.get("State") in LIVE_NAT_STATES]
    if not nats:
        return CheckResult(False, f"no NAT Gateway in {vpc['VpcId']}")
    public = set(_associated(_tables_to(ctx, vpc["VpcId"], "igw-")))
    for n in nats:
        has_eip = any(a.get("AllocationId") for a in n.get("NatGatewayAddresses") or [])
        if has_eip and n["SubnetId"] in public:
            return CheckResult(True, f"{n['NatGatewayId']} has an Elastic IP and sits in public subnet {n['SubnetId']}",
                               [n["NatGatewayId"], n["SubnetId"]])
    ids = [n["NatGatewayId"] for n in nats]
    return CheckResult(False, "a NAT Gateway needs an Elastic IP and a public subnet (routed to the Internet Gateway)", ids)


def _route_table_check(ctx: CheckContext, prefix: str, kind: str, target: str) -> CheckResult:
    vpc = _vpc(ctx)
    if vpc is None:
        return _no_vpc()
    subnets = _subnets(ctx, vpc["VpcId"])
    for t in _tables_to(ctx, vpc["VpcId"], prefix):
        served = [s for s in _associated([t]) if s in subnets]
        if len(served) >= 2 and len({subnets[s]["AvailabilityZone"] for s in served}) >= 2:
            return CheckResult(True, f"{t['RouteTableId']} sends 0.0.0.0/0 to the {target} for {', '.join(served)}",
                               [t["RouteTableId"], *served])
    return CheckResult(False, f"no route table sends 0.0.0.0/0 to the {target} and serves two {kind} subnets in two AZs")


def public_route_table(ctx: CheckContext) -> CheckResult:
    return _route_table_check(ctx, "igw-", "public", "Internet Gateway")


def private_route_table(ctx: CheckContext) -> CheckResult:
    return _route_table_check(ctx, "nat-", "private", "NAT Gateway")
