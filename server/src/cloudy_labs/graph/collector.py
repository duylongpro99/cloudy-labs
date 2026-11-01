"""Read what the emulator holds into a ResourceGraph, driven by the resource type registry.

The collector knows no resource kind by name. For each kind the registry lists it calls the kind's
list method (once per distinct call, all services in parallel), keeps the items its filters keep,
enriches them, then turns each into a node: id, label, parent, props and edges come from the
entry's JMESPaths and named hooks.

A service that fails (a timeout, an unknown operation, a 5xx) drops only its own kinds and adds a
warning; the graph never breaks because of one service. Floci refusing connections is reported as
"emulator down", as is every service failing at once (the hub then decides whether that is
transient). Collecting calls the emulator directly, not through api-tap, so it never shows up as
learner activity.

The tree's root is the emulator's account. Every region the lab uses sits in it, and regional kinds
are listed once per region; global kinds (IAM, CloudFront, Route 53) are listed once and hang under
the account's `global` group.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import cache
from typing import Any, Callable, Iterable

import botocore.session
import jmespath
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError

from ..config import DEFAULT_REGION
from ..providers.aws import AwsProvider
from ..registry import Registry, ResourceType, default_registry
from ..registry.hooks import HOOKS, USER_DATA_NOTE  # noqa: F401  (USER_DATA_NOTE re-exported for callers)
from .host_ports import host_ports as docker_host_ports
from .schema import Contains, Edge, Node, ResourceGraph

FALLBACK_ACCOUNT = "000000000000"  # Floci's account; used when STS does not answer
GLOBAL_ID = "global"
CLIENT_CONFIG = Config(connect_timeout=2, read_timeout=5, retries={"max_attempts": 1, "mode": "standard"})
EMPTY = (None, {}, [])
# Kinds whose links decide whether traffic gets through: a lab that has any of them lists them all.
REACHABILITY_KINDS = frozenset({"route-table", "security-group", "network-acl", "vpc-peering", "subnet-public", "subnet-private"})


def _search(path: str, data: Any) -> Any:
    return jmespath.search(path, data)


class ServiceFailed(Exception):
    def __init__(self, service: str, error: BaseException):
        super().__init__(f"{service}: {type(error).__name__}")
        self.service, self.error = service, error


@dataclass
class CollectContext:
    """What hooks may read: earlier list results, the collect time, host ports and the warning list."""
    clients: Callable[[str], Any]
    now: datetime
    ports: Callable[[], dict[str, dict[str, int]]]
    region: str = DEFAULT_REGION
    warnings: list[str] = field(default_factory=list)
    _listed: dict[tuple[str, str, str], list[dict]] = field(default_factory=dict)
    _ports: dict[str, dict[str, int]] | None = None

    def listed(self, service: str, method: str, items: str, params: dict | None = None) -> list[dict]:
        key = (service, method, items + repr(sorted((params or {}).items())))
        if key not in self._listed:
            self._listed[key] = call_list(self.clients(service), method, items, params or {})
        return self._listed[key]

    def host_ports(self) -> dict[str, dict[str, int]]:
        if self._ports is None:
            self._ports = self.ports()
        return self._ports


def call_list(client: Any, method: str, items: str, params: dict) -> list[dict]:
    if client.can_paginate(method):
        response = client.get_paginator(method).paginate(**params).build_full_result()
    else:
        response = getattr(client, method)(**params)
    return _search(items, response) or []


def _first(paths: Iterable[str], item: dict) -> Any:
    for p in paths:
        value = _search(p, item)
        if value not in (None, ""):
            return value
    return None


def _keep(rt: ResourceType, ctx: CollectContext, item: dict) -> bool:
    for f in rt.filter:
        if f.hook is not None:
            if not HOOKS[f.hook](ctx, item, f.args):
                return False
            continue
        value = _search(f.path, item)
        if f.not_in is not None and value in f.not_in:
            return False
        if f.in_ is not None and value not in f.in_:
            return False
    if rt.protected and _search(rt.protected, item):
        return False
    return True


def _enrich(rt: ResourceType, ctx: CollectContext, item: dict) -> dict:
    if not rt.enrich:
        return item  # no client needed: a hook-listed kind may have no AWS service at all
    client = ctx.clients(rt.service) if rt.service else None
    for e in rt.enrich:
        if e.hook is not None:
            item = {**item, **HOOKS[e.hook](ctx, client, item, e.args)}
            continue
        params = {k: _search(p, item) for k, p in e.params.items()}
        try:
            response = getattr(client, e.method)(**params, **e.const)
        except ClientError:  # the resource went away between the two calls: leave the prop out
            continue
        item = {**item, e.merge_as: _search(e.pick, response) if e.pick else response}
    return item


@dataclass
class _Pending:
    rt: ResourceType
    item: dict
    id: str


def list_items(registry: Registry, kinds: list[str], ctx: CollectContext) -> tuple[dict[str, list[dict]], list[ServiceFailed]]:
    """Raw items per kind, after filters and enrichment. Services run in parallel; within one
    service every distinct list call runs once."""
    types = [registry.by_kind[k] for k in kinds if registry.by_kind[k].listing is not None]
    by_service: dict[str, list[ResourceType]] = {}
    for rt in types:
        by_service.setdefault(rt.service, []).append(rt)

    def run(service: str) -> tuple[str, dict[str, list[dict]] | ServiceFailed]:
        out: dict[str, list[dict]] = {}
        try:
            for rt in by_service[service]:
                spec = rt.listing
                if spec.scope is not None:
                    continue  # listed once its parent kind is known (below)
                if spec.hook is not None:
                    items = HOOKS[spec.hook](ctx, spec.params)
                else:
                    items = ctx.listed(service, spec.method, spec.items, spec.params)
                out[rt.kind] = [_enrich(rt, ctx, i) for i in items if _keep(rt, ctx, i)]
        except EndpointConnectionError:
            raise
        except (BotoCoreError, ClientError, Exception) as e:  # noqa: BLE001 - isolate any failure to its service
            return service, ServiceFailed(service, e)
        return service, out

    raw: dict[str, list[dict]] = {}
    failed: list[ServiceFailed] = []
    if by_service:
        with ThreadPoolExecutor(max_workers=min(len(by_service), 16)) as pool:
            for service, result in pool.map(run, sorted(by_service)):
                if isinstance(result, ServiceFailed):
                    failed.append(result)
                else:
                    raw.update(result)
    # Kinds listed per parent: once per parent item, in kind order, after the parents are known.
    for rt in types:
        spec = rt.listing
        if spec.scope is None or rt.service in {f.service for f in failed}:
            continue
        try:
            found: list[dict] = []
            for parent in raw.get(spec.scope.parent_kind, []):
                value = _search(spec.scope.field, parent)
                if value is None:
                    continue
                items = ctx.listed(rt.service, spec.method, spec.items, {**spec.params, spec.scope.param: value})
                found.extend({**i, "_Parent": value} for i in items)
            raw[rt.kind] = [_enrich(rt, ctx, i) for i in found if _keep(rt, ctx, i)]
        except EndpointConnectionError:
            raise
        except Exception as e:  # noqa: BLE001
            failed.append(ServiceFailed(rt.service, e))
            for other in types:
                if other.service == rt.service:
                    raw.pop(other.kind, None)
    return raw, failed


def _order(registry: Registry, kinds: list[str]) -> list[str]:
    """Kinds with every parent kind before its children."""
    done: list[str] = []
    wanted = set(kinds)

    def visit(k: str, stack: tuple[str, ...] = ()) -> None:
        if k in done or k in stack:
            return
        for p in sorted(registry.by_kind[k].parent_kinds()):
            if p in wanted:
                visit(p, (*stack, k))
        done.append(k)

    for k in kinds:
        visit(k)
    return done


def build_graph(registry: Registry, raw: dict[str, list[dict]], ctx: CollectContext, *, emulator: str = "floci",
                regions: list[str] | None = None, account: str = FALLBACK_ACCOUNT,
                contexts: dict[str, CollectContext] | None = None) -> ResourceGraph:
    """Pure: the graph from items per kind (as `list_items` returns them) and the context.

    An item's `_Region` (set by `collect`) is the region it was listed in; items without one belong
    to the context's region. `contexts` holds each region's context, for the hooks."""
    regions = regions or [ctx.region]
    contexts = contexts or {}
    nodes: dict[str, Node] = {}
    kind_of: dict[str, str] = {}
    items_of: dict[str, dict] = {}
    contains: list[Contains] = []
    edges: dict[str, Edge] = {}

    def structural_node(node_id: str, kind: str, label: str, parent: str | None) -> None:
        nodes[node_id] = Node(id=node_id, kind=kind, label=label)
        kind_of[node_id] = kind
        if parent is not None:
            contains.append(Contains(parent=parent, child=node_id))

    structural_node(account, "account", account, None)
    for r in regions:
        structural_node(r, "region", r, account)
    structural_node(GLOBAL_ID, "global", "global", account)

    def structural(kind: str, item: dict) -> str | None:
        if kind == "region":
            return item.get("_Region", ctx.region)
        return {"account": account, "global": GLOBAL_ID}.get(kind)

    def resolve_parent(rt: ResourceType, item: dict) -> str | None:
        for rule in rt.parent:
            allowed = registry.expand([rule.kind])
            if rule.path is None and rule.template is None:
                if (found := structural(rule.kind, item)) is not None:
                    return found
                continue
            if rule.template is not None:
                try:
                    candidates = [rule.template.format(**item)]
                except (KeyError, IndexError):
                    continue
            else:
                value = _search(rule.path, item)
                candidates = value if isinstance(value, list) else [value]
            for c in candidates:
                if isinstance(c, str) and kind_of.get(c) in allowed:
                    return c
        return None

    for kind in _order(registry, [k for k in registry.kinds() if k in raw]):
        rt = registry.by_kind[kind]
        for item in raw.get(kind, []):
            node_id = _first(rt.id, item)
            if not isinstance(node_id, str):
                continue
            parent = resolve_parent(rt, item)
            if parent is None:
                continue  # its parent is not in the graph: leave it out, as before
            label = _first(rt.name, item) or node_id
            props: dict[str, Any] = {}
            for name, spec in rt.props.items():
                if isinstance(spec, str):
                    props[name] = _search(spec, item)
                else:
                    props.update(HOOKS[spec.hook](contexts.get(item.get("_Region", ""), ctx), item, spec.args))
            nodes[node_id] = Node(id=node_id, kind=kind, label=str(label),
                                  props={k: v for k, v in props.items() if v not in EMPTY})
            kind_of[node_id] = kind
            items_of[node_id] = item
            contains.append(Contains(parent=parent, child=node_id))

    def other_end(rule, value: Any) -> str | None:
        allowed = registry.expand(rule.to)
        if rule.match is None:
            return value if isinstance(value, str) and kind_of.get(value) in allowed else None
        for nid, k in kind_of.items():
            if k in allowed:
                found = _search(rule.match, items_of.get(nid, {}))
                if found == value or (isinstance(found, list) and value in found):
                    return nid
        return None

    for node_id, item in items_of.items():
        rt = registry.by_kind[kind_of[node_id]]
        for rule in rt.edges:
            subs = (_search(rule.each, item) or []) if rule.each else [item]
            for sub in subs:
                value = _search(rule.target, sub)
                label = (_search(rule.label, sub) or "") if rule.label else ""
                for v in value if isinstance(value, list) else [value]:
                    if v is None:
                        continue
                    other = other_end(rule, v)
                    if other is None:
                        continue
                    src, dst = (other, node_id) if rule.reverse else (node_id, other)
                    edge_id = f"{rule.kind}:{src}->{dst}" + (f":{label}" if label else "")
                    edges[edge_id] = Edge(id=edge_id, kind=rule.kind, from_=src, to=dst, label=label)

    return ResourceGraph(
        taken_at=ctx.now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        emulator=emulator,
        nodes=sorted(nodes.values(), key=lambda n: n.id),
        contains=sorted(contains, key=lambda c: (c.child, c.parent)),
        edges=sorted(edges.values(), key=lambda e: e.id),
        warnings=sorted(ctx.warnings),
    )


def emulator_down(now: datetime, regions: Iterable[str] = (DEFAULT_REGION,), reason: str = "", *,
                  account: str = FALLBACK_ACCOUNT, emulator: str = "floci") -> ResourceGraph:
    regions = list(regions) or [DEFAULT_REGION]
    return ResourceGraph(
        taken_at=now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        emulator=emulator,
        status="emulator-down",
        nodes=sorted([Node(id=account, kind="account", label=account), Node(id=GLOBAL_ID, kind="global", label="global"),
                      *(Node(id=r, kind="region", label=r) for r in regions)], key=lambda n: n.id),
        contains=sorted((Contains(parent=account, child=c) for c in [*regions, GLOBAL_ID]), key=lambda c: (c.child, c.parent)),
        edges=[],
        warnings=[f"{emulator.capitalize()} không trả lời: {reason}"] if reason else [],
    )


_accounts: dict[str, str] = {}


def account_id(provider: Any) -> str:
    """The emulator's account id from STS, cached per endpoint; the fallback when STS does not answer."""
    key = getattr(provider, "direct_endpoint", None)
    if key in _accounts:
        return _accounts[key]
    try:
        found = provider.client("sts", direct=True, config=CLIENT_CONFIG).get_caller_identity()["Account"]
    except Exception:  # noqa: BLE001 - no STS (a fake, an emulator without it): the account is only a label
        return FALLBACK_ACCOUNT
    if key is not None:
        _accounts[key] = found
    return found


