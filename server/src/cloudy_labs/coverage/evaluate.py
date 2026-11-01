"""Can the platform run a lab, and what does it lack? One of four verdicts with the reasons for it.

    blocked             Floci lacks a service or an API the lab needs (or an override says so)
    gap                 the platform lacks something it could have: a registry kind, a passing
                        contract test, a builder op
    ready-with-caveats  only caveats the registry declares (control-plane-only, reachability
                        analysed statically, a contract not run yet...)
    ready               nothing left

Evidence: Floci's documented actions at the pinned tag (registry/floci-ops-<version>.json), the
registry, the contract test results (registry/contract-results.json) and the overrides
(coverage/catalog-overrides.yaml). A lab's verdict is a draft while resource names the dictionary
is not sure of are unreviewed (`labctl coverage <lab> --accept`).
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml

from ..graph.collector import REACHABILITY_KINDS
from ..registry import ALIASES, REGISTRY_DIR, Registry, default_registry
from . import extract

COMPOSE = Path(__file__).resolve().parents[1] / "emulator" / "compose.yaml"
CONTRACT_RESULTS = REGISTRY_DIR / "contract-results.json"
OVERRIDES = Path(__file__).parent / "catalog-overrides.yaml"
REVIEW_FILE = "coverage-review.json"
Verdict = Literal["blocked", "gap", "ready-with-caveats", "ready"]
VERDICTS: tuple[Verdict, ...] = ("blocked", "gap", "ready-with-caveats", "ready")
Level = Literal["blocked", "gap", "caveat"]
# Kinds whose presence means the lab's traffic paths are judged by static analysis, not packets.
REACHABILITY_WORDS = re.compile(r"route table|security group|\bNACL\b|network acl|peering|reachab", re.I)
# Services a lab may call without creating anything the platform needs to show.
NO_RESOURCES = {"sts"}
# The catalog's namespace words that are not botocore service names.
NAMESPACE = {"cognito": "cognito-idp", "states": "stepfunctions"}
# Creating APIs that do not make a resource of their own kind (they attach, tag or authorise).
NOT_CREATING = re.compile(r"Attachment$|^Put(Bucket|Object|Item|Record|Parameter|Metric|Event|Secret)|Tags?$|Ingress$|Egress$")


class CoverageError(Exception):
    pass


@dataclass(frozen=True)
class Finding:
    level: Level
    code: str
    text: str  # names services, APIs and kinds only; never the lab page's text
    line: int | None = None
    heading: str | None = None


@dataclass
class Report:
    lab: str
    verdict: Verdict
    draft: bool
    findings: list[Finding]
    unrecognised: list[dict[str, Any]] = field(default_factory=list)  # line, heading, term: for review
    warnings: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["findings"] = [{k: v for k, v in asdict(f).items() if v is not None} for f in self.findings]
        return out


@dataclass(frozen=True)
class Override:
    id: str
    service: str
    reason: str
    apis: tuple[str, ...] = ()
    flags: tuple[tuple[str, str], ...] = ()
    match: tuple[re.Pattern[str], ...] = ()
    exclude: frozenset[str] = frozenset()

    def hits_command(self, cmd: extract.Command) -> bool:
        if cmd.service != self.service:
            return False
        if self.flags:
            return any(name == flag and re.search(rx, value, re.I) for flag, rx in self.flags for name, value in cmd.flags)
        return not self.apis or bool(set(self.apis) & set(cmd.apis))

    def hits_text(self, text: str) -> bool:
        return any(p.search(text) for p in self.match)


def pinned_image(compose: Path = COMPOSE) -> tuple[str, str]:
    """(version, digest) of the Floci image `compose.yaml` pins."""
    m = re.search(r"image:\s*floci/floci:([\w.-]+)@(sha256:[0-9a-f]{64})", compose.read_text())
    if not m:
        raise CoverageError(f"{compose}: no pinned floci/floci image")
    return m.group(1), m.group(2)


@dataclass
class Evidence:
    registry: Registry
    floci: dict[str, Any]  # floci-ops-<version>.json
    contract: dict[str, Any]  # contract-results.json, or {} before the first run
    overrides: list[Override]
    version: str
    digest: str

    @classmethod
    def load(cls, registry: Registry | None = None, compose: Path = COMPOSE,
             contract_file: Path = CONTRACT_RESULTS, overrides_file: Path = OVERRIDES) -> "Evidence":
        version, digest = pinned_image(compose)
        ops_file = REGISTRY_DIR / f"floci-ops-{version}.json"
        if not ops_file.is_file():
            raise CoverageError(f"no {ops_file.name}: run `uv run python scripts/floci-ops-from-docs.py {version}`")
        contract = json.loads(contract_file.read_text()) if contract_file.is_file() else {}
        return cls(registry or default_registry(), json.loads(ops_file.read_text()), contract,
                   read_overrides(overrides_file), version, digest)

    def warnings(self) -> list[str]:
        if not self.contract:
            return ["no contract test results yet (registry/contract-results.json): run the contract tests"]
        if self.contract.get("floci_image_digest") != self.digest:
            return [f"contract results were recorded on Floci {self.contract.get('floci_image_digest')}, "
                    f"but compose.yaml pins {self.digest}: rerun the contract tests"]
        return []

    def contract_of(self, kind: str) -> list[dict[str, Any]]:
        return [r for r in self.contract.get("results", []) if r.get("kind") == kind]

    # Floci
    def floci_service(self, service: str) -> dict[str, Any] | None:
        return self.floci["services"].get(service)

    def floci_api(self, service: str, api: str) -> Finding | None:
        """Why Floci cannot run `api`, or None when it can (or its docs do not list actions)."""
        entry = self.floci_service(service)
        if entry is None:
            return Finding("blocked", "floci-missing-service", f"Floci {self.version} has no {service}")
        if entry.get("complete") or entry.get("unlisted"):
            return None
        if api in entry["refused"]:
            return Finding("blocked", "floci-refused-api", f"Floci {self.version} refuses {service}:{api}")
        if api not in entry["supported"]:
            return Finding("blocked", "floci-missing-api", f"Floci {self.version} does not list {service}:{api}")
        return None

    # Registry
    def kinds_of_service(self, service: str) -> list[str]:
        return [t.kind for t in self.registry.types if t.service == service and not t.structural and not t.test_only]

    def kind_of_api(self, service: str, api: str) -> str | None:
        """The registry kind an API creates or acts on: an op of that API, else a kind whose view
        names the API's noun (CreateDBInstance -> DBInstance)."""
        for t in self.registry.types:
            if t.service == service and any(op.api == api and (op.service or t.service) == service for op in t.ops):
                return t.kind
        noun = extract.CREATE.match(api)
        for t in self.registry.types:
            if t.service == service and noun and noun.group(2) in t.view.actions:
                return t.kind
        return None


