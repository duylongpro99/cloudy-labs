"""Resource type registry: every kind of resource the platform knows, described once as data.

One YAML file per AWS service sits next to this module. Each entry is a `ResourceType`: how the
collector lists it, how a listed item becomes a node (id, label, parent, edges, props), what the
web scene draws for it, what the chat may see of it and what Floci supports. The graph schema,
the lab schema, the twin and the collector read this registry instead of keeping their own tables.

Where data cannot express a rule, an entry names a hook from `hooks.HOOKS`; a name that is not in
that dict makes the registry fail to load.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import jmespath
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .hooks import HOOKS

REGISTRY_DIR = Path(__file__).parent
SLUG = r"^[a-z0-9][a-z0-9-]*$"
# A parent or edge may name `subnet` for either visibility of a subnet.
ALIASES: dict[str, tuple[str, ...]] = {"subnet": ("subnet-public", "subnet-private")}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _compile(path: str) -> str:
    jmespath.compile(path)  # raises on a syntax error, so a bad path fails at load time
    return path


class HookRef(_Strict):
    hook: str
    args: dict[str, Any] = {}

    @field_validator("hook")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in HOOKS:
            raise ValueError(f"unknown hook {v!r}; hooks are named in registry/hooks.py HOOKS")
        return v


class Scope(_Strict):
    """List once per node of `parent_kind`, passing `field` of that node's item as `param`."""
    parent_kind: str
    param: str
    field: str


class ListSpec(_Strict):
    method: str | None = None
    items: str | None = None  # JMESPath into the response, e.g. "Reservations[].Instances[]"
    paginate: bool = True
    params: dict[str, Any] = {}
    scope: Scope | None = None
    hook: str | None = None  # items made by a hook from what other kinds listed

    @model_validator(mode="after")
    def _one_source(self) -> "ListSpec":
        if (self.method is None) == (self.hook is None):
            raise ValueError("list needs either method (with items) or hook")
        if self.method is not None and not self.items:
            raise ValueError("list.method needs items")
        if self.items:
            _compile(self.items)
        if self.hook is not None and self.hook not in HOOKS:
            raise ValueError(f"unknown hook {self.hook!r}")
        return self


class Enrich(_Strict):
    """One more call per item; its response (or `pick` of it) is stored on the item as `merge_as`."""
    method: str | None = None
    params: dict[str, str] = {}  # API parameter -> JMESPath into the item
    const: dict[str, Any] = {}  # API parameters with fixed values
    pick: str | None = None
    merge_as: str | None = None
    hook: str | None = None
    args: dict[str, Any] = {}

    @model_validator(mode="after")
    def _valid(self) -> "Enrich":
        if (self.method is None) == (self.hook is None):
            raise ValueError("enrich needs either method or hook")
        if self.method is not None and not self.merge_as:
            raise ValueError("enrich.method needs merge_as")
        if self.hook is not None and self.hook not in HOOKS:
            raise ValueError(f"unknown hook {self.hook!r}")
        for p in [*self.params.values(), *([self.pick] if self.pick else [])]:
            _compile(p)
        return self


class Filter(_Strict):
    path: str | None = None
    not_in: list[Any] | None = None
    in_: list[Any] | None = Field(None, alias="in")
    hook: str | None = None
    args: dict[str, Any] = {}

    @model_validator(mode="after")
    def _valid(self) -> "Filter":
        if (self.path is None) == (self.hook is None):
            raise ValueError("filter needs either path or hook")
        if self.path is not None:
            _compile(self.path)
        if self.hook is not None and self.hook not in HOOKS:
            raise ValueError(f"unknown hook {self.hook!r}")
        return self


class ParentRule(_Strict):
    """`kind` alone: always this structural parent (region, account, global).
    `path`: JMESPath to the parent's id (a list tries each value); `template` builds it from the item."""
    kind: str
    path: str | None = None
    template: str | None = None

    @model_validator(mode="after")
    def _valid(self) -> "ParentRule":
        if self.path and self.template:
            raise ValueError("parent takes path or template, not both")
        if self.path:
            _compile(self.path)
        return self


