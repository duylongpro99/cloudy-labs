from pathlib import Path

import pytest

from cloudy_labs.builder.ec2_choices import choices
from cloudy_labs.builder.ops import OPS
from cloudy_labs.builder.validate import validate
from cloudy_labs.graph.schema import ResourceGraph

GOLDEN = ResourceGraph.model_validate_json((Path(__file__).parent / "fixtures" / "graph" / "lab-06-07.graph.json").read_text())
AZS = ["us-east-1a", "us-east-1b", "us-east-1c"]
VPC, PUB_A, PRI_A = "vpc-149d0439", "subnet-83a1f79a", "subnet-e917cc42"
IGW, NAT, EIP = "igw-34ddd4cd", "nat-235f142ec41b5d904", "eipalloc-2cc57421a05781343"
RT_PUB, RT_PRI = "rtb-509e5b33", "rtb-02888668"


def graph(nodes, contains=(), edges=()) -> ResourceGraph:
    return ResourceGraph.model_validate({
        "takenAt": "2026-10-29T00:00:00Z",
        "nodes": [{"id": "us-east-1", "kind": "region", "label": "us-east-1"}, *nodes],
        "contains": list(contains),
        "edges": list(edges),
    })


def problems(op: str, g: ResourceGraph = GOLDEN, **params) -> list[tuple[str, str]]:
    p = OPS[op].params.model_validate(params)
    return [(x.field, x.message) for x in validate(op, p, g, AZS)]


def subnet(cidr: str, **over) -> list[tuple[str, str]]:
    params = {"name": "s", "vpcId": VPC, "cidr": cidr, "az": "us-east-1a"} | over
    return problems("create-subnet", **params)


def test_valid_subnet_has_no_problems():
    assert subnet("10.0.3.0/24") == []


@pytest.mark.parametrize(
    "cidr, needle",
    [
        ("10.1.0.0/24", "outside lab06-vpc (vpc-149d0439)'s block 10.0.0.0/16"),  # outside the VPC
        ("10.0.1.128/25", "overlaps subnet lab06-public-a (subnet-83a1f79a) (10.0.1.0/24)"),  # overlaps another subnet
        ("10.0.0.0/15", "/15 is outside what AWS allows"),  # prefix too short
        ("10.0.3.0/29", "/29 is outside what AWS allows"),  # prefix too long
        ("10.0.3.5/24", "host bits set: a block must start at its network address, which for /24 is 10.0.3.0/24"),
        ("10.0.3.0", "no prefix length"),
        ("10.0.3.0/024", "write the prefix length as a number, for example 10.0.3.0/24"),
        ("10.0.3.0/255.255.255.0", "write the prefix length as a number, for example 10.0.3.0/24"),
        ("10.0.300.0/24", "not an IPv4 CIDR block"),
        ("", "enter a CIDR block"),
    ],
)
def test_subnet_cidr_problems(cidr, needle):
    found = subnet(cidr)
    assert len(found) == 1 and found[0][0] == "cidr" and needle in found[0][1], found


def test_vpc_cidr_limits():
    assert problems("create-vpc", name="v", cidr="10.66.0.0/16") == []
    assert "/8 is outside" in problems("create-vpc", name="v", cidr="10.0.0.0/8")[0][1]
    assert "host bits" in problems("create-vpc", name="v", cidr="10.66.1.0/16")[0][1]


def test_container_of_the_wrong_kind():
    found = subnet("10.0.3.0/24", vpcId=PUB_A)
    assert found == [("vpcId", "lab06-public-a (subnet-83a1f79a) is a subnet-public, but this needs a VPC (a subnet always lives inside one VPC)")]
    assert "not in the scene" in subnet("10.0.3.0/24", vpcId="vpc-gone")[0][1]
    assert problems("create-route-table", name="r", vpcId=IGW)[0][0] == "vpcId"


def test_az_must_belong_to_the_region():
    assert subnet("10.0.3.0/24", az="us-west-2a") == [("az", "us-west-2a is not an Availability Zone of this region; choose one of us-east-1a, us-east-1b, us-east-1c")]


