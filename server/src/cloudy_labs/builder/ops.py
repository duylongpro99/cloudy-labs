"""The builder's fixed catalogue of operations (PRD F4.3, F4.4).

The browser sends a typed operation, never a command line: `{op, params}`. Each op turns its
params into one `aws` argv, and the command shown to the learner is printed from that same
argv, so what they read is exactly what runs. Pure: no I/O, no graph.
"""

import json
import re
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


class CreateSecurityGroup(Named):
    vpc_id: str
    description: str


class AuthorizeSecurityGroupIngress(Params):
    group_id: str
    protocol: str  # tcp, udp, icmp or -1 (all traffic)
    port: str  # one port; ignored for icmp and -1
    cidr: str


class CreateKeyPair(Named):
    pass


class RunInstances(Named):
    subnet_id: str
    image_id: str
    instance_type: str
    security_group_id: str
    key_name: str  # empty: no key pair
    user_data: str  # empty: none


class ModifyInstanceAttribute(Params):
    instance_id: str
    group_id: str  # the security group to add
    # `--groups` replaces the whole list, so the command must name the groups already attached.
    # The server fills this from the graph; the browser may not send it (SERVER_FIELDS).
    current_groups: tuple[str, ...] = ()


Tags = dict[str, str]
SUBNET_KINDS = ("subnet-public", "subnet-private")
PORTLESS = ("icmp", "-1")  # protocols whose rules cover every port


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
    result_id: str | None = None  # path to the new resource's id in the JSON output; digits index lists
    server_fields: tuple[str, ...] = ()  # params the server fills in; refused from the browser

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


def _port(value: str) -> int | str:
    """The port as JSON wants it. Left as text when it is not a number: validate explains why,
    and a command with problems never runs."""
    return int(value) if re.fullmatch(r"[0-9]{1,5}", value.strip()) else value


def ip_permissions(p: AuthorizeSecurityGroupIngress) -> str:
    """One inbound rule as `--ip-permissions` JSON, which says exactly what the shorthand
    `--protocol/--port/--cidr` flags leave to the CLI to guess."""
    rule: dict[str, Any] = {"IpProtocol": p.protocol}
    if p.protocol == "icmp":
        rule |= {"FromPort": -1, "ToPort": -1}  # every ICMP type and code
    elif p.protocol != "-1":
        rule |= {"FromPort": _port(p.port), "ToPort": _port(p.port)}
    rule["IpRanges"] = [{"CidrIp": p.cidr}]
    return json.dumps([rule])


def _run_instances(p: RunInstances, t: Tags) -> list[str]:
    argv = ["ec2", "run-instances", "--image-id", p.image_id, "--instance-type", p.instance_type,
            "--subnet-id", p.subnet_id, "--security-group-ids", p.security_group_id, "--count", "1"]
    if p.key_name:
        argv += ["--key-name", p.key_name]
    if p.user_data:
        argv += ["--user-data", p.user_data]
    return argv + tag_spec("instance", p.name, t)


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
    Op("create-security-group", CreateSecurityGroup, "create",
       lambda p, t: ["ec2", "create-security-group", "--group-name", p.name, "--description", p.description,
                     "--vpc-id", p.vpc_id, *tag_spec("security-group", p.name, t)],
       creates="security-group", containers=("vpc",), result_id="GroupId"),
    Op("authorize-security-group-ingress", AuthorizeSecurityGroupIngress, "attribute",
       lambda p, t: ["ec2", "authorize-security-group-ingress", "--group-id", p.group_id, "--ip-permissions", ip_permissions(p)],
       targets=("security-group",)),
    # No --query: the learner needs KeyMaterial, the private key, which AWS shows only once.
    Op("create-key-pair", CreateKeyPair, "create",
       lambda p, t: ["ec2", "create-key-pair", "--key-name", p.name, *tag_spec("key-pair", p.name, t)],
       creates="key-pair", containers=("region",), result_id="KeyPairId"),
    Op("run-instances", RunInstances, "create", _run_instances,
       creates="instance", containers=SUBNET_KINDS, result_id="Instances.0.InstanceId"),
    Op("modify-instance-attribute", ModifyInstanceAttribute, "connect",
       lambda p, t: ["ec2", "modify-instance-attribute", "--instance-id", p.instance_id,
                     "--groups", *p.current_groups, p.group_id],
       source="security-group", targets=("instance",), server_fields=("currentGroups",)),
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
        if isinstance(value, list) and key.isdigit():
            value = value[int(key)] if int(key) < len(value) else None
        else:
            value = value.get(key) if isinstance(value, dict) else None
    return value if isinstance(value, str) else None


def ingress_rule(p: AuthorizeSecurityGroupIngress) -> dict[str, Any]:
    """The rule as the collector writes it into a security group's `ingress`, with `source` for
    one of its `sources`. Rules for all traffic have no ports."""
    [rule] = json.loads(ip_permissions(p))
    ports = {"from": rule["FromPort"], "to": rule["ToPort"]} if "FromPort" in rule else {}
    return {"protocol": p.protocol, **ports, "source": p.cidr}


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
        case AuthorizeSecurityGroupIngress():
            return {"node": params.group_id, "prop": "ingress", "includes": ingress_rule(params)}
        case ModifyInstanceAttribute():
            return {"edge": f"attached:{params.group_id}->{params.instance_id}"}
    new_id = result_id(op, stdout)
    return {"node": new_id} if new_id else {"after": version}


def practice_expectation(op: Op, params: Params) -> dict[str, Any]:
    """What the graph must show once the learner has run this command themselves (F4.7): nothing
    ran here, so there is no id to wait for, only a new resource of the kind with that name."""
    if op.creates and isinstance(params, Named):
        return {"kind": op.creates, "label": params.name}  # "subnet" matches either subnet kind
    return expectation(op, params, "", 0)