def collect(
    provider: AwsProvider | None = None,
    *,
    regions: Iterable[str] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ports: Callable[[], dict[str, dict[str, int]]] = docker_host_ports,
    kinds: Iterable[str] | None = None,
    registry: Registry | None = None,
) -> ResourceGraph:
    """`kinds` limits what is listed (default: the whole registry); parents of each kind are added.
    `regions` (default: the provider's region) are collected in order; the first one also lists
    the global kinds."""
    registry = registry or default_registry()
    provider = provider or AwsProvider("floci")
    emulator = getattr(provider, "emulator", "floci")
    regions = list(dict.fromkeys(regions or [getattr(provider, "region", DEFAULT_REGION)]))
    wanted = _with_parents(registry, list(kinds) if kinds is not None else registry.kinds())
    now = clock()
    host_ports: list[dict[str, dict[str, int]]] = []

    def shared_ports() -> dict[str, dict[str, int]]:  # one docker call per collect, not per region
        if not host_ports:
            host_ports.append(ports())
        return host_ports[0]

    raw: dict[str, list[dict]] = {}
    contexts: dict[str, CollectContext] = {}
    warnings: list[str] = []
    for n, region in enumerate(regions):
        clients: dict[str, Any] = {}

        def client(service: str, region: str = region, clients: dict[str, Any] = clients) -> Any:
            if service not in clients:
                clients[service] = provider.client(service, direct=True, config=CLIENT_CONFIG,
                                                   **({"region": region} if len(regions) > 1 else {}))
            return clients[service]

        here = [k for k in wanted if n == 0 or registry.by_kind[k].scope == "regional"]
        ctx = contexts[region] = CollectContext(clients=client, now=now, ports=shared_ports, region=region)
        try:
            found, failed = list_items(registry, here, ctx)
        except EndpointConnectionError as e:  # connection refused: the emulator is stopped or being recreated
            return emulator_down(now, regions, type(e).__name__, emulator=emulator)
        if failed:
            services = {rt.service for k in here if (rt := registry.by_kind[k]).listing is not None and rt.service}
            if {f.service for f in failed} >= services:
                raise failed[0].error  # nothing answered: let the hub decide whether it is transient
            for f in failed:
                where = f" ({region})" if len(regions) > 1 else ""
                ctx.warnings.append(f"service {f.service}{where} lỗi: {type(f.error).__name__}: {f.error}"[:300])
        for kind, items in found.items():
            raw.setdefault(kind, []).extend({**i, "_Region": region} for i in items)
    home = contexts[regions[0]]
    graph_ctx = CollectContext(clients=home.clients, now=now, ports=shared_ports, region=regions[0])
    graph = build_graph(registry, raw, graph_ctx, emulator=emulator, regions=regions,
                        account=account_id(provider), contexts=contexts)
    for c in contexts.values():  # props hooks warn into the item's region context
        warnings.extend(c.warnings)
    return graph.model_copy(update={"warnings": sorted({*graph.warnings, *warnings})})


