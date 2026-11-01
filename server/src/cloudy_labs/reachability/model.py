"""Results of a reachability analysis and a read-only index over the collected graph."""

from __future__ import annotations

import ipaddress
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from cloudy_labs.graph.schema import ResourceGraph

Network = ipaddress.IPv4Network

# Why a hop passed or stopped the traffic. Codes, so the web panel and checks can match on them.
REASONS = (
    "allowed", "routed", "delivered", "no-matching-rule", "denied-by-rule", "return-denied", "no-route",
    "blackhole", "route-target-unknown", "no-public-ip", "not-transitive",
    "no-return-route", "loop-detected", "endpoint-not-associated", "unsupported-target",
)
SUBNET_KINDS = ("subnet-public", "subnet-private")
ANY = ipaddress.ip_network("0.0.0.0/0")


class EndpointError(ValueError):
    """A source or destination that names no resource in the graph and is no IPv4 address."""


@dataclass(frozen=True)
class Hop:
    resource_id: str
    kind: str
    verdict: str  # allow | deny | forward
    reason: str
    rule: str | None = None


@dataclass
class Reachability:
    ok: bool
    hops: list[Hop]
    blocked_at: str | None = None
    reason: str = "delivered"
    label: str = "analysed"  # configuration was analysed; no packet was sent

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "blockedAt": self.blocked_at, "reason": self.reason, "label": self.label,
                "hops": [{k: v for k, v in asdict(h).items()} for h in self.hops]}


@dataclass
class Endpoint:
    """One end of a flow. `network` is the address the rules are matched against: a host /32 when the
    collected IP lies in its subnet, else the whole subnet (Floci may hand out an IP from elsewhere)."""

    label: str
    kind: str  # a node kind, "internet" or "address"
    network: Network
    node_id: str | None = None
    subnet: str | None = None
    vpc: str | None = None
    groups: tuple[str, ...] = ()
    public: bool = False
    gateway_endpoint: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def net(text: Any) -> Network | None:
    try:
        n = ipaddress.ip_network(str(text), strict=False)
    except ValueError:
        return None
    return n if isinstance(n, ipaddress.IPv4Network) else None


def contains(outer: Network | None, inner: Network | None) -> bool:
    return outer is not None and inner is not None and inner.subnet_of(outer)


class Index:
    """Lookups over a ResourceGraph by id, kind, parent and edge."""

    def __init__(self, graph: ResourceGraph):
        self.nodes = {n.id: n for n in graph.nodes}
        self.parent = {c.child: c.parent for c in graph.contains}
        self.edges = list(graph.edges)

    def props(self, node_id: str | None) -> dict[str, Any]:
        node = self.nodes.get(node_id or "")
        return node.props if node else {}

    def kind(self, node_id: str | None) -> str | None:
        node = self.nodes.get(node_id or "")
        return node.kind if node else None

    def label(self, node_id: str | None) -> str:
        node = self.nodes.get(node_id or "")
        return node.label if node else (node_id or "")

    def of_kind(self, *kinds: str) -> list[Any]:
        return sorted((n for n in self.nodes.values() if n.kind in kinds), key=lambda n: n.id)

    def ancestor(self, node_id: str | None, *kinds: str) -> str | None:
        seen: set[str] = set()
        cur = self.parent.get(node_id or "")
        while cur and cur not in seen:
            if self.kind(cur) in kinds:
                return cur
            seen.add(cur)
            cur = self.parent.get(cur)
        return None

    def groups_of(self, node_id: str) -> tuple[str, ...]:
        return tuple(sorted({e.from_ for e in self.edges if e.kind == "attached" and e.to == node_id
                             and self.kind(e.from_) == "security-group"}))

    def linked(self, node_id: str, edge_kind: str) -> list[str]:
        return sorted(e.to for e in self.edges if e.kind == edge_kind and e.from_ == node_id)

    def subnet_cidr(self, subnet: str | None) -> Network | None:
        return net(self.props(subnet).get("cidr"))

    def subnet_at(self, network: Network, vpcs: Iterable[str] | None = None) -> str | None:
        """The most specific subnet holding `network` (optionally only in `vpcs`)."""
        best: tuple[int, str] | None = None
        allowed = set(vpcs) if vpcs is not None else None
        for s in self.of_kind(*SUBNET_KINDS):
            cidr = self.subnet_cidr(s.id)
            if contains(cidr, network) and (allowed is None or self.ancestor(s.id, "vpc") in allowed):
                if best is None or cidr.prefixlen > best[0]:
                    best = (cidr.prefixlen, s.id)
        return best[1] if best else None
