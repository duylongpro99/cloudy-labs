"""Twin mode (PRD F6): which parts of a lab's target architecture the emulator already holds.

`bind_target` is pure: it matches each target node to a real resource through the resource ids
of the checks that node lists, so the only matching rules are the checkers themselves.
`TwinState` is what the lab-server sends the web app as `{"type": "twin"}`; like the graph, it is
camelCase JSON mirrored by web/src/graph/types.ts and pinned by a golden file both sides read.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from .checks import CheckResult
from .graph.schema import ResourceGraph
from .labs import LoadedLab
from .labs.schema import Target
from .progress import Attempt

GHOST_PREFIX = "ghost:"  # target ids are slugs and could equal a real id such as the region's


def ghost_id(target_id: str) -> str:
    return GHOST_PREFIX + target_id


@dataclass(frozen=True)
class GhostNode:
    id: str  # ghost_id(target node id)
    kind: str
    label: str
    parent: str  # a ghost id, or the real id of the resource its parent is bound to
    checks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Binding:
    bound: dict[str, str]  # target node id -> real resource id
    ghosts: list[GhostNode]


def bind_target(target: Target, results: list[CheckResult], graph: ResourceGraph) -> Binding:
    """Same inputs, same binding. Nodes bind in the order the lab declares them:

    a node binds once every check it lists passed, to the first id in those checks' resource ids
    that the graph holds with the node's kind, that no earlier node took, and that sits in the
    resource its parent bound to. Under an az, candidates go by (real az, id), so the first az of
    the target lands on the alphabetically first real one. An az binds to the real az its bound
    children share.
    """
    passed = {r.check_id: r for r in results if r.passed}
    kinds = {n.id: n.kind for n in graph.nodes}
    parent_of = {c.child: c.parent for c in graph.contains}
    region = next(n.id for n in graph.nodes if n.id not in parent_of)
    nodes = {n.id: n for n in target.nodes}
    bound: dict[str, str] = {}
    taken: set[str] = set()

    for node in target.nodes:
        if node.kind == "az" or not node.checks or any(c not in passed for c in node.checks):
            continue
        ids = {i for c in node.checks for i in passed[c].resource_ids}
        candidates = [i for i in ids if kinds.get(i) == node.kind and i not in taken]
        parent = nodes[node.parent] if node.parent else None
        if parent is None:
            candidates = [i for i in candidates if parent_of.get(i) == region]
        elif parent.id in bound:
            candidates = [i for i in candidates if parent_of.get(i) == bound[parent.id]]
        elif parent.kind == "az" and parent.parent in bound:  # the az binds later; its vpc must still match
            candidates = [i for i in candidates if parent_of.get(parent_of.get(i, ""), "") == bound[parent.parent]]
        if parent is not None and parent.kind == "az":
            candidates.sort(key=lambda i: (parent_of.get(i, ""), i))
        else:
            candidates.sort()
        if candidates:
            bound[node.id] = candidates[0]
            taken.add(candidates[0])

    for node in target.nodes:
        if node.kind != "az":
            continue
        real = {parent_of.get(bound[n.id]) for n in target.nodes if n.parent == node.id and n.id in bound}
        if len(real) == 1:  # subnets are the only children of an az, and they sit in a real az
            az = real.pop()
            if node.parent not in bound or parent_of.get(az) == bound[node.parent]:
                bound[node.id] = az

    def resolve(target_id: str | None) -> str:
        if target_id is None:
            return region
        return bound.get(target_id) or ghost_id(target_id)

    ghosts = [
        GhostNode(ghost_id(n.id), n.kind, n.label, resolve(n.parent), list(n.checks))
        for n in target.nodes if n.id not in bound
    ]
    return Binding(bound=bound, ghosts=ghosts)


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class TwinCheck(_Model):
    id: str
    task: str
    description: str
    status: Literal["passed", "failed", "pending"]  # pending: not run against the current emulator state
    message: str
    resource_ids: list[str]


class TwinGhost(_Model):
    id: str
    kind: str
    label: str
    parent: str
    checks: list[str]


class TwinState(_Model):
    lab: str | None = None  # None: no lab is open
    attempt: int | None = None
    checks: list[TwinCheck] = []
    ghosts: list[TwinGhost] = []
    bound: dict[str, str] = {}

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


def twin_state(loaded: LoadedLab, attempt: Attempt, results: list[CheckResult] | None, graph: ResourceGraph,
               note: str = "") -> TwinState:
    """`results` None: the checks could not run (the emulator is down); each is pending, with `note`."""
    by_id = {r.check_id: r for r in results or []}
    checks = []
    for c in loaded.lab.checks:
        r = by_id.get(c.id)
        status = "pending" if r is None else "passed" if r.passed else "failed"
        checks.append(TwinCheck(id=c.id, task=c.task, description=c.description, status=status,
                                message=r.message if r else note, resource_ids=list(r.resource_ids) if r else []))
    binding = bind_target(loaded.lab.target, results or [], graph)
    return TwinState(
        lab=loaded.lab.id, attempt=attempt.id, checks=checks, bound=binding.bound,
        ghosts=[TwinGhost(id=g.id, kind=g.kind, label=g.label, parent=g.parent, checks=g.checks) for g in binding.ghosts],
    )
