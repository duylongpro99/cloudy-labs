"""The builder's fixed catalogue of operations (PRD F4.3, F4.4).

The browser sends a typed operation, never a command line: `{op, params}`. Each op turns its
params into one `aws` argv, and the command shown to the learner is printed from that same
argv, so what they read is exactly what runs. Pure: no I/O, no graph.
"""

import json
import shlex
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

PROFILE = "lab"  # written by `labctl up` into the learner's AWS config (aws_profile.py)
# create: dragged from the palette into a container. connect: an edge dragged between two
# objects. attribute: a button on an object's property panel.
Gesture = Literal["create", "connect", "attribute"]


class Params(BaseModel):
    # Field contents are checked by validate.py, which explains problems to the learner;
    # the model only fixes which fields exist.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True)


class Named(Params):
    name: str


class CreateVpc(Named):
    cidr: str


class CreateSubnet(Named):
    vpc_id: str
    cidr: str
    az: str


class CreateInternetGateway(Named):
    pass


class AttachInternetGateway(Params):
    igw_id: str
    vpc_id: str


class AllocateAddress(Named):
    pass


class CreateNatGateway(Named):
    subnet_id: str
    allocation_id: str


class CreateRouteTable(Named):
    vpc_id: str


class CreateRoute(Params):
    route_table_id: str
    destination: str
    target_id: str  # igw-... or nat-...


class AssociateRouteTable(Params):
    route_table_id: str
    subnet_id: str


class ModifyVpcAttribute(Params):
    vpc_id: str


class ModifySubnetAttribute(Params):
    subnet_id: str


Tags = dict[str, str]
SUBNET_KINDS = ("subnet-public", "subnet-private")


@dataclass(frozen=True)
class Op:
    name: str
    params: type[Params]
    gesture: Gesture
    args: Callable[[Any, Tags], list[str]]  # everything after `aws`, before the common flags
    # create: the palette kind it makes and the node kinds it may be dropped on.
    creates: str | None = None
    containers: tuple[str, ...] = ()
    # connect: the edge's source kind and target kinds. attribute: the node kinds it applies to.
    source: str | None = None
    targets: tuple[str, ...] = ()
    result_id: str | None = None  # path to the new resource's id in the JSON output

    def argv(self, params: Params, tags: Tags) -> list[str]:
        return ["aws", *self.args(params, tags), "--profile", PROFILE, "--output", "json"]

    def describe(self) -> dict[str, Any]:
        """What the web app needs to offer this op: which gesture, from what, onto what."""
        out: dict[str, Any] = {"name": self.name, "gesture": self.gesture}
        if self.creates:
            out |= {"creates": self.creates, "containers": list(self.containers)}
        if self.source:
            out["source"] = self.source
        if self.targets:
            out["targets"] = list(self.targets)
        return out

    def palette_kind(self) -> str:
        """The palette entry an op belongs to: what it creates, connects from or modifies."""
        kind = self.creates or self.source or self.targets[0]
        return "subnet" if kind in SUBNET_KINDS else kind


def tag_spec(resource_type: str, name: str, tags: Tags) -> list[str]:
    pairs = [("Name", name), *sorted(tags.items())]
    tag_list = ",".join(f"{{Key={k},Value={v}}}" for k, v in pairs)
    return ["--tag-specifications", f"ResourceType={resource_type},Tags=[{tag_list}]"]


def display(argv: list[str]) -> str:
    """The command as the learner sees it; shell-quoted so pasting it runs the same argv."""
    return shlex.join(argv)


