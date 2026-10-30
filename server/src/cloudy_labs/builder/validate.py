"""Check a builder op against the current resource graph before it runs (PRD F4.3).

Pure: reads only the graph the collector produced (props `cidr`, `attachedVpc`, `state`,
`groupName`, `ingress`, edges `route`, `association`, `attached`), the region's AZs and the
AMIs and instance types on offer, never the emulator. Messages
are written for the learner: what is wrong and why, not just "invalid". M5's chat reuses this.
"""

import re
from dataclasses import dataclass
from ipaddress import IPv4Network, ip_network

from ..graph.schema import Node, ResourceGraph
from ..labs.schema import USER_DATA_MAX
from .ec2_choices import Choices, choices as host_choices
from .ops import (
    OPS, PORTLESS, SUBNET_KINDS, AttachInternetGateway, AuthorizeSecurityGroupIngress, CreateKeyPair, CreateNatGateway,
    CreateRoute, CreateSecurityGroup, CreateSubnet, CreateVpc, AssociateRouteTable, ModifyInstanceAttribute,
    ModifySubnetAttribute, ModifyVpcAttribute, Named, Params, CreateRouteTable, RunInstances,
)

MIN_PREFIX, MAX_PREFIX = 16, 28  # AWS's limits for VPC and subnet blocks
# Name tags go into the CLI's shorthand syntax, where commas, brackets and spaces have meaning.
NAME = re.compile(r"[A-Za-z0-9._-]{1,64}")  # used with fullmatch: `$` would let a trailing newline in
PROTOCOLS = ("tcp", "udp", "icmp", "-1")
SSH_PORT, WORLD = 22, "0.0.0.0/0"
DESCRIPTION_MAX = 255
# The characters AWS accepts in a security group description (VPC groups).
DESCRIPTION = re.compile(rf"[A-Za-z0-9 ._\-:/()#,@\[\]+=&;{{}}!$*]{{1,{DESCRIPTION_MAX}}}")
PORT = re.compile(r"[0-9]{1,5}")  # str.isdigit() also takes digits like ², which int() refuses
# The aws CLI replaces a value with this prefix by the contents of that file, whatever the parameter.
FILE_PREFIXES = ("file://", "fileb://")
MAX_GROUPS_PER_INSTANCE = 5  # AWS's default quota of security groups per network interface
GONE_INSTANCE_STATES = ("terminated", "shutting-down")


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


def validate(op_name: str, params: Params, graph: ResourceGraph, azs: list[str],
             choices: Choices | None = None) -> list[Problem]:
    """Problems with running `op_name` with `params` now. Empty means it may run.
    `choices`: the AMIs and instance types on offer; this host's when None."""
    op = OPS[op_name]
    if not isinstance(params, op.params):
        raise TypeError(f"{op_name} takes {op.params.__name__}, not {type(params).__name__}")
    g = _Graph(graph)
    problems: list[Problem] = []
    for field, value in params.model_dump(by_alias=True).items():
        if isinstance(value, str) and value.lstrip().lower().startswith(FILE_PREFIXES):
            problems.append(Problem(field, "a value may not start with file:// or fileb://: the aws CLI would read "
                                           "that file from this machine instead of using the text"))

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

        case CreateSecurityGroup():
            vpc = _node(g, "vpcId", params.vpc_id, ("vpc",), "VPC (a security group belongs to one VPC)", problems)
            if params.name.startswith("sg-"):
                problems.append(Problem("name", "a security group name may not start with sg-: AWS keeps that prefix "
                                                "for group ids, so the name could be mistaken for one"))
            elif vpc and (same := next((n for n in g.nodes.values() if n.kind == "security-group"
                                        and g.vpc_of(n.id) == vpc.id and n.props.get("groupName") == params.name), None)):
                problems.append(Problem("name", f"{_name(vpc)} already has a security group named {params.name} "
                                                f"({same.id}); names are unique within a VPC"))
            if not params.description.strip():
                problems.append(Problem("description", "describe what the group is for, for example Lab web server; "
                                                       "AWS requires a description"))
            elif not DESCRIPTION.fullmatch(params.description):
                problems.append(Problem("description", f"use up to {DESCRIPTION_MAX} letters, digits, spaces and ._-:/()#,@[]+=&;{{}}!$* "
                                                       "(no accents or emoji)"))

        case AuthorizeSecurityGroupIngress():
            _ingress(g, params, problems)

        case CreateKeyPair():
            if any(n.kind == "key-pair" and n.label == params.name for n in g.nodes.values()):
                problems.append(Problem("name", f"a key pair named {params.name} already exists; key pair names are "
                                                "unique in a region, so choose another"))

        case RunInstances():
            _run_instances(g, params, choices or host_choices(), problems)

        case ModifyInstanceAttribute():
            instance = _node(g, "instanceId", params.instance_id, ("instance",), "instance", problems)
            group = _node(g, "groupId", params.group_id, ("security-group",), "security group", problems)
            if instance and instance.props.get("state") in GONE_INSTANCE_STATES:
                problems.append(Problem("instanceId", f"{_name(instance)} is {instance.props['state']}; "
                                                      "it can no longer take security groups"))
            if instance and group:
                if g.vpc_of(group.id) != g.vpc_of(instance.id):
                    problems.append(Problem("groupId", f"{_name(group)} belongs to {g.vpc_of(group.id)} but {_name(instance)} "
                                                       f"runs in {g.vpc_of(instance.id)}; an instance can only use "
                                                       "security groups of its own VPC"))
                elif any(e.to == instance.id for e in g.edges_from("attached", group.id)):
                    problems.append(Problem("groupId", f"{_name(group)} is already attached to {_name(instance)}"))
                elif len(params.current_groups) >= MAX_GROUPS_PER_INSTANCE:
                    problems.append(Problem("groupId", f"{_name(instance)} already has {len(params.current_groups)} "
                                                       f"security groups, the most AWS allows by default; put the "
                                                       "rule in one of them instead"))

    return problems


