import json
import shlex

import pytest

from cloudy_labs.builder.ops import OPS, catalog, display, expectation, result_id

TAGS = {"lab": "06"}
COMMON = ["--profile", "lab", "--output", "json"]


def argv(op: str, **params) -> list[str]:
    o = OPS[op]
    return o.argv(o.params.model_validate(params), TAGS)


def spike(line: str) -> list[str]:
    """A command from spikes/m0-emulators/lab-06-07.sh with --endpoint-url swapped for the lab profile."""
    return ["aws", *shlex.split(line), *COMMON]


# Each case is the same command lab-06-07.sh ran against Floci, so the builder emits CLI calls known to work there.
@pytest.mark.parametrize(
    "op, params, expected",
    [
        ("create-vpc", {"name": "lab06-vpc", "cidr": "10.0.0.0/16"},
         "ec2 create-vpc --cidr-block 10.0.0.0/16 --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=lab06-vpc},{Key=lab,Value=06}]'"),
        ("modify-vpc-attribute", {"vpcId": "vpc-1"},
         """ec2 modify-vpc-attribute --vpc-id vpc-1 --enable-dns-hostnames '{"Value": true}'"""),
        ("create-subnet", {"name": "lab06-public-a", "vpcId": "vpc-1", "cidr": "10.0.1.0/24", "az": "us-east-1a"},
         "ec2 create-subnet --vpc-id vpc-1 --cidr-block 10.0.1.0/24 --availability-zone us-east-1a "
         "--tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=lab06-public-a},{Key=lab,Value=06}]'"),
        ("modify-subnet-attribute", {"subnetId": "subnet-1"}, "ec2 modify-subnet-attribute --subnet-id subnet-1 --map-public-ip-on-launch"),
        ("create-internet-gateway", {"name": "lab06-igw"},
         "ec2 create-internet-gateway --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=lab06-igw},{Key=lab,Value=06}]'"),
        ("attach-internet-gateway", {"igwId": "igw-1", "vpcId": "vpc-1"}, "ec2 attach-internet-gateway --internet-gateway-id igw-1 --vpc-id vpc-1"),
        ("allocate-address", {"name": "lab06-eip"},
         "ec2 allocate-address --domain vpc --tag-specifications 'ResourceType=elastic-ip,Tags=[{Key=Name,Value=lab06-eip},{Key=lab,Value=06}]'"),
        ("create-nat-gateway", {"name": "lab06-nat", "subnetId": "subnet-1", "allocationId": "eipalloc-1"},
         "ec2 create-nat-gateway --subnet-id subnet-1 --allocation-id eipalloc-1 "
         "--tag-specifications 'ResourceType=natgateway,Tags=[{Key=Name,Value=lab06-nat},{Key=lab,Value=06}]'"),
        ("create-route-table", {"name": "lab06-rt-public", "vpcId": "vpc-1"},
         "ec2 create-route-table --vpc-id vpc-1 --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=lab06-rt-public},{Key=lab,Value=06}]'"),
        ("create-route", {"routeTableId": "rtb-1", "destination": "0.0.0.0/0", "targetId": "igw-1"},
         "ec2 create-route --route-table-id rtb-1 --destination-cidr-block 0.0.0.0/0 --gateway-id igw-1"),
        ("create-route", {"routeTableId": "rtb-2", "destination": "0.0.0.0/0", "targetId": "nat-1"},
         "ec2 create-route --route-table-id rtb-2 --destination-cidr-block 0.0.0.0/0 --nat-gateway-id nat-1"),
        ("associate-route-table", {"routeTableId": "rtb-1", "subnetId": "subnet-1"},
         "ec2 associate-route-table --route-table-id rtb-1 --subnet-id subnet-1"),
    ],
)
def test_argv_matches_the_spike(op, params, expected):
    assert argv(op, **params) == spike(expected)


def test_display_round_trips_through_the_shell():
    a = argv("create-vpc", name="lab06-vpc", cidr="10.0.0.0/16")
    shown = display(a)
    assert shown.startswith("aws ec2 create-vpc ") and shown.endswith("--profile lab --output json")
    assert shlex.split(shown) == a
    m = argv("modify-vpc-attribute", vpcId="vpc-1")
    assert shlex.split(display(m)) == m and json.loads(m[-5]) == {"Value": True}


def test_unknown_params_are_rejected():
    with pytest.raises(ValueError):
        OPS["create-vpc"].params.model_validate({"name": "x", "cidr": "10.0.0.0/16", "extra": "--debug"})


def test_catalog_follows_the_palette():
    def names(palette):
        return [o["name"] for o in catalog(palette)]

    assert names([]) == []
    assert names(["vpc"]) == ["create-vpc", "modify-vpc-attribute"]
    assert "attach-internet-gateway" in names(["igw"]) and "modify-subnet-attribute" in names(["subnet"])
    assert len(catalog(["vpc", "subnet", "igw", "elastic-ip", "nat", "route-table"])) == len(OPS)
    subnet = next(o for o in catalog(["subnet"]) if o["name"] == "create-subnet")
    assert subnet == {"name": "create-subnet", "gesture": "create", "creates": "subnet", "containers": ["vpc", "az"]}
    route = next(o for o in catalog(["route-table"]) if o["name"] == "create-route")
    assert route == {"name": "create-route", "gesture": "connect", "source": "route-table", "targets": ["igw", "nat"]}


def test_result_id_and_expectation():
    vpc = OPS["create-vpc"]
    out = json.dumps({"Vpc": {"VpcId": "vpc-9", "CidrBlock": "10.0.0.0/16"}})
    assert result_id(vpc, out) == "vpc-9"
    assert result_id(vpc, "not json") is None and result_id(vpc, "{}") is None
    assert result_id(OPS["allocate-address"], '{"AllocationId": "eipalloc-1"}') == "eipalloc-1"
    params = vpc.params.model_validate({"name": "a", "cidr": "10.0.0.0/16"})
    assert expectation(vpc, params, out, 3) == {"node": "vpc-9"}
    assert expectation(vpc, params, "WARNING: not json", 3) == {"after": 3}  # still waits for a newer graph
    route = OPS["create-route"]
    p = route.params.model_validate({"routeTableId": "rtb-1", "destination": "0.0.0.0/0", "targetId": "igw-1"})
    assert expectation(route, p, "", 3) == {"edge": "route:rtb-1->igw-1:0.0.0.0/0"}
    attach = OPS["attach-internet-gateway"]
    p = attach.params.model_validate({"igwId": "igw-1", "vpcId": "vpc-1"})
    assert expectation(attach, p, "", 3) == {"node": "igw-1", "prop": "attachedVpc", "value": "vpc-1"}
