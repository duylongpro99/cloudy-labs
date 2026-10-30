"""The system prompt for the chat (PRD F5.2): the lab, its builder ops, the current graph.

Pure: no I/O. The model never writes a command line. It picks ops from the lab's catalogue and
fills their params; the server builds the argv and validates it with the builder's own code.
"""

import json
from typing import Any

from ..builder.ec2_choices import Choices
from ..builder.ops import OPS, catalog
from ..graph.schema import ResourceGraph
from ..labs.schema import Lab

# What each op does and how to fill its params, for the model. Field names are the camelCase
# aliases the server accepts; every value is a string.
OP_NOTES: dict[str, str] = {
    "create-vpc": "Create a VPC. cidr: an IPv4 block between /16 and /28, e.g. 10.0.0.0/16.",
    "create-subnet": "Create a subnet in a VPC. vpcId: the VPC id; cidr: a block inside the VPC's cidr that overlaps "
                     "no other subnet of that VPC; az: one of the Availability Zones listed below.",
    "create-internet-gateway": "Create an Internet Gateway (not attached yet).",
    "attach-internet-gateway": "Attach an Internet Gateway to a VPC. A VPC has at most one, and an IGW serves one VPC.",
    "allocate-address": "Allocate an Elastic IP. Its id (eipalloc-...) is the allocationId of a NAT Gateway.",
    "create-nat-gateway": "Create a NAT Gateway in a public subnet. subnetId: a subnet-public; allocationId: an "
                          "unused Elastic IP id.",
    "create-route-table": "Create a route table in a VPC.",
    "create-route": "Add a route to a route table. destination: a CIDR such as 0.0.0.0/0; targetId: an Internet "
                    "Gateway attached to the table's VPC (igw-...) or an available NAT Gateway (nat-...) of that VPC.",
    "associate-route-table": "Associate a route table with a subnet of the same VPC that has no route table yet. "
                             "A subnet is public when its route table routes 0.0.0.0/0 to an Internet Gateway.",
    "modify-vpc-attribute": "Turn on DNS hostnames for a VPC.",
    "modify-subnet-attribute": "Make a subnet give instances a public IP on launch.",
    "create-security-group": "Create a security group in a VPC. name: not starting with sg-, unique in the VPC; "
                             "description: plain ASCII text.",
    "authorize-security-group-ingress": "Add one inbound rule. protocol: tcp, udp, icmp or -1 (all traffic); port: "
                                        "one port number (any value for icmp and -1); cidr: the source block. Never "
                                        "open port 22 or all traffic to 0.0.0.0/0; use one address with /32.",
    "create-key-pair": "Create a key pair. name is the key name used by run-instances keyName.",
    "run-instances": "Launch one instance. subnetId; imageId and instanceType from the lists below; "
                     "securityGroupId: a group in the subnet's VPC; keyName: a key pair's name, or empty for none; "
                     "userData: a script, or empty for none.",
    "modify-instance-attribute": "Attach one more security group to an instance; the groups it has are kept.",
}

# Where the emulator differs from AWS in a way the chat must know (docs/emulator-differences.md).
EMULATOR_LIMITS = [
    "Everything runs on a local AWS emulator (Floci) with the CLI profile `lab`; never ask for or mention real AWS "
    "credentials, accounts or the AWS console.",
    "Only the ops listed below exist here. Other services (S3, IAM, RDS, Lambda, ...) and other EC2 actions "
    "(delete, stop, terminate, VPC peering, ...) are not available in this lab.",
    "An instance reports running before its UserData has finished; a web server may need a minute.",
    "Public IPs are 127.0.0.1 with host ports; the scene shows them.",
]

PROPS = ("cidr", "az", "attachedVpc", "state", "groupName", "ingress", "mapPublicIpOnLaunch",
         "enableDnsHostnames", "isDefault", "main", "keyName")
HIDDEN_KINDS = ("region", "az")