def test_name_is_required_and_shorthand_safe():
    assert problems("create-vpc", name="", cidr="10.66.0.0/16")[0][0] == "name"
    assert problems("create-vpc", name="a,b", cidr="10.66.0.0/16")[0][0] == "name"
    assert problems("create-vpc", name="a\n", cidr="10.66.0.0/16")[0][0] == "name"


def test_az_is_refused_while_the_region_zones_are_unknown():
    p = OPS["create-subnet"].params.model_validate({"name": "s", "vpcId": VPC, "cidr": "10.0.3.0/24", "az": "us-east-1a"})
    found = validate("create-subnet", p, GOLDEN, [])
    assert [x.field for x in found] == ["az"] and "could not read" in found[0].message


def test_igw_attach_rules():
    g = graph(
        [{"id": "vpc-1", "kind": "vpc", "label": "vpc-1", "props": {"cidr": "10.0.0.0/16"}},
         {"id": "vpc-2", "kind": "vpc", "label": "vpc-2", "props": {"cidr": "10.1.0.0/16"}},
         {"id": "igw-1", "kind": "igw", "label": "igw-1"},
         {"id": "igw-2", "kind": "igw", "label": "igw-2", "props": {"attachedVpc": "vpc-2"}}],
        [{"parent": "us-east-1", "child": c} for c in ("vpc-1", "igw-1")] + [{"parent": "vpc-2", "child": "igw-2"},
                                                                             {"parent": "us-east-1", "child": "vpc-2"}],
    )
    assert problems("attach-internet-gateway", g, igwId="igw-1", vpcId="vpc-1") == []
    already = problems("attach-internet-gateway", g, igwId="igw-2", vpcId="vpc-1")
    assert already[0][0] == "igwId" and "already attached to vpc-2" in already[0][1]
    taken = problems("attach-internet-gateway", g, igwId="igw-1", vpcId="vpc-2")
    assert taken[0][0] == "vpcId" and "only one Internet Gateway" in taken[0][1]


def test_nat_needs_a_public_subnet_and_a_free_eip():
    found = problems("create-nat-gateway", name="n", subnetId=PRI_A, allocationId=EIP)
    fields = [f for f, _ in found]
    assert fields == ["subnetId", "allocationId"]
    assert "must sit in a public subnet" in found[0][1] and "already in use by nat-" in found[1][1]
    empty = graph([{"id": "vpc-1", "kind": "vpc", "label": "v", "props": {"cidr": "10.0.0.0/16"}}], [{"parent": "us-east-1", "child": "vpc-1"}])
    assert problems("create-nat-gateway", empty, name="n", subnetId="", allocationId="") == [
        ("subnetId", "choose a subnet"), ("allocationId", "a NAT Gateway needs an Elastic IP; allocate one first")]


def test_route_rules():
    # The golden graph already has both default routes.
    dup = problems("create-route", routeTableId=RT_PUB, destination="0.0.0.0/0", targetId=IGW)
    assert dup == [("destination", "lab06-rt-public (rtb-509e5b33) already has a route for 0.0.0.0/0; each destination can appear once per route table")]
    assert problems("create-route", routeTableId=RT_PUB, destination="192.168.0.0/16", targetId=IGW) == []
    other_vpc = problems("create-route", routeTableId="rtb-default", destination="10.9.0.0/16", targetId=NAT)
    assert other_vpc[0][0] == "targetId" and "own VPC" in other_vpc[0][1]
    assert problems("create-route", routeTableId=RT_PUB, destination="10.9.0.1/16", targetId=IGW)[0][0] == "destination"
    assert problems("create-route", routeTableId=PUB_A, destination="0.0.0.0/0", targetId=IGW)[0][0] == "routeTableId"


