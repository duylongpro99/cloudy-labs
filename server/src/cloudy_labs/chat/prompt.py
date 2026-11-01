"""The system prompt for the chat (PRD F5.2): the lab, its builder ops, the current graph.

Pure: no I/O. The model never writes a command line. It picks ops from the lab's catalogue and
fills their params; the server builds the argv and validates it with the builder's own code.
"""

import json
from datetime import date
from typing import Any

from ..builder.catalog import BuilderOp, all_ops
from ..builder.ec2_choices import Choices
from ..graph.schema import ResourceGraph
from ..labs.schema import Lab
from ..registry import CHAT_PROPS_DENY, Registry, default_registry

# Where the emulator differs from AWS in a way the chat must know (docs/emulator-differences.md).
EMULATOR_NAME = {"floci": "Floci", "moto": "moto"}
INSTANCE_LIMITS = [
    "An instance reports running before its UserData has finished; a web server may need a minute.",
    "Public IPs are 127.0.0.1 with host ports; the scene shows them.",
]
HIDDEN_KINDS = ("account", "region", "global", "az")

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


def _iso(value: Any) -> str:
    """Props read from botocore may hold a datetime (a secret's lastChanged); write it as /ws does."""
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=_iso)


def _palette_ops(palette: list[str], registry: Registry) -> list[BuilderOp]:
    return [op for op in all_ops(registry).values() if op.palette_kind() in palette]


def emulator_limits(lab: Lab, registry: Registry | None = None) -> list[str]:
    """What the model must know about where commands run, built from the lab and its ops."""
    ops = _palette_ops(list(lab.builder.palette), registry or default_registry())
    services = sorted({op.service for op in ops})
    gestures = sorted({op.gesture for op in ops})
    lines = [
        f"Everything runs on a local AWS emulator ({EMULATOR_NAME.get(lab.emulator, lab.emulator)}) with the CLI "
        "profile `lab`; never ask for or mention real AWS credentials, accounts or the AWS console.",
        f"Only the ops listed below exist here (services: {', '.join(services) or 'none'}; kinds of action: "
        f"{', '.join(gestures) or 'none'}). Any other service or action is not available in this lab.",
    ]
    if "instance" in lab.builder.palette:
        lines += INSTANCE_LIMITS
    return lines


def _param(field: Any) -> str:
    """A param's type for the model; every value is still sent as a string."""
    text = field.type
    if field.choices:
        text += " (one of " + " | ".join(field.choices) + ")"
    if field.type == "list":
        text += " (values separated by commas)"
    elif field.type == "json":
        text += " (JSON text)"
    if field.ref:
        text += f" (the {'name' if field.ref_by == 'label' else 'id'} of a {field.ref})"
    return text + (", required" if field.required else ", optional: \"\" for none")


def ops_section(palette: list[str], registry: Registry | None = None) -> list[dict[str, Any]]:
    out = []
    for op in _palette_ops(palette, registry or default_registry()):
        params = {f.name: _param(f) for f in op.fields() if not f.advanced and f.type != "blob"}
        out.append({"op": op.name, "params": params, "does": op.spec.note or op.spec.title,
                    "builderGesture": op.gesture})
    return out


def chat_props(kind: str, registry: Registry) -> list[str]:
    """The props of `kind` the model may see: its `chat_props`, never one that may hold a secret."""
    t = registry.get(kind)
    return [p for p in (t.chat_props if t else []) if not any(d in p.lower() for d in CHAT_PROPS_DENY)]


def compact_graph(graph: ResourceGraph, registry: Registry | None = None) -> dict[str, Any]:
    """Only what the model needs to pick ids and what validate checks: AZ trays are folded into
    the nodes' `az` prop and parents skip them, so a subnet's parent is its VPC. Each kind shows
    only its registry `chat_props`."""
    registry = registry or default_registry()
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
        entry |= {k: n.props[k] for k in chat_props(n.kind, registry) if k in n.props}
        nodes.append(entry)
    edges = [{"kind": e.kind, "from": e.from_, "to": e.to, **({"label": e.label} if e.label else {})} for e in graph.edges]
    return {"nodes": nodes, "edges": edges}


def system_prompt(lab: Lab, graph: ResourceGraph, azs: list[str], choices: Choices) -> str:
    builder = lab.builder
    tasks = "\n".join(f"- {t.id}: {t.text}" for t in lab.tasks)
    limits = "\n".join(f"- {line}" for line in emulator_limits(lab))
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