def read_overrides(path: Path = OVERRIDES) -> list[Override]:
    out = []
    for e in yaml.safe_load(path.read_text()) or []:
        out.append(Override(
            id=e["id"], service=e["service"], reason=e["reason"], apis=tuple(e.get("apis") or ()),
            flags=tuple((e.get("flags") or {}).items()),
            match=tuple(re.compile(p, re.I) for p in e.get("match") or ()),
            exclude=frozenset(e.get("exclude") or ()),
        ))
    return out


def _kind_findings(ev: Evidence, kinds: set[str], builder_kinds: set[str]) -> list[Finding]:
    out: list[Finding] = []
    for kind in sorted(kinds):
        t = ev.registry.get(kind)
        if t is None:
            out.append(Finding("gap", "no-kind", f"the registry has no kind {kind}"))
            continue
        if t.structural:
            continue
        if t.floci.status == "missing":
            out.append(Finding("blocked", "floci-missing-kind", f"Floci cannot create {kind}: {t.floci.note}".rstrip(": ")))
        elif t.floci.status == "control-plane-only":
            out.append(Finding("caveat", "control-plane-only", f"{kind}: {t.floci.note or 'Floci keeps the configuration only'}"))
        out.extend(Finding("caveat", c.code, f"{kind}: {c.text}") for c in t.caveats)
        results = ev.contract_of(kind)
        if any(r.get("result") == "fail" for r in results):
            failed = sorted({r.get("op", "?") for r in results if r.get("result") == "fail"})
            out.append(Finding("gap", "contract-failed", f"{kind}: contract test failed ({', '.join(failed)})"))
        elif slow := sorted({r.get("op", "?") for r in results if r.get("result") == "slow"}):
            out.append(Finding("caveat", "contract-slow", f"{kind}: the graph showed {', '.join(slow)} later than the limit"))
        elif not results and any(op.gesture == "create" for op in t.ops):
            out.append(Finding("caveat", "contract-not-run", f"{kind}: no contract test result"))
        siblings = next((m for m in ALIASES.values() if kind in m), (kind,))  # subnet-public/-private share ops
        if kind in builder_kinds and not any(ev.registry.by_kind[k].ops for k in siblings if k in ev.registry.by_kind):
            out.append(Finding("gap", "no-builder-op", f"{kind} is in the palette but has no builder op"))
    if kinds & REACHABILITY_KINDS:
        out.append(Finding("caveat", "reachability-analysed", "traffic paths are judged by static analysis of routes, SGs and NACLs"))
    return out