class EdgeRule(_Strict):
    """Edges from this node to nodes of kind `to`, found by `target` (JMESPath, scalar or list).
    `each` walks sub-items first (target and label then read the sub-item). `match` finds the
    other end by a field of its item instead of its id. `reverse` makes the other end the source."""
    kind: str
    to: list[str]
    target: str
    each: str | None = None
    label: str | None = None
    match: str | None = None
    reverse: bool = False
    optional: bool = True
    # How the web draws this edge kind; one kind keeps one style across the registry.
    style: Literal["attach", "route", "association", "reference", "replica"] | None = None

    @field_validator("to", mode="before")
    @classmethod
    def _as_list(cls, v: Any) -> Any:
        return [v] if isinstance(v, str) else v

    @model_validator(mode="after")
    def _paths(self) -> "EdgeRule":
        for p in (self.target, self.each, self.label, self.match):
            if p:
                _compile(p)
        return self


class Caveat(_Strict):
    code: str = Field(pattern=SLUG)
    text: str
    prop: str | None = None


class View(_Strict):
    """How the web app draws a kind. The icon is a file in web/src/scene/aws-objects/icons/;
    `source` is its path in the AWS Architecture Icons package (absent for self-drawn artwork)."""
    role: Literal["block", "tray-badge", "attach-badge", "outline-only"] = "block"
    category: str = "general"
    icon: str | None = None
    source: str | None = None
    curve_segments: int | None = Field(None, ge=1)  # Bezier subdivision when extruding the glyph
    height: float | None = Field(None, gt=0)  # block height; the web default otherwise
    order: int = 1000
    group: bool = False  # drawn as a tray holding its children
    stack: bool = False  # a group that stacks its child groups front to back
    host: bool = False  # SGs and EIPs attach to it as badges
    actions: list[str] = []  # nouns in API action names that touch this kind, e.g. "DBInstance"

    @model_validator(mode="after")
    def _icon(self) -> "View":
        if self.role != "outline-only" and not self.icon:
            raise ValueError(f"a {self.role} view needs an icon")
        if self.source and not self.source.endswith(f"/{self.icon}"):
            raise ValueError(f"icon {self.icon!r} must be named after its source {self.source!r}")
        return self


# Prop names whose values may hold secrets or whole scripts; a kind may never send them to the chat
# model, whatever its `chat_props` say. Matched case-insensitively anywhere in the name.
CHAT_PROPS_DENY = ("environment", "password", "secret", "outputs", "parameters", "userdata")
Gesture = Literal["create", "modify", "connect", "attribute", "delete"]
FieldType = Literal["string", "enum", "boolean", "integer", "list", "json", "blob"]


class OpField(_Strict):
    """A form field the API's input shape cannot describe on its own: a field of an op with its own
    `argv` (which maps fields to flags itself), or a shape member that needs a label, options or a
    reference to a kind. A plain string in `fields` is a shape member taken as the shape says."""
    name: str
    type: FieldType | None = None  # None: from the shape; "string" for an argv op's own field
    label: str | None = None
    doc: str = ""
    placeholder: str | None = None
    multiline: bool = False
    choices: list[str] | None = None
    source: str | None = None  # options the web app fills from the lab: azs, images, instanceTypes, ...
    ref: str | None = None  # the kind whose node id (or label) this takes; a select of the scene's nodes
    ref_by: Literal["id", "label"] = "id"
    required: bool | None = None  # None: from the shape; True for an argv op's own field
    free: bool = False  # connect and attribute forms leave it editable although the gesture opened them
    flag: str | None = None  # blob: the CLI option that takes the file (the API member is nested)
    sample: str | None = None  # blob: the server-chosen sample (builder/samples) it always sends


class Container(_Strict):
    """The param that takes the tray a create op is dropped on."""
    param: str
    by: Literal["id", "label"] = "id"


class Expect(_Strict):
    """A practice run counts once a node of `kind` labelled with the value of param `label` appears."""
    kind: str | None = None  # the op's own kind when absent
    label: str


