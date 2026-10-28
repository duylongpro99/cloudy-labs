"""Lab lifecycle: start, check, reset and status, on top of a provider and the progress store."""

from collections.abc import Callable
from dataclasses import dataclass, field
from ipaddress import IPv4Network
from pathlib import Path
from typing import Any

from .checks import CheckContext, CheckResult, run_checks
from .config import home
from .emulator.preflight import cidr_overlaps, docker_networks, overlap_warning
from .labs import Lab, LabError, LoadedLab, list_labs, load_lab
from .progress import Progress
from .providers import EMULATORS, Provider, get_provider

Log = Callable[[str], None]


class EngineError(Exception):
    pass


@dataclass
class Engine:
    progress: Progress
    labs_root: Path | None = None  # None: config.labs_dir()
    providers: Callable[[str, str], Provider] = get_provider
    networks: Callable[[], list[tuple[str, IPv4Network]]] = docker_networks
    log: Log = print
    _labs: dict[str, LoadedLab] = field(default_factory=dict)

    @classmethod
    def default(cls, log: Log = print) -> "Engine":
        return cls(Progress(home() / "progress.db"), log=log)

    def lab(self, lab_id: str) -> LoadedLab:
        if lab_id not in self._labs:
            self._labs[lab_id] = load_lab(lab_id, self.labs_root)
        return self._labs[lab_id]

    def _provider(self, lab: Lab) -> Provider:
        provider = self.providers(lab.provider, lab.emulator)
        if not provider.health():
            raise EngineError(f"the {lab.emulator} emulator is not reachable; run `labctl up` first")
        return provider

    def start(self, lab_id: str) -> int:
        loaded = self.lab(lab_id)
        lab = loaded.lab
        if lab.cidrs:
            for overlap in cidr_overlaps(lab.cidrs, self.networks()):
                self.log("warning: " + overlap_warning(*overlap))
        attempt = self._fresh_attempt(loaded)
        self.log(f"{lab.title} ({lab.id}), attempt {attempt}")
        for task in lab.tasks:
            self.log(f"  [{task.id}] {task.text}")
        self.log(f'point your CLI at the emulator: eval "$(labctl env {lab.id})"')
        return attempt

    def reset(self, lab_id: str) -> int:
        attempt = self._fresh_attempt(self.lab(lab_id))
        self.log(f"{lab_id}: emulator reset, attempt {attempt}")
        return attempt

    def _fresh_attempt(self, loaded: LoadedLab) -> int:
        provider = self._provider(loaded.lab)
        provider.reset()
        # Open the attempt before setup: the emulator is already wiped, so the previous attempt
        # is gone whether or not setup succeeds, and `check` must not grade against it.
        attempt = self.progress.start_attempt(loaded.lab.id).id
        ctx = CheckContext(client=provider.client)
        for ref in loaded.lab.setup:
            try:
                loaded.resolve(ref)(ctx)
            except Exception as e:
                raise EngineError(
                    f"{loaded.lab.id}: setup step {ref} failed: {type(e).__name__}: {e}; "
                    f"run `labctl reset {loaded.lab.id}` to try again"
                ) from e
        return attempt

    def check(self, lab_id: str) -> tuple[int, list[CheckResult]]:
        loaded = self.lab(lab_id)
        current = self.progress.current_attempt()
        if current is None or current.lab_id != lab_id:
            raise EngineError(f"no open attempt at {lab_id}; run `labctl start {lab_id}` first")
        provider = self._provider(loaded.lab)
        results = run_checks(loaded, CheckContext(client=provider.client))
        self.progress.record_checks(current.id, results)
        return current.id, results

    def status(self, lab_id: str | None = None) -> dict[str, Any]:
        emulators = {emulator: self.providers(name, emulator).health() for name, emulator in EMULATORS}
        if lab_id:
            self.lab(lab_id)  # an unknown lab id is an error, not an empty result
        current = self.progress.current_attempt()
        focus = lab_id or (current.lab_id if current else None)
        done = self.progress.lab_summary()
        labs = []
        for lid in list_labs(self.labs_root):
            try:
                title = self.lab(lid).lab.title
            except LabError as e:
                title = f"(invalid: {e})"
            labs.append({"id": lid, "title": title, "completed": done.get(lid, False)})
        return {
            "emulators": emulators,
            "current_attempt": current.__dict__ if current else None,
            "lab": focus,
            "results": [result_dict(r) for r in self.progress.latest_results(focus)] if focus else [],
            "labs": labs,
        }


def result_dict(r: CheckResult) -> dict[str, Any]:
    return {"check_id": r.check_id, "passed": r.passed, "message": r.message, "resource_ids": r.resource_ids}