def _ingress(g: _Graph, params: AuthorizeSecurityGroupIngress, problems: list[Problem]) -> None:
    group = _node(g, "groupId", params.group_id, ("security-group",), "security group", problems)
    protocol, port = params.protocol, None
    if protocol not in PROTOCOLS:
        problems.append(Problem("protocol", f"{protocol or '(none)'} is not a protocol a rule can use; choose tcp, udp, "
                                            "icmp, or -1 for all traffic"))
        return
    if protocol not in PORTLESS:
        if not PORT.fullmatch(params.port.strip()):
            problems.append(Problem("port", f"{params.port or '(none)'} is not a port number; "
                                            "enter one number, for example 80 for HTTP or 22 for SSH"))
        elif not 0 <= (port := int(params.port)) <= 65535:
            problems.append(Problem("port", f"{port} is not a port: ports go from 0 to 65535"))
            port = None
    block = _cidr("cidr", params.cidr, problems, limits=False)
    if block is None:
        return
    if str(block) == WORLD and (protocol == "-1" or (protocol == "tcp" and port == SSH_PORT)):
        what = "all traffic, including SSH on port 22," if protocol == "-1" else "SSH (port 22)"
        problems.append(Problem("cidr", f"this would open {what} to the whole Internet: bots scan for open port 22 "
                                        "and try passwords and stolen keys within minutes. Allow only your own address, "
                                        "for example 203.0.113.10/32 (look up your public IP and add /32)"))
    if group:
        portless = protocol in PORTLESS
        for rule in group.props.get("ingress") or []:
            same_ports = portless or (rule.get("from") == port and rule.get("to") == port)
            if rule.get("protocol") == protocol and same_ports and str(block) in rule.get("sources", []):
                problems.append(Problem("cidr", f"{_name(group)} already allows this ({protocol}"
                                                f"{'' if portless else f' {port}'} from {block})"))
                break


def _run_instances(g: _Graph, params: RunInstances, offer: Choices, problems: list[Problem]) -> None:
    subnet = _node(g, "subnetId", params.subnet_id, SUBNET_KINDS, "subnet", problems)
    group = _node(g, "securityGroupId", params.security_group_id, ("security-group",),
                  "security group (create one in this VPC first)", problems)
    if subnet and group and g.vpc_of(group.id) != g.vpc_of(subnet.id):
        problems.append(Problem("securityGroupId", f"{_name(group)} belongs to {g.vpc_of(group.id)} but {_name(subnet)} "
                                                   f"is in {g.vpc_of(subnet.id)}; an instance can only use security "
                                                   "groups of the VPC it runs in"))
    if params.key_name and not any(n.kind == "key-pair" and n.label == params.key_name for n in g.nodes.values()):
        problems.append(Problem("keyName", f"there is no key pair named {params.key_name}; create it first, "
                                           "or launch without one"))
    if params.image_id not in offer["images"]:
        problems.append(Problem("imageId", f"{params.image_id or '(none)'} is not offered here; choose "
                                           f"{', '.join(offer['images'])}, which matches this machine and starts fast"))
    if params.instance_type not in offer["instanceTypes"]:
        problems.append(Problem("instanceType", f"{params.instance_type or '(none)'} is not offered here; choose one of "
                                                f"{', '.join(offer['instanceTypes'])}"))
    if (size := len(params.user_data.encode())) > USER_DATA_MAX:
        problems.append(Problem("userData", f"UserData is {size:,} bytes; EC2 accepts at most {USER_DATA_MAX:,}"))


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