def _service_findings(ev: Evidence, svcs: set[str]) -> list[Finding]:
    out: list[Finding] = []
    for s in sorted(svcs):
        entry = ev.floci_service(s)
        if entry is None:
            out.append(Finding("blocked", "floci-missing-service", f"Floci {ev.version} has no {s}"))
            continue
        if entry.get("unlisted"):
            out.append(Finding("caveat", "floci-actions-unlisted", f"Floci's docs for {s} do not list its actions"))
        if s not in NO_RESOURCES and not ev.kinds_of_service(s):
            out.append(Finding("gap", "no-kind-for-service", f"the registry has no kind of {s}"))
    return out


def verdict_of(findings: list[Finding]) -> Verdict:
    levels = {f.level for f in findings}
    if "blocked" in levels:
        return "blocked"
    if "gap" in levels:
        return "gap"
    return "ready-with-caveats" if "caveat" in levels else "ready"


def _dedupe(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, str]] = set()
    out = []
    for f in findings:
        if (f.code, f.text) not in seen:
            seen.add((f.code, f.text))
            out.append(f)
    order = {"blocked": 0, "gap": 1, "caveat": 2}
    return sorted(out, key=lambda f: (order[f.level], f.code, f.text))


# One lab ------------------------------------------------------------------------------------------


def read_review(lab_dir: Path) -> dict[str, str]:
    """line number (as text) -> "ignore" | "require", from `coverage <lab> --accept`."""
    path = lab_dir / REVIEW_FILE
    if not path.is_file():
        return {}
    return {str(k): v for k, v in json.loads(path.read_text()).get("lines", {}).items()}


def write_review(lab_dir: Path, lines: list[int], require: set[int]) -> Path:
    path = lab_dir / REVIEW_FILE
    data = {"reviewed": date.today().isoformat(),
            "lines": {str(n): "require" if n in require else "ignore" for n in sorted(set(lines) | require)}}
    path.write_text(json.dumps(data, indent=1) + "\n")
    return path


