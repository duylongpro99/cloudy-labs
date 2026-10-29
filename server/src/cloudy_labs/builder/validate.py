"""Check a builder op against the current resource graph before it runs (PRD F4.3).

Pure: reads only the graph the collector produced (props `cidr`, `attachedVpc`, `state`,
edges `route`, `association`, `attached`) and the region's AZs, never the emulator. Messages
are written for the learner: what is wrong and why, not just "invalid". M5's chat reuses this.
"""

import re
from dataclasses import dataclass
from ipaddress import IPv4Network, ip_network

from ..graph.schema import Node, ResourceGraph
from .ops import (
    OPS, SUBNET_KINDS, AttachInternetGateway, CreateNatGateway, CreateRoute, CreateSubnet, CreateVpc,
    AssociateRouteTable, ModifySubnetAttribute, ModifyVpcAttribute, Named, Params, CreateRouteTable,
)

MIN_PREFIX, MAX_PREFIX = 16, 28  # AWS's limits for VPC and subnet blocks
# Name tags go into the CLI's shorthand syntax, where commas, brackets and spaces have meaning.
NAME = re.compile(r"[A-Za-z0-9._-]{1,64}")  # used with fullmatch: `$` would let a trailing newline in


@dataclass(frozen=True)
class Problem:
    field: str  # the param it is about, camelCase like the browser's form; "" for the op as a whole
    message: str


class _Graph:
    def __init__(self, graph: ResourceGraph):
        self.nodes = {n.id: n for n in graph.nodes}
        self.parent = {c.child: c.parent for c in graph.contains}
        self.edges = graph.edges

    def get(self, node_id: str) -> Node | None:
        return self.nodes.get(node_id)

    def vpc_of(self, node_id: str) -> str | None:
        cur: str | None = node_id
        while cur is not None:
            node = self.nodes.get(cur)
            if node and node.kind == "vpc":
                return node.id
            cur = self.parent.get(cur)
        return None

    def subnets_in(self, vpc_id: str) -> list[Node]:
        return [n for n in self.nodes.values() if n.kind in SUBNET_KINDS and self.vpc_of(n.id) == vpc_id]

    def edges_from(self, kind: str, src: str) -> list:
        return [e for e in self.edges if e.kind == kind and e.from_ == src]


def _name(node: Node) -> str:
    return node.id if node.label == node.id else f"{node.label} ({node.id})"


def _cidr(field: str, value: str, problems: list[Problem], *, limits: bool = True) -> IPv4Network | None:
    """Parse a CIDR block, explaining each way it can be wrong. None when it is unusable."""
    if not value.strip():
        problems.append(Problem(field, "enter a CIDR block, for example 10.0.1.0/24"))
        return None
    if "/" not in value:
        problems.append(Problem(field, f"{value} has no prefix length; write it as a block such as {value}/24"))
        return None
    try:
        loose = ip_network(value, strict=False)
    except ValueError:
        problems.append(Problem(field, f"{value} is not an IPv4 CIDR block; use the form 10.0.1.0/24"))
        return None
    if loose.version != 4:
        problems.append(Problem(field, f"{value} is IPv6; this lab uses IPv4 blocks such as 10.0.1.0/24"))
        return None
    if value.rsplit("/", 1)[1] != str(loose.prefixlen):
        problems.append(Problem(field, f"write the prefix length as a number, for example {loose.network_address}/{loose.prefixlen}"))
        return None
    if str(loose) != value:
        problems.append(Problem(field, f"{value} has host bits set: a block must start at its network address, "
                                       f"which for /{loose.prefixlen} is {loose}"))
        return None
    if limits and not MIN_PREFIX <= loose.prefixlen <= MAX_PREFIX:
        problems.append(Problem(field, f"/{loose.prefixlen} is outside what AWS allows: VPC and subnet blocks "
                                       f"must be between /{MIN_PREFIX} (65,536 addresses) and /{MAX_PREFIX} (16 addresses)"))
        return None
    return loose  # type: ignore[return-value]


def _node(g: _Graph, field: str, node_id: str, kinds: tuple[str, ...], what: str, problems: list[Problem]) -> Node | None:
    """The node `node_id` must exist and be one of `kinds`."""
    if not node_id:
        problems.append(Problem(field, f"choose a {what}"))
        return None
    node = g.get(node_id)
    if node is None:
        problems.append(Problem(field, f"{node_id} is not in the scene; it may have been deleted or not collected yet"))
        return None
    if node.kind not in kinds:
        problems.append(Problem(field, f"{_name(node)} is a {node.kind}, but this needs a {what}"))
        return None
    return node