_OPS = [
    Op("create-vpc", CreateVpc, "create",
       lambda p, t: ["ec2", "create-vpc", "--cidr-block", p.cidr, *tag_spec("vpc", p.name, t)],
       creates="vpc", containers=("region",), result_id="Vpc.VpcId"),
    Op("create-subnet", CreateSubnet, "create",
       lambda p, t: ["ec2", "create-subnet", "--vpc-id", p.vpc_id, "--cidr-block", p.cidr,
                     "--availability-zone", p.az, *tag_spec("subnet", p.name, t)],
       creates="subnet", containers=("vpc", "az"), result_id="Subnet.SubnetId"),
    Op("create-internet-gateway", CreateInternetGateway, "create",
       lambda p, t: ["ec2", "create-internet-gateway", *tag_spec("internet-gateway", p.name, t)],
       creates="igw", containers=("region",), result_id="InternetGateway.InternetGatewayId"),
    Op("attach-internet-gateway", AttachInternetGateway, "connect",
       lambda p, t: ["ec2", "attach-internet-gateway", "--internet-gateway-id", p.igw_id, "--vpc-id", p.vpc_id],
       source="igw", targets=("vpc",)),
    Op("allocate-address", AllocateAddress, "create",
       lambda p, t: ["ec2", "allocate-address", "--domain", "vpc", *tag_spec("elastic-ip", p.name, t)],
       creates="elastic-ip", containers=("region",), result_id="AllocationId"),
    Op("create-nat-gateway", CreateNatGateway, "create",
       lambda p, t: ["ec2", "create-nat-gateway", "--subnet-id", p.subnet_id, "--allocation-id", p.allocation_id,
                     *tag_spec("natgateway", p.name, t)],
       creates="nat", containers=("subnet-public",), result_id="NatGateway.NatGatewayId"),
    Op("create-route-table", CreateRouteTable, "create",
       lambda p, t: ["ec2", "create-route-table", "--vpc-id", p.vpc_id, *tag_spec("route-table", p.name, t)],
       creates="route-table", containers=("vpc",), result_id="RouteTable.RouteTableId"),
    Op("create-route", CreateRoute, "connect",
       lambda p, t: ["ec2", "create-route", "--route-table-id", p.route_table_id, "--destination-cidr-block", p.destination,
                     "--nat-gateway-id" if p.target_id.startswith("nat-") else "--gateway-id", p.target_id],
       source="route-table", targets=("igw", "nat")),
    Op("associate-route-table", AssociateRouteTable, "connect",
       lambda p, t: ["ec2", "associate-route-table", "--route-table-id", p.route_table_id, "--subnet-id", p.subnet_id],
       source="route-table", targets=SUBNET_KINDS),
    Op("modify-vpc-attribute", ModifyVpcAttribute, "attribute",
       lambda p, t: ["ec2", "modify-vpc-attribute", "--vpc-id", p.vpc_id, "--enable-dns-hostnames", json.dumps({"Value": True})],
       targets=("vpc",)),
    Op("modify-subnet-attribute", ModifySubnetAttribute, "attribute",
       lambda p, t: ["ec2", "modify-subnet-attribute", "--subnet-id", p.subnet_id, "--map-public-ip-on-launch"],
       targets=SUBNET_KINDS),
]
OPS: dict[str, Op] = {op.name: op for op in _OPS}


def catalog(palette: list[str]) -> list[dict[str, Any]]:
    """Ops a lab offers: those whose palette kind the lab lists (F4.1)."""
    return [op.describe() for op in _OPS if op.palette_kind() in palette]


def result_id(op: Op, stdout: str) -> str | None:
    """The id of the resource a create op made, read from the CLI's JSON output."""
    if not op.result_id:
        return None
    try:
        value: Any = json.loads(stdout)
    except ValueError:
        return None
    for key in op.result_id.split("."):
        value = value.get(key) if isinstance(value, dict) else None
    return value if isinstance(value, str) else None


def expectation(op: Op, params: Params, stdout: str, version: int) -> dict[str, Any]:
    """What the next graph must show for this op to count as seen by the collector (F4.5).
    `version` is the graph's version before the run: when the output names no id, any newer graph
    that differs is the best evidence left, which still waits for the collector."""
    match params:
        case AttachInternetGateway():
            return {"node": params.igw_id, "prop": "attachedVpc", "value": params.vpc_id}
        case CreateRoute():
            return {"edge": f"route:{params.route_table_id}->{params.target_id}:{params.destination}"}
        case AssociateRouteTable():
            return {"edge": f"association:{params.route_table_id}->{params.subnet_id}"}
        case ModifyVpcAttribute():
            return {"node": params.vpc_id, "prop": "enableDnsHostnames", "value": True}
        case ModifySubnetAttribute():
            return {"node": params.subnet_id, "prop": "mapPublicIpOnLaunch", "value": True}
    new_id = result_id(op, stdout)
    return {"node": new_id} if new_id else {"after": version}