FORMAT = """\
Answer with exactly one JSON object and nothing else:
{"reply": "<short answer for the learner>", "refusal": null, "steps": [{"op": "<op name>", "params": {...}, "explanation": "<why this step>"}]}
- steps run in order. Give every param of the op, as strings. Use ids exactly as they appear in the graph.
- A step may use the id of a resource that an earlier create step in the same answer makes: write {"ref": n} as \
the param value, where n is that step's number counting from 1. Never invent ids.
- Skip work the graph shows is already done, and do not repeat a resource that already exists.
- When the request needs something no op can do, or is not about this lab, set "refusal" to a short reason \
(outside this lab's scope, or not supported by the emulator), "steps" to [], and suggest what the learner can do here.
- Write "reply", "refusal" and every "explanation" in the learner's language."""


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _params(op_name: str) -> dict[str, str]:
    op = OPS[op_name]
    fields = [f.alias or name for name, f in op.params.model_fields.items()]
    return {f: "string" for f in fields if f not in op.server_fields}


def ops_section(palette: list[str]) -> list[dict[str, Any]]:
    out = []
    for spec in catalog(palette):
        name = spec["name"]
        out.append({"op": name, "params": _params(name), "does": OP_NOTES.get(name, ""),
                    "builderGesture": spec["gesture"]})
    return out


def compact_graph(graph: ResourceGraph) -> dict[str, Any]:
    """Only what the model needs to pick ids and what validate checks: AZ trays are folded into
    the nodes' `az` prop and parents skip them, so a subnet's parent is its VPC."""
    kinds = {n.id: n.kind for n in graph.nodes}
    parent = {c.child: c.parent for c in graph.contains}

    def visible_parent(node_id: str) -> str | None:
        cur = parent.get(node_id)
        while cur is not None and kinds.get(cur) in HIDDEN_KINDS:
            cur = parent.get(cur)
        return cur

    nodes = []
    for n in graph.nodes:
        if n.kind in HIDDEN_KINDS:
            continue
        entry: dict[str, Any] = {"id": n.id, "kind": n.kind}
        if n.label != n.id:
            entry["name"] = n.label
        if p := visible_parent(n.id):
            entry["in"] = p
        entry |= {k: n.props[k] for k in PROPS if k in n.props}
        nodes.append(entry)
    edges = [{"kind": e.kind, "from": e.from_, "to": e.to, **({"label": e.label} if e.label else {})} for e in graph.edges]
    return {"nodes": nodes, "edges": edges}


def system_prompt(lab: Lab, graph: ResourceGraph, azs: list[str], choices: Choices) -> str:
    builder = lab.builder
    tasks = "\n".join(f"- {t.id}: {t.text}" for t in lab.tasks)
    limits = "\n".join(f"- {line}" for line in EMULATOR_LIMITS)
    sections = [
        f"You are the teaching assistant of the hands-on lab \"{lab.title}\" ({lab.id}). The learner asks in their "
        "own words; you answer by choosing steps from the builder ops below. The server turns each step into an "
        "aws CLI command, checks it against the current resources and shows it; the learner presses Run. "
        "You never write a command line yourself.",
        f"Emulator rules:\n{limits}",
        f"Lab tasks:\n{tasks}",
        f"Builder ops of this lab (the only steps you may use):\n{_dumps(ops_section(list(builder.palette)))}",
        f"Availability Zones: {_dumps(azs)}",
    ]
    if "instance" in builder.palette:
        sections.append(f"Images (imageId): {_dumps(choices['images'])}\nInstance types: {_dumps(choices['instanceTypes'])}")
        if builder.user_data:
            sections.append(f"The lab's suggested UserData for run-instances:\n{_dumps(builder.user_data)}")
    sections += [
        f"Current resources (graph version {graph.version}; `in` is the parent):\n{_dumps(compact_graph(graph))}",
        FORMAT,
    ]
    return "\n\n".join(sections)