class OpSpec(_Strict):
    """One builder operation of a kind. Ops without `argv` are generated from the botocore shape
    of `api`; the ones with `argv` keep a hand-written command, checks and gesture (builder/ops.py)."""
    id: str = Field(pattern=SLUG)
    api: str = Field(pattern=r"^[A-Z][A-Za-z0-9]*$")
    service: str | None = None  # botocore service; the kind's own when absent
    gesture: Gesture
    title: str
    fields: list[str | OpField] = []
    defaults: dict[str, Any] = {}
    choices: dict[str, list[str]] = {}
    container: Container | None = None
    containers: list[str] | None = None  # create: tray kinds; the kind's parent kinds when absent
    creates: str | None = None  # create: the palette kind; the op's kind when absent
    source: str | None = None  # connect: the kind the edge starts from
    source_param: str | None = None
    targets: list[str] = []  # connect: kinds the edge ends on; attribute/modify/delete: kinds it acts on
    target_param: str | None = None
    validator: str | None = None  # builder/validate.py VALIDATORS
    argv: str | None = None  # the hand-written op in builder/ops.py OPS it keeps (command, checks, expectation)
    result_id: str | None = None  # dotted path to the new resource's id in the JSON output
    expect: Expect | None = None
    server_fields: list[str] = []  # filled by the server; refused from the browser and the chat
    note: str = ""  # for the chat model: what the op does and how to fill it

    @model_validator(mode="after")
    def _valid(self) -> "OpSpec":
        names = [f if isinstance(f, str) else f.name for f in self.fields]
        if len(set(names)) != len(names):
            raise ValueError(f"op {self.id}: a field is listed twice")
        if self.argv and any(isinstance(f, str) for f in self.fields):
            raise ValueError(f"op {self.id}: an op with its own argv describes every field itself")
        if self.gesture == "connect" and self.argv is None and not (self.source and self.targets):
            raise ValueError(f"op {self.id}: a connect op needs source and targets")
        known = set(names) | set(self.server_fields)
        for p in (self.source_param, self.target_param, *(self.container and [self.container.param] or [])):
            if p and self.argv is None and p not in known:
                raise ValueError(f"op {self.id}: {p} is not one of its fields")
        return self

    def field_names(self) -> list[str]:
        return [f if isinstance(f, str) else f.name for f in self.fields]


class ContractStep(_Strict):
    """One builder op the contract test runs through the lab-server. A param value "{name}" is the
    node a `save`d step made, or a value of the lab info (az, region, image, instanceType, userData);
    it may sit inside a longer text (com.amazonaws.{region}.s3)."""
    op: str = Field(pattern=SLUG)
    params: dict[str, Any] = {}
    save: str | None = None


class Contract(_Strict):
    """How the contract test proves the builder can create (and change, and delete) this kind on
    the pinned Floci: `needs` make what it sits in, `create` makes it, `then` changes it."""
    needs: list[ContractStep] = []
    create: ContractStep
    parent: str | None = None  # the saved node it must sit in; a node of one of its parent kinds when absent
    then: list[ContractStep] = []  # modify/connect/attribute/delete ops, checked by what each run expects
    max_seconds: float = Field(2.0, gt=0)  # from the command's return to the graph showing the result


class FlociSupport(_Strict):
    status: Literal["supported", "control-plane-only", "missing"] = "supported"
    note: str = ""