def validate(op_name: str, params: Params, graph: ResourceGraph, azs: list[str]) -> list[Problem]:
    """Problems with running `op_name` with `params` now. Empty means it may run."""
    op = OPS[op_name]
    if not isinstance(params, op.params):
        raise TypeError(f"{op_name} takes {op.params.__name__}, not {type(params).__name__}")
    g = _Graph(graph)
    problems: list[Problem] = []

    if isinstance(params, Named) and not NAME.fullmatch(params.name):
        problems.append(Problem("name", "give it a Name tag of 1–64 letters, digits, dots, dashes or underscores "
                                        "(for example lab06-vpc), so you can tell resources apart"))

    match params:
        case CreateVpc():
            _cidr("cidr", params.cidr, problems)

        case CreateSubnet():
            vpc = _node(g, "vpcId", params.vpc_id, ("vpc",), "VPC (a subnet always lives inside one VPC)", problems)
            block = _cidr("cidr", params.cidr, problems)
            if not azs:  # fail closed: an unchecked AZ would reach the aws argv as free text
                problems.append(Problem("az", "could not read this region's Availability Zones from the emulator; "
                                              "check that it is up (`labctl up`) and try again in a moment"))
            elif params.az not in azs:
                problems.append(Problem("az", f"{params.az or '(none)'} is not an Availability Zone of this region; "
                                              f"choose one of {', '.join(azs)}"))
            if vpc and block:
                _subnet_fits(g, vpc, block, problems)

        case AttachInternetGateway():
            igw = _node(g, "igwId", params.igw_id, ("igw",), "Internet Gateway", problems)
            vpc = _node(g, "vpcId", params.vpc_id, ("vpc",), "VPC", problems)
            if igw and igw.props.get("attachedVpc"):
                problems.append(Problem("igwId", f"{_name(igw)} is already attached to {igw.props['attachedVpc']}; "
                                                 "an Internet Gateway serves one VPC at a time"))
            if vpc:
                other = next((n for n in g.nodes.values() if n.kind == "igw" and n.props.get("attachedVpc") == vpc.id), None)
                if other and (igw is None or other.id != igw.id):
                    problems.append(Problem("vpcId", f"{_name(vpc)} already has {_name(other)}; "
                                                     "a VPC can have only one Internet Gateway"))

        case CreateNatGateway():
            subnet = _node(g, "subnetId", params.subnet_id, SUBNET_KINDS, "subnet", problems)
            if subnet and subnet.kind == "subnet-private":
                problems.append(Problem("subnetId", f"{_name(subnet)} is private: its route table has no route to an "
                                                    "Internet Gateway. A NAT Gateway forwards private traffic to the "
                                                    "Internet, so it must sit in a public subnet"))
            if not params.allocation_id and not any(n.kind == "elastic-ip" for n in g.nodes.values()):
                problems.append(Problem("allocationId", "a NAT Gateway needs an Elastic IP; allocate one first"))
            else:
                eip = _node(g, "allocationId", params.allocation_id, ("elastic-ip",), "Elastic IP", problems)
                if eip and (used := g.edges_from("attached", eip.id)):
                    problems.append(Problem("allocationId", f"{_name(eip)} is already in use by {used[0].to}; "
                                                            "allocate another Elastic IP"))

        case CreateRouteTable():
            _node(g, "vpcId", params.vpc_id, ("vpc",), "VPC", problems)

        case CreateRoute():
            table = _node(g, "routeTableId", params.route_table_id, ("route-table",), "route table", problems)
            target = _node(g, "targetId", params.target_id, ("igw", "nat"), "Internet Gateway or NAT Gateway", problems)
            dest = _cidr("destination", params.destination, problems, limits=False)
            if table and target:
                table_vpc = g.vpc_of(table.id)
                target_vpc = target.props.get("attachedVpc") if target.kind == "igw" else g.vpc_of(target.id)
                if target.kind == "igw" and not target_vpc:
                    problems.append(Problem("targetId", f"{_name(target)} is not attached to a VPC yet; attach it to "
                                                        f"{table_vpc} before routing to it"))
                elif target_vpc != table_vpc:
                    problems.append(Problem("targetId", f"{_name(target)} belongs to {target_vpc}, but {_name(table)} "
                                                        f"belongs to {table_vpc}; a route can only use gateways of its own VPC"))
                if target.kind == "nat" and target.props.get("state") != "available":
                    problems.append(Problem("targetId", f"{_name(target)} is {target.props.get('state', 'not ready')}; "
                                                        "wait until it is available before routing to it"))
            if table and dest:
                if any(e.label == str(dest) for e in g.edges_from("route", table.id)):
                    problems.append(Problem("destination", f"{_name(table)} already has a route for {dest}; "
                                                           "each destination can appear once per route table"))

        case AssociateRouteTable():
            table = _node(g, "routeTableId", params.route_table_id, ("route-table",), "route table", problems)
            subnet = _node(g, "subnetId", params.subnet_id, SUBNET_KINDS, "subnet", problems)
            if table and subnet:
                if g.vpc_of(table.id) != g.vpc_of(subnet.id):
                    problems.append(Problem("subnetId", f"{_name(subnet)} is in {g.vpc_of(subnet.id)} but {_name(table)} "
                                                        f"is in {g.vpc_of(table.id)}; a route table serves subnets of its own VPC"))
                current = next((e.from_ for e in g.edges if e.kind == "association" and e.to == subnet.id), None)
                if current:
                    problems.append(Problem("subnetId", f"{_name(subnet)} already uses route table {current}; "
                                                        "a subnet is associated with one route table at a time"))

        case ModifyVpcAttribute():
            _node(g, "vpcId", params.vpc_id, ("vpc",), "VPC", problems)

        case ModifySubnetAttribute():
            _node(g, "subnetId", params.subnet_id, SUBNET_KINDS, "subnet", problems)

    return problems


def _subnet_fits(g: _Graph, vpc: Node, block: IPv4Network, problems: list[Problem]) -> None:
    vpc_block = ip_network(vpc.props["cidr"]) if vpc.props.get("cidr") else None
    if vpc_block and not block.subnet_of(vpc_block):  # type: ignore[arg-type]
        problems.append(Problem("cidr", f"{block} is outside {_name(vpc)}'s block {vpc_block}; "
                                        "a subnet takes its addresses from its VPC's range"))
        return
    for other in g.subnets_in(vpc.id):
        if other.props.get("cidr") and block.overlaps(ip_network(other.props["cidr"])):
            problems.append(Problem("cidr", f"{block} overlaps subnet {_name(other)} ({other.props['cidr']}); "
                                            "subnets of one VPC must not share addresses"))
