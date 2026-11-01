"""Checker contract (PRD F1.3) and the runner that applies it to a lab.

A checker is `def name(ctx: CheckContext, **args) -> CheckResult`. It reads emulator state
through `ctx.client(service)` and reports the resource ids the 3D scene should highlight.
A network check can ask `ctx.reachable(src, dst, port)` and turn the answer into a result with
`reachability_result`; until reachability grading is enabled that result is `info` and never
decides whether the lab is complete.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .labs import LoadedLab


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    message: str
    resource_ids: list[str] = field(default_factory=list)
    check_id: str = ""  # filled in by the runner
    info: bool = False  # shown to the learner, but not graded: it never blocks completion


class _Clients:
    """The collector's provider interface over a checker's `client(service)`."""

    def __init__(self, client: Callable[..., Any]):
        self._client = client

    def client(self, service: str, credentials=None, **_):
        return self._client(service)


@dataclass(frozen=True)
class CheckContext:
    client: Callable[..., Any]  # client(service) -> boto3 client bound to the lab's emulator
    # collect(kinds) -> ResourceGraph of the emulator; default: the collector over `client`
    collect: Callable[[Iterable[str]], Any] | None = None

    def graph(self, kinds: Iterable[str]) -> Any:
        if self.collect is not None:
            return self.collect(kinds)
        from .graph.collector import collect

        return collect(_Clients(self.client), kinds=list(kinds), ports=lambda: {})

    def reachable(self, src: str, dst: str, port: int, proto: str = "tcp") -> Any:
        """Static analysis of whether `src` reaches `dst` on `port`, over a fresh graph of every
        network kind (not the scene's, which a lab may narrow). Raises EndpointError for an
        endpoint that names nothing in the graph."""
        from .reachability import NETWORK_KINDS, analyze

        return analyze(self.graph(NETWORK_KINDS), src, dst, port, proto)


def reachability_result(found: Any, message: str, expect: bool = True) -> CheckResult:
    """A check result from `ctx.reachable(...)`: passed when reachability is what the lab expects,
    highlighting the hops; `info` while reachability grading is disabled."""
    from .reachability import GRADING_ENABLED

    hops = list(dict.fromkeys(h.resource_id for h in found.hops if h.resource_id != "internet"))
    where = f" (blocked at {found.blocked_at}: {found.reason})" if not found.ok else ""
    return CheckResult(found.ok == expect, f"{message}{where} [analysed]", hops, info=not GRADING_ENABLED)


def _invalid(r: object) -> str | None:
    if not isinstance(r, CheckResult):
        return f"returned {type(r).__name__}, expected CheckResult"
    if not isinstance(r.passed, bool):
        return f"returned passed={r.passed!r}, expected True or False"
    if not isinstance(r.message, str):
        return f"returned message of type {type(r.message).__name__}, expected str"
    if not isinstance(r.resource_ids, list) or not all(isinstance(i, str) for i in r.resource_ids):
        return "returned resource_ids that is not a list of strings"
    return None


def run_checks(loaded: LoadedLab, ctx: CheckContext) -> list[CheckResult]:
    results = []
    for check in loaded.lab.checks:
        try:
            r = loaded.resolve(check.fn)(ctx, **check.args)
            problem = _invalid(r)
            if problem:
                r = CheckResult(False, f"checker {check.fn} {problem}")
        except Exception as e:  # one broken checker must not hide the others
            r = CheckResult(False, f"checker error: {type(e).__name__}: {e}")
        results.append(CheckResult(r.passed, r.message, list(r.resource_ids), check.id, bool(getattr(r, "info", False))))
    return results
