"""Move the recorded Floci describe fixtures (tests/fixtures/graph/floci-describe/) to another region.

The fixtures hold lab 06/07 as Floci answered it. What depends on the region (AZ names and ids,
ARNs, the default VPC's ids, private DNS names) is read from a running Floci in both regions, so
the moved fixtures say what Floci says there; resource ids Floci draws at random stay as they
are, and the tests that name them keep working.

    labctl up
    uv run python scripts/move-floci-fixtures-region.py us-east-1 ap-southeast-2

Launches one instance in the target region's default subnet to read its DNS name, then
terminates it. Run `labctl reset` afterwards if a lab is open.
"""

import argparse
import sys
from pathlib import Path

from cloudy_labs.providers.aws import AwsProvider

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "graph" / "floci-describe"


def zones(ec2) -> list[tuple[str, str]]:
    return sorted((z["ZoneName"], z["ZoneId"]) for z in ec2.describe_availability_zones()["AvailabilityZones"])


def dns_suffix(ec2, subnet: str) -> str:
    """What Floci appends to `ip-a-b-c-d` in this region."""
    image = next((i["ImageId"] for i in ec2.describe_images(Owners=["amazon"])["Images"]), "ami-0abcdef1234567890")
    instance = ec2.run_instances(ImageId=image, InstanceType="t3.micro", MinCount=1, MaxCount=1, SubnetId=subnet)["Instances"][0]
    try:
        return instance["PrivateDnsName"].split(".", 1)[1]
    finally:
        ec2.terminate_instances(InstanceIds=[instance["InstanceId"]])


def default_ids(ec2) -> list[str]:
    vpc = next(v for v in ec2.describe_vpcs()["Vpcs"] if v.get("IsDefault"))
    subnets = sorted(s["SubnetId"] for s in ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc["VpcId"]]}])["Subnets"])
    groups = sorted(g["GroupId"] for g in ec2.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [vpc["VpcId"]]}])["SecurityGroups"])
    return [vpc["VpcId"], *subnets, *groups]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source", help="the region the fixtures were recorded in")
    parser.add_argument("target", help="the region to move them to")
    args = parser.parse_args()
    src = AwsProvider("floci", args.source).client("ec2", direct=True)
    dst = AwsProvider("floci", args.target).client("ec2", direct=True)

    src_zones, dst_zones = zones(src), zones(dst)
    if len(src_zones) != len(dst_zones):
        print(f"{args.source} has {len(src_zones)} AZs and {args.target} {len(dst_zones)}; cannot pair them", file=sys.stderr)
        return 1
    src_default, dst_default = default_ids(src), default_ids(dst)
    # Longest first: an AZ name contains the region name.
    pairs = [*((a[0], b[0]) for a, b in zip(src_zones, dst_zones)), *((a[1], b[1]) for a, b in zip(src_zones, dst_zones))]
    pairs.append(("." + dns_suffix(src, src_default[1]), "." + dns_suffix(dst, dst_default[1])))
    pairs.append((args.source, args.target))
    pairs.sort(key=lambda p: -len(p[0]))

    def move(text: str) -> str:
        for old, new in pairs:
            text = text.replace(old, new)
        return text

    moved = [move(i) for i in src_default]
    if moved != dst_default:
        print(f"Floci's default resources do not move by name: {moved} != {dst_default}", file=sys.stderr)
        return 1
    for path in sorted(FIXTURES.iterdir()):
        text = path.read_text()
        if (new := move(text)) != text:
            path.write_text(new)
            print(f"moved {path.name}")
    for old, new in pairs:
        print(f"  {old} -> {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