def evaluate_lab(lab_dir: Path, ev: Evidence, review: dict[str, str] | None = None) -> Report:
    """The verdict on `labs/<slug>/`: its lab.yaml (palette, target, checks) and its local page."""
    from ..labs.content import CONTENT_DIR, LAB_MD

    slug = lab_dir.name
    findings: list[Finding] = []
    kinds: set[str] = set()
    builder_kinds: set[str] = set()
    svcs: set[str] = set()
    page = lab_dir / CONTENT_DIR / LAB_MD
    if not (lab_dir / "lab.yaml").is_file() and not page.is_file():
        raise CoverageError(f"{lab_dir}: no lab.yaml and no {CONTENT_DIR}/{LAB_MD}")
    if (lab_dir / "lab.yaml").is_file():
        from ..labs import load_lab

        lab = load_lab(slug, lab_dir.parent).lab
        builder_kinds = set(ev.registry.expand(lab.builder.palette))
        kinds |= builder_kinds | {n.kind for n in lab.target.nodes}
        sources = [p.read_text(encoding="utf-8") for p in sorted(lab_dir.glob("*.py"))]
        svcs |= extract.checker_services(sources)
    svcs |= {ev.registry.by_kind[k].service for k in kinds if k in ev.registry.by_kind and ev.registry.by_kind[k].service}

    unrecognised: list[dict[str, Any]] = []
    review = read_review(lab_dir) if review is None else review
    if page.is_file():
        text = page.read_text(encoding="utf-8")
        for cmd in extract.commands(text):
            where = {"line": cmd.line, "heading": cmd.heading}
            if cmd.service not in extract.services():
                findings.append(Finding("blocked", "unknown-service", f"aws {cmd.cli}: not an AWS service botocore knows", **where))
                continue
            svcs.add(cmd.service)
            if not cmd.apis:
                findings.append(Finding("gap", "unknown-command", f"aws {cmd.cli}: no API of {cmd.service} by that name", **where))
            for api in cmd.apis:
                if problem := ev.floci_api(cmd.service, api):
                    findings.append(Finding(problem.level, problem.code, problem.text, **where))
                if (m := extract.CREATE.match(api)) and not NOT_CREATING.search(api) and m.group(1) in ("Create", "Run", "Allocate"):
                    kind = ev.kind_of_api(cmd.service, api)
                    if kind:
                        kinds.add(kind)
                    else:
                        findings.append(Finding("gap", "no-kind-for-api", f"the registry has no kind that {cmd.service}:{api} creates", **where))
            for o in ev.overrides:
                if o.hits_command(cmd):
                    findings.append(Finding("blocked", "catalog-override", f"{o.id}: {o.reason}", **where))
        for m in extract.mentions(text, extract.dictionary(ev.registry)):
            decision = review.get(str(m.line))
            if m.certain:
                kinds.update(m.kinds)
            elif decision == "require":
                # A name several services share ("target group": elbv2, vpc-lattice) most likely means
                # one Floci has; it blocks the lab only when Floci has none of them.
                emulated = [s for s in m.services if ev.floci_service(s)]
                svcs.update(emulated or m.services)
                findings.append(Finding("gap" if emulated else "blocked", "reviewed-requirement",
                                        f"{m.term} ({', '.join(emulated or m.services)}), marked required",
                                        line=m.line, heading=m.heading))
            else:
                unrecognised.append({"line": m.line, "heading": m.heading, "term": m.term, "services": list(m.services)})
        for n, line, _fenced, heading in extract._lines(text):
            for o in ev.overrides:
                if o.hits_text(line):
                    if review.get(str(n)) == "require":
                        findings.append(Finding("blocked", "catalog-override", f"{o.id}: {o.reason}", line=n, heading=heading))
                    else:
                        unrecognised.append({"line": n, "heading": heading, "term": o.id, "services": [o.service]})
    findings += _service_findings(ev, svcs) + _kind_findings(ev, kinds, builder_kinds)
    findings = _dedupe(findings)
    pending = [u for u in unrecognised if review.get(str(u["line"])) is None]
    return Report(slug, verdict_of(findings), draft=bool(pending), findings=findings, unrecognised=unrecognised,
                  warnings=ev.warnings(), services=sorted(svcs), kinds=sorted(kinds))


# The catalog --------------------------------------------------------------------------------------


def namespaces(row: dict[str, str]) -> set[str]:
    out = set()
    for word in re.split(r"[;,]", row.get("api_namespaces", "")):
        if word := word.strip().lower():
            out.add(NAMESPACE.get(word, word))
    return out


