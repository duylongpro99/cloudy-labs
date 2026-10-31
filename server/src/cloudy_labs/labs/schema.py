"""Lab definition schema (PRD F1.1). One lab is one `lab.yaml` next to its `checks.py`."""

import re
from ipaddress import IPv4Network
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..graph.schema import PARENT_KINDS

SLUG = r"^[a-z0-9][a-z0-9-]*$"
FN_REF = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:[A-Za-z_][A-Za-z0-9_]*$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Task(_Strict):
    id: str = Field(pattern=SLUG)
    text: str


class Check(_Strict):
    id: str = Field(pattern=SLUG)
    task: str
    fn: str  # "module:function", module relative to the lab directory
    args: dict[str, Any] = {}
    description: str = ""

    @field_validator("fn")
    @classmethod
    def _fn_ref(cls, v: str) -> str:
        if not FN_REF.match(v):
            raise ValueError(f"expected 'module:function', got {v!r}")
        return v


class Hint(_Strict):
    task: str
    text: str


# Resource kinds the builder can create (PRD F4.1); a lab's palette is a subset.
BuilderKind = Literal["vpc", "subnet", "igw", "elastic-ip", "nat", "route-table", "security-group", "key-pair", "instance"]
# Tags go into the CLI's shorthand syntax, where commas, brackets, braces and spaces have meaning.
TAG_TEXT = re.compile(r"[A-Za-z0-9._:/-]{1,128}")  # used with fullmatch
USER_DATA_MAX = 16 * 1024  # bytes; EC2's limit on UserData before base64


class Builder(_Strict):
    palette: list[BuilderKind] = []
    tags: dict[str, str] = {}  # added to every resource the builder creates, next to Name
    # The instance form's starting UserData; the learner may edit it.
    user_data: str = Field("", alias="userData")

    @field_validator("palette")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("palette lists a kind twice")
        return v

    @field_validator("tags")
    @classmethod
    def _no_name(cls, v: dict[str, str]) -> dict[str, str]:
        if "Name" in v:
            raise ValueError("the Name tag comes from the builder form, not from the lab")
        for key, value in v.items():
            if not TAG_TEXT.fullmatch(key) or not TAG_TEXT.fullmatch(value):
                raise ValueError(f"tag {key}={value}: use 1-128 letters, digits and . _ : / - only")
        return v

    @field_validator("user_data")
    @classmethod
    def _user_data_size(cls, v: str) -> str:
        if len(v.encode()) > USER_DATA_MAX:
            raise ValueError(f"userData is {len(v.encode())} bytes; EC2 accepts at most {USER_DATA_MAX}")
        return v


TargetKind = Literal[
    "vpc", "az", "subnet-public", "subnet-private", "igw", "nat",
    "route-table", "security-group", "key-pair", "instance", "elastic-ip",
]


class TargetNode(_Strict):
    """One resource of the architecture the lab builds, drawn as a ghost until its checks pass."""
    id: str = Field(pattern=SLUG)
    kind: TargetKind
    label: str
    parent: str | None = None  # another target node; none means the region
    checks: list[str] = []  # the node is reached once all of these pass; their resource ids find it


class Target(_Strict):
    nodes: list[TargetNode] = []

    def check_references(self, check_ids: set[str]) -> None:
        by_id: dict[str, TargetNode] = {}
        for n in self.nodes:
            if n.id in by_id:
                raise ValueError(f"duplicate target node id: {n.id}")
            by_id[n.id] = n
        for n in self.nodes:
            parent_kind = "region"
            if n.parent is not None:
                if n.parent not in by_id:
                    raise ValueError(f"target node {n.id!r} has unknown parent {n.parent!r}")
                parent_kind = by_id[n.parent].kind
            if parent_kind not in PARENT_KINDS[n.kind]:
                where = "the region" if n.parent is None else f"a {parent_kind} ({n.parent!r})"
                raise ValueError(f"target node {n.id!r}: a {n.kind} cannot sit in {where}; "
                                 f"it goes in {' or '.join(sorted(PARENT_KINDS[n.kind]))}")
            unknown = [c for c in n.checks if c not in check_ids]
            if unknown:
                raise ValueError(f"target node {n.id!r} refers to unknown check {', '.join(map(repr, unknown))}")
            if n.kind == "az" and n.checks:
                raise ValueError(f"target node {n.id!r}: an az has no checks; it is reached through its subnets")
            if n.kind != "az" and not n.checks:
                raise ValueError(f"target node {n.id!r} needs at least one check")
        # Parent kinds only ever go up the region > vpc > az > subnet > nat/instance ladder, so a
        # cycle cannot pass the kind rule above; walking every chain is the plain proof anyway.
        for n in self.nodes:
            seen, cur = set(), n
            while cur.parent is not None:
                if cur.id in seen:
                    raise ValueError(f"target nodes form a cycle through {cur.id!r}")
                seen.add(cur.id)
                cur = by_id[cur.parent]


class Lab(_Strict):
    id: str = Field(pattern=SLUG)
    provider: Literal["aws"]
    emulator: Literal["floci", "moto"] = "floci"
    title: str
    # CIDRs the lab will create; checked against Docker networks before the lab starts.
    cidrs: list[IPv4Network] = []
    setup: list[str] = []  # "module:function" steps run after a reset
    tasks: list[Task] = Field(min_length=1)
    checks: list[Check] = Field(min_length=1)
    hints: list[Hint] = []
    builder: Builder = Builder()  # no builder section: the web app says the lab has no builder
    target: Target = Target()  # the architecture the 3D scene shows as ghosts (PRD F6.2)

    @field_validator("setup")
    @classmethod
    def _setup_refs(cls, v: list[str]) -> list[str]:
        for ref in v:
            if not FN_REF.match(ref):
                raise ValueError(f"expected 'module:function', got {ref!r}")
        return v

    @model_validator(mode="after")
    def _references(self) -> "Lab":
        task_ids = [t.id for t in self.tasks]
        check_ids = [c.id for c in self.checks]
        for kind, ids in (("task", task_ids), ("check", check_ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            if dupes:
                raise ValueError(f"duplicate {kind} id: {', '.join(dupes)}")
        known = set(task_ids)
        for c in self.checks:
            if c.task not in known:
                raise ValueError(f"check {c.id!r} refers to unknown task {c.task!r}")
        for h in self.hints:
            if h.task not in known:
                raise ValueError(f"hint refers to unknown task {h.task!r}")
        self.target.check_references(set(check_ids))
        return self
