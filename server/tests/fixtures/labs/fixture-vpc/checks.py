from cloudy_labs.checks import CheckContext, CheckResult


def vpc_exists(ctx: CheckContext, cidr: str) -> CheckResult:
    vpcs = ctx.client("ec2").describe_vpcs(Filters=[{"Name": "tag:lab", "Values": ["fixture-vpc"]}])["Vpcs"]
    match = [v["VpcId"] for v in vpcs if v["CidrBlock"] == cidr]
    if match:
        return CheckResult(True, f"VPC {match[0]} has CIDR {cidr}", match)
    return CheckResult(False, f"no VPC tagged lab=fixture-vpc with CIDR {cidr}")
