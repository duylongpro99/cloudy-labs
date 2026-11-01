"""Every builder op of the registry, hand-written or generated, behind one interface.

An op with `argv` in the registry keeps its command, checks and expectation in ops.py and
validate.py; the registry adds its title, note and form. Any other op is generated from the
botocore shape of its API (shapes.py): a new kind with an op entry reaches the palette, the
form, the command and the chat with no code change.

Checks run in a fixed order: the sanitizer, then the shape (botocore's own validation), then
the scene (referenced nodes exist and are of the right kind, protected resources are refused,
the tray is of a kind the op may be dropped on), then the op's validator hook.
"""

from __future__ import annotations

import json

from dataclasses import dataclass, field
from typing import Any

import jmespath
from pydantic import ValidationError

from ..graph.schema import ResourceGraph
from ..registry import Registry, ResourceType, OpSpec, default_registry
from . import ops as legacy_ops
from . import shapes
from .ec2_choices import Choices
from .ops import SUBNET_KINDS, Op, Params, Tags, display
from .sanitize import Problem, sanitize
from .samples import SampleError, sample_zip
from .validate import VALIDATORS, attached_groups, validate as legacy_validate

# Server fields of hand-written ops and how the server fills them from the scene.
SERVER_FILL = {
    "currentGroups": lambda graph, p: {"current_groups": attached_groups(graph, p.instance_id)},
}


class OpError(Exception):
    """The request names no op, a field the server fills, or (hand-written ops) params of the wrong shape."""


@dataclass(frozen=True)
class BuilderOp:
    spec: OpSpec
    kind: str  # the registry kind that declares it
    service: str
    legacy: Op | None = None
    containers: tuple[str, ...] = ()
    order: int = 0

    @property
    def name(self) -> str:
        return self.spec.id

    @property
    def gesture(self) -> str:
        return self.legacy.gesture if self.legacy else self.spec.gesture

    @property
    def creates(self) -> str | None:
        if self.legacy:
            return self.legacy.creates
        return (self.spec.creates or self.kind) if self.spec.gesture == "create" else None

    @property
    def source(self) -> str | None:
        return self.legacy.source if self.legacy else self.spec.source

    @property
    def targets(self) -> tuple[str, ...]:
        if self.legacy:
            return self.legacy.targets
        if self.spec.targets or self.spec.gesture in ("create", "connect"):
            return tuple(self.spec.targets)
        return (self.kind,)

    @property
    def server_fields(self) -> tuple[str, ...]:
        return self.legacy.server_fields if self.legacy else tuple(self.spec.server_fields)

    @property
    def result_id(self) -> str | None:
        return self.legacy.result_id if self.legacy else self.spec.result_id

    def palette_kind(self) -> str:
        """A generated create op belongs to the kind that declares it, even when it makes another
        kind (a version, alias or snapshot of that resource), which no palette lists."""
        created = self.creates and (self.creates if self.legacy else self.kind)
        kind = created or self.source or self.targets[0]
        return "subnet" if kind in SUBNET_KINDS else kind

    def fields(self) -> list[shapes.Field]:
        return [f for f in shapes.fields(self.spec, self.service) if f.name not in self.server_fields]

    def describe(self) -> dict[str, Any]:
        """What the web app needs to offer this op: which gesture, from what, onto what, with which form."""
        out: dict[str, Any] = {"name": self.name, "gesture": self.gesture, "title": self.spec.title,
                               "kind": self.kind, "generated": self.legacy is None,
                               "fields": [f.describe() for f in self.fields()]}
        if self.legacy is None:
            if self.spec.defaults:  # as text, the way the form holds every value
                out["defaults"] = {k: v if isinstance(v, str) else json.dumps(v) if isinstance(v, (dict, list, bool)) else str(v)
                                   for k, v in self.spec.defaults.items()}
            if self.spec.expect:
                out["nameField"] = self.spec.expect.label  # the field the new resource is known by
        if self.creates:
            out |= {"creates": self.creates, "containers": list(self.containers)}
            if self.spec.container:
                out["container"] = {"param": self.spec.container.param, "by": self.spec.container.by}
        if self.source:
            out["source"] = self.source
            if self.spec.source_param:
                out["sourceParam"] = self.spec.source_param
        if self.targets:
            out["targets"] = list(self.targets)
            if self.spec.target_param:
                out["targetParam"] = self.spec.target_param
        return out


@dataclass
class Prepared:
    """A request checked and turned into its command. `params`: the hand-written op's model, or the
    generated op's API request."""
    op: BuilderOp
    params: Any
    argv: list[str]
    problems: list[Problem] = field(default_factory=list)
    target: str | None = None  # the scene node a delete, modify or attribute op acts on

    @property
    def command(self) -> str:
        return display(self.argv)