class ResourceType(_Strict):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    kind: str = Field(pattern=SLUG)
    service: str = ""  # boto3 client name; empty for structural kinds
    label: str
    listing: ListSpec | None = Field(None, alias="list")  # None: a structural kind the collector makes itself
    enrich: list[Enrich] = []
    filter: list[Filter] = []
    id: list[str] = []  # JMESPaths tried in order
    name: list[str] = []  # label of the node: Name tag first, then these paths in order
    parent: list[ParentRule] = []
    edges: list[EdgeRule] = []
    props: dict[str, str | HookRef] = {}  # prop name -> JMESPath, or a hook returning several props
    chat_props: list[str] = []  # the only props the chat assistant may send to the model
    caveats: list[Caveat] = []
    protected: str | None = None  # JMESPath; an item it matches is hidden from the graph and builder
    # regional: listed once per region of the lab, under its region; global: listed once (in the
    # lab's region), under the global group.
    scope: Literal["regional", "global"] = "regional"
    builder: bool = False  # the builder palette may offer it
    target: bool = True  # a lab's target architecture may name it
    view: View  # every kind says how it is drawn
    floci: FlociSupport = FlociSupport()
    test_only: bool = False
    ops: list[OpSpec] = []  # what the builder and the chat can do to this kind
    contract: Contract | None = None  # the contract test of its create op (tests/test_registry_contract_docker.py)

    @field_validator("filter", "parent", "edges", "enrich", mode="before")
    @classmethod
    def _as_list(cls, v: Any) -> Any:
        return [v] if isinstance(v, dict) else v

    @field_validator("id", "name", mode="before")
    @classmethod
    def _paths_list(cls, v: Any) -> Any:
        return [v] if isinstance(v, str) else v

    @model_validator(mode="after")
    def _valid(self) -> "ResourceType":
        for p in [*self.id, *self.name, *([self.protected] if self.protected else [])]:
            _compile(p)
        for name, spec in self.props.items():
            if isinstance(spec, str):
                _compile(spec)
        if denied := [p for p in self.chat_props if any(d in p.lower() for d in CHAT_PROPS_DENY)]:
            raise ValueError(f"{self.kind}: chat_props {denied} may hold secrets or scripts and never go to the chat model")
        hook_props = any(isinstance(s, HookRef) for s in self.props.values())
        if not hook_props:
            extra = set(self.chat_props) - set(self.props)
            if extra:
                raise ValueError(f"{self.kind}: chat_props {sorted(extra)} are not props")
        if self.listing is not None:
            if not self.service and self.listing.method:
                raise ValueError(f"{self.kind}: a listed kind needs a service")
            if not self.id:
                raise ValueError(f"{self.kind}: a listed kind needs id paths")
            if not self.parent:
                raise ValueError(f"{self.kind}: a listed kind needs a parent rule")
        return self

    @property
    def structural(self) -> bool:
        return self.listing is None

    def parent_kinds(self) -> set[str]:
        found: set[str] = set()
        for rule in self.parent:
            found.update(ALIASES.get(rule.kind, (rule.kind,)))
        return found