def evaluate_row(row: dict[str, str], ev: Evidence) -> Report:
    """The verdict on one lab of the public catalog, from its metadata only."""
    svcs = namespaces(row)
    findings = _service_findings(ev, svcs)
    if not svcs:
        findings.append(Finding("caveat", "no-api-metadata", "the catalog names no API the lab calls; its page decides"))
    for missing in filter(None, (m.strip() for m in row.get("floci_missing", "").split(";"))):
        findings.append(Finding("blocked", "floci-missing", f"Floci lacks {missing} (catalog research)"))
    if row.get("floci_fit") == "control-plane-only":
        findings.append(Finding("caveat", "control-plane-only", "the lab looks at data-plane behaviour Floci only configures (catalog research)"))
    text = " | ".join(row.get(k, "") for k in ("slug", "title", "toc"))
    for o in ev.overrides:
        if row.get("slug") not in o.exclude and o.hits_text(text):
            findings.append(Finding("blocked", "catalog-override", f"{o.id}: {o.reason}"))
    kinds = {k for s in svcs for k in ev.kinds_of_service(s)}
    kind_findings = [f for f in _kind_findings(ev, kinds, set()) if f.code != "reachability-analysed"]
    findings += kind_findings
    if "ec2" in svcs and REACHABILITY_WORDS.search(text):
        findings.append(Finding("caveat", "reachability-analysed", "traffic paths are judged by static analysis"))
    # The title and table of contents name resources; one that only botocore knows, in a service the
    # lab calls, is a kind the platform still lacks.
    outline = "\n".join([row.get("title", ""), *row.get("toc", "").split(";")])
    for m in extract.mentions(outline, extract.dictionary(ev.registry)):
        if not m.certain and set(m.services) & svcs:
            findings.append(Finding("gap", "no-kind-for-resource", f"the registry has no kind for {m.term} ({', '.join(m.services)})"))
    # Namespaces say which services a lab calls, not which of their resources it makes: having some
    # kind of each service is not enough to call the lab ready.
    if svcs - NO_RESOURCES and not any(f.level in ("blocked", "gap") for f in findings):
        findings.append(Finding("caveat", "namespace-level", "the catalog names the lab's services, not its resources; "
                                "the registry has kinds of each, not necessarily the ones the lab makes"))
    findings = _dedupe(findings)
    return Report(row.get("slug", "?"), verdict_of(findings), draft=False, findings=findings,
                  warnings=[], services=sorted(svcs), kinds=sorted(kinds))


def read_catalog(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@dataclass
class CatalogSummary:
    total: int
    by_verdict: dict[str, int]
    by_service: dict[str, dict[str, int]]  # service -> verdict -> labs naming it
    reasons: dict[str, int]  # blocked/gap finding text -> labs
    reports: list[Report]
    warnings: list[str]

    def as_dict(self, labs: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "total": self.total, "by_verdict": self.by_verdict, "by_service": self.by_service,
            "reasons": self.reasons, "warnings": self.warnings,
            "note": "verdicts come from the public catalog's metadata (API namespaces, table of contents); "
                    "a lab's own page can need more",
        }
        if labs:
            out["labs"] = [{"lab": r.lab, "verdict": r.verdict,
                            "reasons": [f.text for f in r.findings if f.level != "caveat"]} for r in self.reports]
        return out


def evaluate_catalog(rows: list[dict[str, str]], ev: Evidence) -> CatalogSummary:
    reports = [evaluate_row(row, ev) for row in rows]
    by_verdict = {v: 0 for v in VERDICTS}
    by_service: dict[str, dict[str, int]] = {}
    reasons: Counter[str] = Counter()
    for r in reports:
        by_verdict[r.verdict] += 1
        for s in r.services:
            by_service.setdefault(s, {v: 0 for v in VERDICTS})[r.verdict] += 1
        reasons.update({f.text for f in r.findings if f.level == r.verdict or (r.verdict == "gap" and f.level == "gap")})
    return CatalogSummary(len(reports), by_verdict, dict(sorted(by_service.items())), dict(reasons.most_common()),
                          reports, ev.warnings())

