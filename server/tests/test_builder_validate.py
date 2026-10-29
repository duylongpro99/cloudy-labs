from pathlib import Path

import pytest

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
