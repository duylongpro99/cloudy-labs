"""Resource graph: what the emulator holds, as the 3D scene needs it.

Exported as camelCase JSON. web/src/graph/types.ts mirrors these models, and a golden
graph written by the server tests is read back by the web tests so the two cannot drift.
"""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

# Same set as AwsKind in web/src/scene/aws-objects/manifest.ts.
Kind = Literal[
    "region", "vpc", "az", "subnet-public", "subnet-private", "igw", "nat",
    "route-table", "security-group", "key-pair", "instance", "elastic-ip",
]
# route: route table -> IGW/NAT, labelled with the destination CIDR.
# association: route table -> subnet. attached: SG/EIP -> what it is attached to.
# uses-key: instance -> key pair.
EdgeKind = Literal["route", "association", "attached", "uses-key"]
# Kinds the collector may place directly under each kind: a lab's target nests the same way.
# An attached IGW sits in its VPC; one not attached yet sits in the region.
PARENT_KINDS: dict[str, set[str]] = {
    "vpc": {"region"}, "key-pair": {"region"}, "elastic-ip": {"region"}, "igw": {"region", "vpc"},
    "az": {"vpc"}, "route-table": {"vpc"}, "security-group": {"vpc"},
    "subnet-public": {"az"}, "subnet-private": {"az"},
    "nat": {"subnet-public", "subnet-private"}, "instance": {"subnet-public", "subnet-private"},
}
Status = Literal["ok", "emulator-down"]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class Node(_Model):
    id: str
    kind: Kind
    label: str
    props: dict[str, Any] = Field(default_factory=dict)


class Contains(_Model):
    parent: str
    child: str


class Edge(_Model):
    id: str
    kind: EdgeKind
    from_: str = Field(alias="from")
    to: str
    label: str = ""


class ResourceGraph(_Model):
    version: int = 0
    taken_at: str  # ISO 8601, UTC
    emulator: Literal["floci"] = "floci"
    status: Status = "ok"
    nodes: list[Node]
    contains: list[Contains]
    edges: list[Edge]
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _well_formed(self) -> "ResourceGraph":
        ids = [n.id for n in self.nodes]
        known = set(ids)
        if len(known) != len(ids):
            raise ValueError("duplicate node ids")
        parents: dict[str, str] = {}
        for c in self.contains:
            for end in (c.parent, c.child):
                if end not in known:
                    raise ValueError(f"contains refers to unknown node {end}")
            if c.child in parents:
                raise ValueError(f"{c.child} has two parents: {parents[c.child]} and {c.parent}")
            parents[c.child] = c.parent
        roots = [n for n in self.nodes if n.id not in parents]
        if len(roots) != 1 or roots[0].kind != "region":
            raise ValueError(f"the tree must have exactly one root and it must be a region, got {[n.id for n in roots]}")
        for node in self.nodes:  # every chain must end at the root, so no cycles
            seen, cur = set(), node.id
            while cur in parents:
                if cur in seen:
                    raise ValueError(f"containment cycle through {cur}")
                seen.add(cur)
                cur = parents[cur]
        for e in self.edges:
            for end in (e.from_, e.to):
                if end not in known:
                    raise ValueError(f"edge {e.id} refers to unknown node {end}")
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")

    def to_json(self, indent: int | None = None) -> str:
        """Deterministic: same graph, same bytes."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True, ensure_ascii=False)

    def content_hash(self) -> str:
        """Identity of the state the graph shows, ignoring when it was taken and its version."""
        import hashlib

        data = self.to_dict()
        del data["version"], data["takenAt"]
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