def test_route_to_unattached_igw_or_pending_nat():
    g = graph(
        [{"id": "vpc-1", "kind": "vpc", "label": "v", "props": {"cidr": "10.0.0.0/16"}},
         {"id": "vpc-1/us-east-1a", "kind": "az", "label": "us-east-1a"},
         {"id": "subnet-1", "kind": "subnet-public", "label": "s", "props": {"cidr": "10.0.1.0/24"}},
         {"id": "nat-1", "kind": "nat", "label": "n", "props": {"state": "pending"}},
         {"id": "igw-1", "kind": "igw", "label": "i"},
         {"id": "rtb-1", "kind": "route-table", "label": "r"}],
        [{"parent": "us-east-1", "child": "vpc-1"}, {"parent": "vpc-1", "child": "vpc-1/us-east-1a"},
         {"parent": "vpc-1/us-east-1a", "child": "subnet-1"}, {"parent": "subnet-1", "child": "nat-1"},
         {"parent": "us-east-1", "child": "igw-1"}, {"parent": "vpc-1", "child": "rtb-1"}],
    )
    assert "not attached to a VPC yet" in problems("create-route", g, routeTableId="rtb-1", destination="0.0.0.0/0", targetId="igw-1")[0][1]
    assert "is pending; wait until it is available" in problems("create-route", g, routeTableId="rtb-1", destination="0.0.0.0/0", targetId="nat-1")[0][1]


def test_association_rules():
    assert problems("associate-route-table", routeTableId="rtb-157470092a6fefa4a", subnetId="subnet-default-us-east-1-a")[0][1].endswith(
        "a route table serves subnets of its own VPC")
    taken = problems("associate-route-table", routeTableId=RT_PUB, subnetId=PRI_A)
    assert taken == [("subnetId", f"lab06-private-a ({PRI_A}) already uses route table {RT_PRI}; a subnet is associated with one route table at a time")]


def test_attribute_ops_need_the_right_node():
    assert problems("modify-vpc-attribute", vpcId=VPC) == []
    assert problems("modify-subnet-attribute", subnetId=PUB_A) == []
    assert problems("modify-subnet-attribute", subnetId=VPC)[0][0] == "subnetId"


SG_WEB, SG_DEFAULT, INSTANCE, KEY = "sg-dbd2e6007fa2e7eef", "sg-b58b05ddff613fe13", "i-fdb553d289095d128", "key-856759379e524ce96"
ARM = choices("arm64")


def fields(found: list[tuple[str, str]]) -> list[str]:
    return [f for f, _ in found]


def test_choices_follow_the_host_architecture():
    assert choices("arm64") == choices("aarch64") == {"images": ["ami-amazonlinux2023-arm64"], "instanceTypes": ["t4g.micro", "t4g.small"]}
    assert choices("x86_64") == choices("AMD64") == {"images": ["ami-amazonlinux2023"], "instanceTypes": ["t3.micro", "t3.small"]}


def sg(**over) -> list[tuple[str, str]]:
    return problems("create-security-group", **({"name": "web", "vpcId": VPC, "description": "Lab web server"} | over))


def test_create_security_group_rules():
    assert sg() == []
    assert fields(sg(vpcId=PUB_A)) == ["vpcId"]
    assert "may not start with sg-" in sg(name="sg-web")[0][1]
    assert "already has a security group named lab07-web (sg-dbd2e6007fa2e7eef)" in sg(name="lab07-web")[0][1]
    assert sg(name="lab07-web", vpcId="vpc-default-us-east-1") == []  # the name is free in another VPC
    assert "AWS requires a description" in sg(description="  ")[0][1]
    assert fields(sg(description="Máy chủ web")) == ["description"]
    assert fields(sg(description="x" * 256)) == ["description"]
    assert fields(sg(description="web\nserver")) == ["description"]  # AWS refuses line breaks and quotes
    assert fields(sg(description='say "hi"')) == ["description"]
    assert sg(description="SSH from 203.0.113.10/32 (admin) #1") == []


@pytest.mark.parametrize("field", ["description", "userData"])
@pytest.mark.parametrize("value", ["file:///etc/passwd", "fileb://key.pem", "  FILE://x"])
def test_values_the_cli_would_read_as_files_are_refused(field, value):
    """The aws CLI reads file://path and fileb://path into any parameter: the server's own files."""
    found = sg(description=value) if field == "description" else run(userData=value)
    assert field in fields(found) and any("file://" in m for _, m in found), found


def ingress(**over) -> list[tuple[str, str]]:
    return problems("authorize-security-group-ingress", **({"groupId": SG_WEB, "protocol": "tcp", "port": "443", "cidr": "0.0.0.0/0"} | over))


def test_ingress_rule_is_valid():
    assert ingress() == []
    assert ingress(protocol="udp", port="53", cidr="10.0.0.0/16") == []
    assert ingress(protocol="icmp", port="", cidr="10.0.0.0/16") == []
    assert ingress(port="22", cidr="198.51.100.7/32") == []
    assert ingress(protocol="udp", port="22") == []  # not SSH


