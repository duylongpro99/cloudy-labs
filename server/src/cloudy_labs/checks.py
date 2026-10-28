"""Checker contract (PRD F1.3) and the runner that applies it to a lab.

A checker is `def name(ctx: CheckContext, **args) -> CheckResult`. It reads emulator state
through `ctx.client(service)` and reports the resource ids the 3D scene should highlight.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .labs import LoadedLab


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    message: str
    resource_ids: list[str] = field(default_factory=list)
    check_id: str = ""  # filled in by the runner


@dataclass(frozen=True)
class CheckContext:
    client: Callable[..., Any]  # client(service) -> boto3 client bound to the lab's emulator


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
        results.append(CheckResult(r.passed, r.message, list(r.resource_ids), check.id))
    return results