def _build(registry: Registry) -> dict[str, BuilderOp]:
    out: dict[str, BuilderOp] = {}
    n = 0
    for t in registry.types:
        for spec in t.ops:
            n += 1
            service = spec.service or t.service
            shapes.operation(service, spec.api)  # raises when botocore has no such operation
            if spec.argv:
                legacy = legacy_ops.OPS.get(spec.argv)
                if legacy is None:
                    raise ValueError(f"{t.kind}: op {spec.id} names no hand-written op {spec.argv!r}")
                containers = legacy.containers
                order = list(legacy_ops.OPS).index(spec.argv)
            else:
                legacy, order = None, len(legacy_ops.OPS) + n
                containers = tuple(registry.expand(spec.containers)) if spec.containers is not None \
                    else tuple(sorted(t.parent_kinds()))
                if spec.validator and spec.validator not in VALIDATORS:
                    raise ValueError(f"{t.kind}: op {spec.id} names no validator {spec.validator!r}")
                for f in shapes.fields(spec, service):
                    if f.type == "blob" and not (f.flag and f.sample):
                        raise ValueError(f"{t.kind}: op {spec.id}: blob field {f.name} needs flag and sample")
            out[spec.id] = BuilderOp(spec, t.kind, service, legacy, containers, order)
    return out


_BUILT: dict[int, tuple[Registry, dict[str, BuilderOp]]] = {}


def all_ops(registry: Registry | None = None) -> dict[str, BuilderOp]:
    """The registry's ops by name, hand-written ones first in their own order."""
    registry = registry or default_registry()
    cached = _BUILT.get(id(registry))
    if cached is None or cached[0] is not registry:
        built = _build(registry)
        cached = _BUILT[id(registry)] = (registry, dict(sorted(built.items(), key=lambda kv: kv[1].order)))
    return cached[1]


def op_named(name: Any, registry: Registry | None = None) -> BuilderOp | None:
    return all_ops(registry).get(name) if isinstance(name, str) else None


def catalog(palette: list[str], registry: Registry | None = None) -> list[dict[str, Any]]:
    """Ops a lab offers: those whose palette kind the lab lists (F4.1)."""
    return [op.describe() for op in all_ops(registry).values() if op.palette_kind() in palette]


def server_field_problem(op: BuilderOp, raw: dict[str, Any]) -> list[str]:
    """Server fields the request sent, in either spelling of a hand-written op's model."""
    names = set(op.server_fields)
    if op.legacy:
        names |= {n for n, f in op.legacy.params.model_fields.items() if f.alias in op.server_fields}
    return sorted(names & set(raw))


def parse_legacy(op: BuilderOp, raw: dict[str, Any]) -> Params:
    """The hand-written op's model. OpError when a field is missing or unknown."""
    assert op.legacy is not None
    try:
        return op.legacy.params.model_validate(raw)
    except ValidationError as e:
        fields = [".".join(map(str, err["loc"])) for err in e.errors()]
        raise OpError(f"{op.name}: wrong parameters: {', '.join(fields)}") from e


def _list_fields(op: BuilderOp) -> frozenset[str]:
    return frozenset(f.name for f in op.fields() if f.type == "list")


def _tags(op: BuilderOp, request: dict[str, Any], tags: Tags) -> None:
    """The lab's tags on a generated create, in the form the API takes them."""
    if op.gesture != "create" or not tags:
        return
    members = shapes.operation(op.service, op.spec.api).input_shape.members
    name = next((n for n in ("Tags", "tags") if n in members), None)  # SQS spells it in lower case
    if name is None or name in request:
        return
    member = members[name]
    if member.type_name == "map":
        request[name] = dict(sorted(tags.items()))
    elif member.type_name == "list" and set(getattr(member.member, "members", {})) >= {"Key", "Value"}:
        request[name] = [{"Key": k, "Value": v} for k, v in sorted(tags.items())]


def _node_label(graph: ResourceGraph, node_id: str) -> str:
    node = next((n for n in graph.nodes if n.id == node_id), None)
    return node_id if node is None or node.label == node_id else f"{node.label} ({node_id})"


def _scene_problems(op: BuilderOp, request: dict[str, Any], graph: ResourceGraph, registry: Registry) -> list[Problem]:
    problems: list[Problem] = []
    for f in op.fields():
        value = request.get(f.name) if "." not in f.name else None
        if not f.ref or not isinstance(value, str):
            continue
        kinds = registry.expand([f.ref])
        found = [n for n in graph.nodes if (n.id if f.ref_by == "id" else n.label) == value]
        if not found:
            problems.append(Problem(f.name, f"{value} is not in the scene; it may have been deleted, be protected, "
                                            "or not be collected yet"))
        elif not any(n.kind in kinds for n in found):
            problems.append(Problem(f.name, f"{_node_label(graph, found[0].id)} is a {found[0].kind}, "
                                            f"but this needs a {f.ref}"))
    spec = op.spec
    if spec.container and op.containers and (value := request.get(spec.container.param)) is not None:
        named = [n for n in graph.nodes if (n.id if spec.container.by == "id" else n.label) == value]
        # Names are unique per kind only: an ECR repository may share a Beanstalk application's name.
        node = next((n for n in named if n.kind in op.containers), named[0] if named else None)
        if node is None:
            problems.append(Problem(spec.container.param, f"{value} is not in the scene"))
        elif node.kind not in op.containers:
            problems.append(Problem(spec.container.param, f"{op.creates} cannot be placed in a {node.kind}; "
                                                          f"drop it on a {' or '.join(op.containers)}"))
    if op.gesture != "create":
        # A connect op changes its source too (attach-user-policy), so a protected source is refused as well.
        acted_on = [(k, spec.target_param) for k in op.targets] + ([(op.source, spec.source_param)] if op.source else [])
        for kinds, param in acted_on:
            for kind in registry.expand([kinds]):
                t: ResourceType | None = registry.get(kind)
                if t and t.protected and jmespath.search(t.protected, request):
                    problems.append(Problem(param or "", f"this {t.label} belongs to the lab platform and "
                                                         "cannot be changed or deleted from the builder"))
    return problems