def _with_parents(registry: Registry, kinds: list[str]) -> list[str]:
    out: list[str] = []
    stack = [k for k in kinds if k in registry.by_kind]
    while stack:
        k = stack.pop(0)
        if k in out:
            continue
        out.append(k)
        rt = registry.by_kind[k]
        stack.extend(sorted(rt.parent_kinds()))
        # A kind listed per parent (one call per log group, per hosted zone...) needs that parent listed too.
        if rt.listing and rt.listing.scope:
            stack.append(rt.listing.scope.parent_kind)
    return [k for k in registry.kinds() if k in out]


def region_azs(provider: AwsProvider | None = None, region: str | None = None) -> list[str]:
    """Availability Zones of the region as the emulator reports them; empty when it does not answer."""
    ec2 = (provider or AwsProvider("floci", region or DEFAULT_REGION)).client("ec2", direct=True, config=CLIENT_CONFIG)
    try:
        zones = ec2.describe_availability_zones()["AvailabilityZones"]
    except (BotoCoreError, ClientError):
        return []
    return sorted(z["ZoneName"] for z in zones if z.get("State", "available") == "available")


def lab_kinds(registry: Registry, palette: Iterable[str], target: Iterable[str], seen: Iterable[str] = ()) -> list[str] | None:
    """The closed set of kinds to list for one lab: the palette's kinds and the kinds their ops make
    (a function's versions), the target's, every reachability kind when the lab has one, and kinds
    already seen in this lab's graph or named by its writes. None when the lab names no kind at all:
    then everything is listed."""
    offered = set(registry.expand(list(palette)))
    named = offered | {op.creates for t in registry.types if t.kind in offered for op in t.ops if op.creates} | set(target)
    if not named:
        return None
    if named & REACHABILITY_KINDS:
        named |= REACHABILITY_KINDS
    return [k for k in registry.kinds() if k in named | set(seen)]