@pytest.mark.parametrize(
    "over, field, needle",
    [
        ({"port": "http"}, "port", "http is not a port number"),
        ({"port": ""}, "port", "(none) is not a port number"),
        ({"port": "-5"}, "port", "not a port number"),
        ({"port": "65536"}, "port", "ports go from 0 to 65535"),
        ({"port": "²"}, "port", "is not a port number"),  # str.isdigit() takes it, int() does not
        ({"protocol": "ssh"}, "protocol", "choose tcp, udp, icmp, or -1"),
        ({"cidr": "0.0.0.0"}, "cidr", "no prefix length"),
        ({"cidr": "::/0"}, "cidr", "IPv6"),
        ({"port": "22"}, "cidr", "open SSH (port 22) to the whole Internet"),
        ({"protocol": "-1", "port": ""}, "cidr", "all traffic, including SSH on port 22,"),
        ({"port": "80"}, "cidr", "already allows this (tcp 80 from 0.0.0.0/0)"),
        ({"port": "22", "cidr": "203.0.113.10/32"}, "cidr", "already allows this"),
        ({"groupId": INSTANCE}, "groupId", "this needs a security group"),
    ],
)
def test_ingress_problems(over, field, needle):
    found = ingress(**over)
    assert len(found) == 1 and found[0][0] == field and needle in found[0][1], found


def test_key_pair_names_are_unique():
    assert problems("create-key-pair", name="lab07-key-2") == []
    assert "a key pair named lab07-key already exists" in problems("create-key-pair", name="lab07-key")[0][1]
    assert fields(problems("create-key-pair", name="my key")) == ["name"]


def run(**over) -> list[tuple[str, str]]:
    params = {"name": "web-2", "subnetId": PUB_A, "imageId": "ami-amazonlinux2023-arm64", "instanceType": "t4g.micro",
              "securityGroupId": SG_WEB, "keyName": "lab07-key", "userData": "#!/bin/sh\n"} | over
    p = OPS["run-instances"].params.model_validate(params)
    return [(x.field, x.message) for x in validate("run-instances", p, GOLDEN, AZS, ARM)]


def test_run_instances_rules():
    assert run() == []
    assert run(keyName="", userData="") == []
    assert run(subnetId=PRI_A) == []  # later labs may need a private instance
    assert "belongs to vpc-149d0439 but subnet-default-us-east-1-a is in vpc-default-us-east-1" in run(subnetId="subnet-default-us-east-1-a")[0][1]
    assert "create one in this VPC first" in run(securityGroupId="")[0][1]
    assert "no key pair named nope" in run(keyName="nope")[0][1]
    assert "choose ami-amazonlinux2023-arm64" in run(imageId="ami-amazonlinux2023")[0][1]
    assert "choose one of t4g.micro, t4g.small" in run(instanceType="t3.micro")[0][1]
    assert fields(run(userData="x" * 16384)) == []
    assert "16,385 bytes" in run(userData="x" * 16385)[0][1]
    assert fields(run(subnetId=VPC)) == ["subnetId"]


def attach(g: ResourceGraph = GOLDEN, **over) -> list[tuple[str, str]]:
    return problems("modify-instance-attribute", g, **({"instanceId": INSTANCE, "groupId": SG_DEFAULT} | over))


def test_attach_security_group_rules():
    assert attach() == []
    assert "lab07-web (sg-dbd2e6007fa2e7eef) is already attached to lab07-web (i-fdb553d289095d128)" in attach(groupId=SG_WEB)[0][1]
    assert "an instance can only use security groups of its own VPC" in attach(groupId="sg-default-us-east-1")[0][1]
    assert fields(attach(instanceId=KEY)) == ["instanceId"]
    stopping = GOLDEN.model_copy(update={"nodes": [
        n.model_copy(update={"props": n.props | {"state": "shutting-down"}}) if n.id == INSTANCE else n for n in GOLDEN.nodes]})
    assert "is shutting-down" in attach(stopping)[0][1]
    assert "already has 5 security groups" in attach(currentGroups=("sg-1",) * 5)[0][1]