def prepare(op: BuilderOp, raw: dict[str, Any], *, graph: ResourceGraph, azs: list[str], choices: Choices,
            tags: Tags, registry: Registry | None = None, check: bool = True) -> Prepared:
    """The command for `raw` (text values from the browser or the chat) and every problem with it.
    `check=False` builds the command only (a chat step that waits for an earlier step's id).
    OpError when the request cannot be read as this op at all."""
    registry = registry or default_registry()
    if refused := server_field_problem(op, raw):
        raise OpError(f"{op.name}: wrong parameters: {', '.join(refused)} (the server fills these in)")
    first = sanitize(raw, list_fields=_list_fields(op), service=op.service)
    if op.legacy:
        params = parse_legacy(op, raw)
        for server_field in op.server_fields:
            params = params.model_copy(update=SERVER_FILL[server_field](graph, params))
        prepared = Prepared(op, params, op.legacy.argv(params, tags), first)
        if check and not first:
            prepared.problems += legacy_validate(op.legacy.name, params, graph, azs, choices)
        return prepared

    request, unreadable = shapes.request(op.spec, op.service, raw)
    _tags(op, request, tags)
    blobs: dict[str, str] = {}
    problems = list(first) + [Problem(k, v) for k, v in unreadable.items()]
    for f in op.fields():
        if f.type == "blob" and f.sample:
            try:
                blobs[f.name] = str(sample_zip(f.sample))
            except SampleError as e:
                problems.append(Problem(f.name, str(e)))
    prepared = Prepared(op, request, shapes.argv(op.spec, op.service, request, blobs) if not problems else
                        _argv_without_blobs(op, request), problems)
    if problems or not check:
        return prepared
    if shape := shapes.shape_problems(op.service, op.spec.api, request):
        prepared.problems += [Problem(_member_of(line), line) for line in shape]
        return prepared
    prepared.problems += _scene_problems(op, request, graph, registry)
    prepared.target = _target_node(op, request, graph, registry)
    if not prepared.problems and op.spec.validator:
        prepared.problems += VALIDATORS[op.spec.validator](request, graph)
    return prepared


def _argv_without_blobs(op: BuilderOp, request: dict[str, Any]) -> list[str]:
    """The command shown while a problem keeps it from running: sample files are not built for it."""
    return shapes.argv(op.spec, op.service, request, {f.name: f"<{f.sample}.zip>" for f in op.fields() if f.type == "blob"})


def _member_of(line: str) -> str:
    """The member a botocore validation message is about, e.g. `Missing required parameter in input: "Engine"`."""
    quoted = line.split('"')
    return quoted[1].split(".")[0] if len(quoted) > 2 else ""


def expectation(prepared: Prepared, stdout: str, version: int) -> dict[str, Any]:
    """What the next graph must show for a run to count as seen by the collector (F4.5)."""
    op = prepared.op
    if op.legacy:
        return legacy_ops.expectation(op.legacy, prepared.params, stdout, version)
    if op.gesture == "delete" and (gone := _target_id(prepared)):
        return {"gone": gone}
    if op.gesture == "create" and (new_id := legacy_ops.result_id(op, stdout)):  # type: ignore[arg-type]
        return {"node": new_id}
    return {"after": version}


def practice_expectation(prepared: Prepared) -> dict[str, Any]:
    """What the graph must show once the learner has run the command themselves (F4.7)."""
    op = prepared.op
    if op.legacy:
        return legacy_ops.practice_expectation(op.legacy, prepared.params)
    if op.gesture == "delete" and (gone := _target_id(prepared)):
        return {"gone": gone}
    if op.spec.expect and isinstance(label := prepared.params.get(op.spec.expect.label), str):
        return {"kind": op.spec.expect.kind or op.creates or op.kind, "label": label}
    return {"after": 0}


def _target_node(op: BuilderOp, request: dict[str, Any], graph: ResourceGraph, registry: Registry) -> str | None:
    param = op.spec.target_param
    value = request.get(param) if param else None
    if op.gesture == "create" or not isinstance(value, str):
        return None
    kinds = registry.expand(list(op.targets))
    found = next((n for n in graph.nodes if n.kind in kinds and value in (n.id, n.label)), None)
    return found.id if found else None


def _target_id(prepared: Prepared) -> str | None:
    return prepared.target
