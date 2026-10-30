import json
import shlex
from pathlib import Path

import pytest

from cloudy_labs.builder.ops import OPS, catalog, display, expectation, practice_expectation, result_id

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
        ("create-security-group", {"name": "lab07-web", "vpcId": "vpc-1", "description": "Lab 7 web"},
         "ec2 create-security-group --group-name lab07-web --description 'Lab 7 web' --vpc-id vpc-1 "
         "--tag-specifications 'ResourceType=security-group,Tags=[{Key=Name,Value=lab07-web},{Key=lab,Value=06}]'"),
        ("authorize-security-group-ingress", {"groupId": "sg-1", "protocol": "tcp", "port": "22", "cidr": "203.0.113.10/32"},
         """ec2 authorize-security-group-ingress --group-id sg-1 --ip-permissions """
         """'[{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "203.0.113.10/32"}]}]'"""),
        ("authorize-security-group-ingress", {"groupId": "sg-1", "protocol": "-1", "port": "", "cidr": "10.0.0.0/8"},
         """ec2 authorize-security-group-ingress --group-id sg-1 --ip-permissions '[{"IpProtocol": "-1", "IpRanges": [{"CidrIp": "10.0.0.0/8"}]}]'"""),
        ("authorize-security-group-ingress", {"groupId": "sg-1", "protocol": "icmp", "port": "80", "cidr": "10.0.0.0/8"},
         """ec2 authorize-security-group-ingress --group-id sg-1 --ip-permissions """
         """'[{"IpProtocol": "icmp", "FromPort": -1, "ToPort": -1, "IpRanges": [{"CidrIp": "10.0.0.0/8"}]}]'"""),
        ("create-key-pair", {"name": "lab07-key"},
         "ec2 create-key-pair --key-name lab07-key --tag-specifications 'ResourceType=key-pair,Tags=[{Key=Name,Value=lab07-key},{Key=lab,Value=06}]'"),
        ("run-instances", {"name": "lab07-web", "subnetId": "subnet-1", "imageId": "ami-amazonlinux2023-arm64",
                           "instanceType": "t4g.micro", "securityGroupId": "sg-1", "keyName": "lab07-key", "userData": "#!/bin/sh"},
         "ec2 run-instances --image-id ami-amazonlinux2023-arm64 --instance-type t4g.micro --subnet-id subnet-1 "
         "--security-group-ids sg-1 --count 1 --key-name lab07-key --user-data '#!/bin/sh' "
         "--tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=lab07-web},{Key=lab,Value=06}]'"),
        ("run-instances", {"name": "w", "subnetId": "subnet-1", "imageId": "ami-amazonlinux2023", "instanceType": "t3.micro",
                           "securityGroupId": "sg-1", "keyName": "", "userData": ""},
         "ec2 run-instances --image-id ami-amazonlinux2023 --instance-type t3.micro --subnet-id subnet-1 "
         "--security-group-ids sg-1 --count 1 --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=w},{Key=lab,Value=06}]'"),
        ("modify-instance-attribute", {"instanceId": "i-1", "groupId": "sg-2", "currentGroups": ["sg-1"]},
         "ec2 modify-instance-attribute --instance-id i-1 --groups sg-1 sg-2"),
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
    assert len(catalog(["vpc", "subnet", "igw", "elastic-ip", "nat", "route-table", "security-group", "key-pair", "instance"])) == len(OPS)
    assert names(["security-group"]) == ["create-security-group", "authorize-security-group-ingress", "modify-instance-attribute"]
    assert names(["key-pair", "instance"]) == ["create-key-pair", "run-instances"]
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


def test_multiline_user_data_round_trips_through_the_shell():
    script = (Path(__file__).parent / "fixtures" / "labs" / "fixture-lab-07" / "lab.yaml").read_text()
    user_data = script[script.index("#!/bin/sh"):script.index("tasks:")]  # quotes, $( ), ${ }, & and newlines
    a = argv("run-instances", name="w", subnetId="subnet-1", imageId="ami-amazonlinux2023-arm64", instanceType="t4g.micro",
             securityGroupId="sg-1", keyName="k", userData=user_data)
    assert shlex.split(display(a)) == a and a[a.index("--user-data") + 1] == user_data


def test_result_id_follows_list_indexes():
    run = OPS["run-instances"]
    out = json.dumps({"Groups": [], "Instances": [{"InstanceId": "i-9", "State": {"Name": "pending"}}]})
    assert result_id(run, out) == "i-9"
    assert result_id(run, '{"Instances": []}') is None and result_id(run, '{"Instances": {"0": "x"}}') is None
    assert result_id(OPS["create-key-pair"], '{"KeyPairId": "key-1", "KeyMaterial": "x"}') == "key-1"
    assert result_id(OPS["create-security-group"], '{"GroupId": "sg-1"}') == "sg-1"


@pytest.mark.parametrize(
    "protocol, port, includes",
    [
        ("tcp", "80", {"protocol": "tcp", "from": 80, "to": 80, "source": "0.0.0.0/0"}),
        ("icmp", "", {"protocol": "icmp", "from": -1, "to": -1, "source": "0.0.0.0/0"}),
        ("-1", "80", {"protocol": "-1", "source": "0.0.0.0/0"}),  # the collector stores no ports for all traffic
    ],
)
def test_ingress_expectation_matches_the_collector(protocol, port, includes):
    op = OPS["authorize-security-group-ingress"]
    p = op.params.model_validate({"groupId": "sg-1", "protocol": protocol, "port": port, "cidr": "0.0.0.0/0"})
    assert expectation(op, p, '{"Return": true}', 3) == {"node": "sg-1", "prop": "ingress", "includes": includes}


def test_attach_security_group_expects_the_attached_edge():
    op = OPS["modify-instance-attribute"]
    p = op.params.model_validate({"instanceId": "i-1", "groupId": "sg-2"})
    assert expectation(op, p, "", 3) == {"edge": "attached:sg-2->i-1"}
    assert op.server_fields == ("currentGroups",)


def test_practice_expectation_waits_for_a_named_resource_or_the_same_change():
    subnet = OPS["create-subnet"]
    params = subnet.params.model_validate({"name": "lab06-public-a", "vpcId": "vpc-1", "cidr": "10.66.1.0/24", "az": "us-east-1a"})
    assert practice_expectation(subnet, params) == {"kind": "subnet", "label": "lab06-public-a"}
    attach = OPS["modify-instance-attribute"]
    params = attach.params.model_validate({"instanceId": "i-1", "groupId": "sg-2"})
    assert practice_expectation(attach, params) == {"edge": "attached:sg-2->i-1"}
