"""TwinRunner: runs the open lab's checks whenever the emulator state changes (PRD F6.1) and
pushes the result to every browser as `{"type": "twin"}`, so the learner never types `labctl check`."""

import asyncio
import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ConnectionError as BotoConnectionError
from botocore.exceptions import HTTPClientError

from ..checks import CheckContext, CheckResult, run_checks
from ..config import home
from ..graph.collector import CLIENT_CONFIG, emulator_down
from ..labs import LabError, LoadedLab
from ..progress import Attempt, Progress
from ..providers import get_provider
from ..twin import TwinState, twin_state
from .hub import GraphHub

log = logging.getLogger(__name__)

CurrentLab = Callable[[], tuple[LoadedLab, Attempt] | None]
ChecksRunner = Callable[[LoadedLab], list[CheckResult]]
Record = Callable[[int, list[CheckResult]], bool]
DOWN = "the emulator is not answering; run `labctl up`"


class EmulatorSlow(Exception):
    """A request of the checks timed out or lost its connection, so a failure says nothing about the lab."""


def run_lab_checks(loaded: LoadedLab) -> list[CheckResult]:
    """The lab's checks against its emulator, bypassing api-tap so they never show as learner
    activity, with the collector's short timeouts so a hung emulator cannot stall the runner.
    Raises EmulatorSlow when any request timed out or lost its connection, like the hub, which
    does not take one slow describe for a down emulator."""
    provider = get_provider(loaded.lab.provider, loaded.lab.emulator)
    if not provider.health():
        raise ConnectionError(DOWN)
    session = boto3.session.Session()  # this turn's thread only: the default session is the collector's
    slow: list[str] = []
    lock = threading.Lock()

    def watch(caught_exception=None, **_):
        if isinstance(caught_exception, (BotoConnectionError, HTTPClientError)):
            slow.append(f"{type(caught_exception).__name__}: {caught_exception}")

    def client(service: str, credentials=None):
        with lock:  # a checker may start threads of its own
            c = provider.client(service, credentials, direct=True, config=CLIENT_CONFIG, session=session)
        c.meta.events.register("needs-retry", watch)  # emitted after every attempt, with what it raised
        return c

    results = run_checks(loaded, CheckContext(client=client))
    if slow:
        raise EmulatorSlow(slow[0])
    return results


def record_run(attempt_id: int, results: list[CheckResult]) -> bool:
    progress = Progress(home() / "progress.db")  # one connection per call: sqlite3 objects stay in their thread
    try:
        return progress.record_if_changed(attempt_id, results)
    finally:
        progress.close()


class TwinRunner:
    def __init__(self, hub: GraphHub, lab: CurrentLab, *, checks: ChecksRunner = run_lab_checks,
                 record: Record = record_run):
        self._hub, self._lab, self._checks, self._record = hub, lab, checks, record
        self.state: TwinState | None = None
        self.runs = 0  # turns that ran the checks
        self._running = False
        self._dirty = False
        self._force = False  # a turn asked for by a change, not by the poll
        self._retry = False  # the last turn could not tell, so the next poll runs the checks whatever they were
        self._tasks: set[asyncio.Task] = set()

    def trigger(self, reason: str) -> None:
        """Called by the hub: "graph" when the graph changed, "poll" on a poll that changed nothing."""
        task = asyncio.create_task(self.run(reason))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def stop(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, reason: str = "") -> None:
        """One turn at a time; a trigger during a turn gets exactly one more turn after it."""
        self._dirty = True
        self._force = self._force or reason != "poll" or self._retry
        if self._running:
            return
        self._running = True
        try:
            while self._dirty:
                self._dirty = False
                force, self._force = self._force, False
                try:
                    state = await asyncio.to_thread(self._turn, force)
                except Exception as e:  # never let a lab bug take the server down
                    log.warning("twin run failed: %s: %s", type(e).__name__, e)
                    continue
                if state is not None:
                    self._show(state)
        finally:
            self._running = False

    def _turn(self, force: bool) -> TwinState | None:
        """The new state, or None when a poll finds nothing worth running the checks for."""
        try:
            current = self._lab()
        except LabError as e:
            log.warning("twin: %s", e)
            return TwinState()
        if current is None:
            return TwinState()
        loaded, attempt = current
        last = self.state
        if not force and last is not None and (last.lab, last.attempt) == (loaded.lab.id, attempt.id) \
                and all(c.status == "passed" for c in last.checks):
            return None  # nothing left to reach; a write or a reset changes the graph and forces a turn
        graph = self._hub.graph
        if graph is None or graph.status != "ok":
            return twin_state(loaded, attempt, None, graph or emulator_down(datetime.now(timezone.utc)), note=DOWN)
        self._retry = False
        try:
            results = self._checks(loaded)
        except EmulatorSlow as e:
            log.warning("twin: emulator slow, keeping the last result: %s", e)
            self._retry = True
            if last is not None and (last.lab, last.attempt) == (loaded.lab.id, attempt.id):
                return None
            return twin_state(loaded, attempt, None, graph, note=f"the emulator was slow to answer ({e}); retrying")
        except Exception as e:
            log.warning("twin: checks did not run: %s: %s", type(e).__name__, e)
            return twin_state(loaded, attempt, None, graph, note=str(e) or type(e).__name__)
        self.runs += 1
        try:
            self._record(attempt.id, results)
        except Exception as e:  # a locked progress.db must not hide the result from the learner
            log.warning("twin: progress not recorded: %s: %s", type(e).__name__, e)
        return twin_state(loaded, attempt, results, graph)

    def _show(self, state: TwinState) -> None:
        self.state = state
        message = {"type": "twin", "twin": state.to_dict()}
        if message != self._hub.twin:
            self._hub.set_twin(message)