@cache
def _signing_names() -> dict[str, frozenset[str]]:
    """SigV4 signing name (what api-tap reports, e.g. `monitoring`) -> the botocore services that sign
    with it. Several share one: `rds` is also DocumentDB and Neptune, `elasticloadbalancing` both ELB
    APIs, `events` EventBridge and its v2 model, `apigateway` both API Gateway APIs."""
    session = botocore.session.get_session()
    out: dict[str, set[str]] = {}
    for name in session.get_available_services():
        meta = session.get_service_model(name).metadata
        out.setdefault(meta.get("signingName") or meta.get("endpointPrefix") or name, set()).add(name)
        out.setdefault(name, set()).add(name)
    return {k: frozenset(v) for k, v in out.items()}


def kinds_of_action(registry: Registry, service: str, action: str) -> set[str]:
    """Kinds a write named by api-tap may have touched: those with an op of that API, else those
    whose view names a noun inside the action (AuthorizeSecurityGroupIngress -> security-group),
    else every listed kind of the service. Too many only costs a few more list calls."""
    names = _signing_names().get(service, frozenset({service}))
    types = [t for t in registry.types if t.service in names and t.listing is not None and not t.test_only]
    by_op = {k for t in types for op in t.ops if op.api == action for k in (t.kind, op.creates) if k}
    by_noun = {t.kind for t in types if any(noun in action for noun in t.view.actions)}
    return by_op or by_noun or {t.kind for t in types}