class Registry:
    def __init__(self, types: list[ResourceType]):
        self.types = types
        self.by_kind: dict[str, ResourceType] = {}
        for t in types:
            if t.kind in self.by_kind:
                raise ValueError(f"kind {t.kind!r} is declared twice")
            self.by_kind[t.kind] = t
        self._check()

    def _expand(self, kinds: list[str] | set[str]) -> set[str]:
        out: set[str] = set()
        for k in kinds:
            out.update(ALIASES.get(k, (k,)))
        return out

    def _check(self) -> None:
        known = set(self.by_kind)
        for t in self.types:
            for rule in t.parent:
                if not self._expand([rule.kind]) <= known:
                    raise ValueError(f"{t.kind}: parent kind {rule.kind!r} is not in the registry")
            for e in t.edges:
                missing = self._expand(e.to) - known
                if missing:
                    raise ValueError(f"{t.kind}: edge to unknown kind {sorted(missing)}")
            if t.listing and t.listing.scope and t.listing.scope.parent_kind not in known:
                raise ValueError(f"{t.kind}: scope parent kind {t.listing.scope.parent_kind!r} is not in the registry")
        self.edge_styles()  # one style per edge kind
        seen_ops: set[str] = set()
        for t in self.types:
            for op in t.ops:
                if op.id in seen_ops:
                    raise ValueError(f"op {op.id!r} is declared twice")
                seen_ops.add(op.id)
                if not (op.service or t.service):
                    raise ValueError(f"{t.kind}: op {op.id} needs a service")
                kinds = [*(op.containers or []), *([op.source] if op.source else []), *op.targets]
                kinds += [f.ref for f in op.fields if isinstance(f, OpField) and f.ref]
                if op.expect and op.expect.kind:
                    kinds.append(op.expect.kind)
                if missing := self._expand(kinds) - known:
                    raise ValueError(f"{t.kind}: op {op.id} names unknown kind {sorted(missing)}")
        # Kind-level parent cycles: a kind may not be its own ancestor.
        for t in self.types:
            seen: set[str] = set()
            stack = list(t.parent_kinds())
            while stack:
                k = stack.pop()
                if k == t.kind:
                    raise ValueError(f"{t.kind}: parent rules form a cycle")
                if k in seen:
                    continue
                seen.add(k)
                stack.extend(self.by_kind[k].parent_kinds())

    def get(self, kind: str) -> ResourceType | None:
        return self.by_kind.get(kind)

    def kinds(self) -> list[str]:
        return [t.kind for t in self.types]

    def by_service(self) -> dict[str, list[ResourceType]]:
        out: dict[str, list[ResourceType]] = {}
        for t in self.types:
            if t.listing is not None:
                out.setdefault(t.service, []).append(t)
        return out

    def parent_kinds(self) -> dict[str, set[str]]:
        return {t.kind: t.parent_kinds() for t in self.types if t.parent}

    def edge_kinds(self) -> list[str]:
        return sorted({e.kind for t in self.types for e in t.edges})

    def edge_styles(self) -> dict[str, str]:
        """Style per edge kind: the one its rules declare, else `reference`."""
        styles: dict[str, str] = {}
        for t in self.types:
            for e in t.edges:
                if e.style is None:
                    continue
                if styles.setdefault(e.kind, e.style) != e.style:
                    raise ValueError(f"edge kind {e.kind!r} has two styles: {styles[e.kind]!r} and {e.style!r}")
        return {k: styles.get(k, "reference") for k in self.edge_kinds()}

    def builder_kinds(self) -> list[str]:
        """Kinds a lab palette may list; both subnet visibilities are one palette entry, `subnet`."""
        out: list[str] = []
        for t in self.types:
            if not t.builder:
                continue
            alias = next((a for a, members in ALIASES.items() if t.kind in members), None)
            name = alias if alias and all(self.by_kind.get(m) and self.by_kind[m].builder for m in ALIASES[alias]) else t.kind
            if name not in out:
                out.append(name)
        return out

    def target_kinds(self) -> list[str]:
        return [t.kind for t in self.types if t.target and t.parent]

    def expand(self, kinds: list[str] | set[str]) -> set[str]:
        return self._expand(kinds)

    def public(self) -> dict[str, Any]:
        """What the web app needs: kinds with their view, and the edge kinds."""
        def view(v: View) -> dict[str, Any]:
            d = v.model_dump()
            d["curveSegments"] = d.pop("curve_segments")
            return d

        return {
            "kinds": [
                {"kind": t.kind, "label": t.label, "service": t.service, "signingName": signing_name(t.service), **view(t.view),
                 "parents": sorted(t.parent_kinds()), "floci": t.floci.status, "scope": t.scope}
                for t in sorted(self.types, key=lambda t: (t.view.order, t.kind))
            ],
            "edgeKinds": [{"kind": k, "style": s} for k, s in self.edge_styles().items()],
        }


@lru_cache(maxsize=None)
def signing_name(service: str) -> str:
    """The SigV4 signing name of a botocore service: what api-tap reports for a call (`monitoring`
    for cloudwatch, `elasticloadbalancing` for elbv2). The service name itself when botocore has
    no such service."""
    import botocore.session

    try:
        meta = botocore.session.get_session().get_service_model(service).metadata
    except Exception:  # noqa: BLE001  botocore raises UnknownServiceError, DataNotFoundError
        return service
    return meta.get("signingName") or meta.get("endpointPrefix") or service


def _read(path: Path) -> list[ResourceType]:
    data = yaml.safe_load(path.read_text()) or []
    if not isinstance(data, list):
        raise ValueError(f"{path.name}: expected a list of resource types")
    out = []
    for entry in data:
        try:
            out.append(ResourceType.model_validate(entry))
        except Exception as e:
            raise ValueError(f"{path.name}: {entry.get('kind') if isinstance(entry, dict) else entry}: {e}") from e
    return out


def load_registry(*dirs: Path) -> Registry:
    """The registry from REGISTRY_DIR plus any extra directories (tests add a test-only kind)."""
    types: list[ResourceType] = []
    for d in (REGISTRY_DIR, *dirs):
        for path in sorted(d.glob("*.yaml")):
            types.extend(_read(path))
    return Registry(types)


@lru_cache(maxsize=1)
def default_registry() -> Registry:
    import os

    extra = [Path(p) for p in os.environ.get("CLOUDY_LABS_REGISTRY_EXTRA", "").split(os.pathsep) if p]
    return load_registry(*extra)
