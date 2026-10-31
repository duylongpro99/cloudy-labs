"""TwinRunner with a fake checks runner on top of a real GraphHub."""

import asyncio
import threading
import time
from pathlib import Path

from cloudy_labs.checks import CheckResult
from cloudy_labs.labs import LabError, load_lab
from cloudy_labs.progress import Attempt
from cloudy_labs.server.hub import GraphHub
from cloudy_labs.server import twin_runner
from cloudy_labs.server.twin_runner import EmulatorSlow, TwinRunner, run_lab_checks
from test_hub import FakeCollector, drain, run

LAB06 = load_lab("fixture-lab-06", Path(__file__).parent / "fixtures" / "labs")
CHECK_IDS = [c.id for c in LAB06.lab.checks]


class FakeChecks:
    def __init__(self, delay: float = 0.0):
        self.passed: set[str] = set()
        self.calls = 0
        self.delay = delay
        self.error: Exception | None = None
        self.lock = threading.Lock()

    def __call__(self, loaded):
        with self.lock:
            self.calls += 1
        time.sleep(self.delay)
        if self.error:
            raise self.error
        return [CheckResult(c in self.passed, "ok" if c in self.passed else "not yet", [], c) for c in CHECK_IDS]


class Setup:
    def __init__(self, delay: float = 0.0):
        self.collector = FakeCollector()
        self.checks = FakeChecks(delay)
        self.lab: object = (LAB06, Attempt(1, "fixture-lab-06", ""))
        self.recorded: list[tuple[int, list[CheckResult]]] = []
        self.hub = GraphHub(self.collector, debounce=0.01, poll=60)
        self.runner = TwinRunner(self.hub, self.current, checks=self.checks, record=self.record)

    def current(self):
        if isinstance(self.lab, Exception):
            raise self.lab
        return self.lab

    def record(self, attempt_id, results):
        self.recorded.append((attempt_id, results))
        return True

    async def start(self) -> asyncio.Queue:
        await self.hub.start()
        self.hub.watch(self.runner.trigger)
        await self.runner.run("start")
        return self.hub.subscribe()

    async def settle(self, seconds: float = 0.3) -> None:
        await asyncio.sleep(seconds)

    async def stop(self) -> None:
        await self.runner.stop()
        await self.hub.stop()


def twins(messages: list) -> list[dict]:
    return [m["twin"] for m in messages if m and m["type"] == "twin"]


def statuses(twin: dict) -> dict[str, str]:
    return {c["id"]: c["status"] for c in twin["checks"]}


def test_a_new_graph_runs_the_checks_and_sends_one_twin():
    async def main():
        s = Setup()
        queue = await s.start()
        first = drain(queue)
        s.checks.passed = {"vpc-exists"}
        s.collector.vpcs = ["vpc-1"]
        await s.hub.refresh()
        await s.settle()
        later = drain(queue)
        await s.stop()
        return s, first, later

    s, first, later = run(main())
    assert [m["type"] for m in first] == ["graph", "twin"]
    assert set(statuses(first[1]["twin"]).values()) == {"failed"}
    assert [m["type"] for m in later] == ["graph", "twin"]
    assert statuses(later[1]["twin"])["vpc-exists"] == "passed"
    assert later[1]["twin"]["lab"] == "fixture-lab-06" and later[1]["twin"]["attempt"] == 1
    assert [a for a, _ in s.recorded] == [1, 1]


def test_unchanged_results_send_nothing():
    async def main():
        s = Setup()
        queue = await s.start()
        drain(queue)
        s.collector.vpcs = ["vpc-1"]  # a change the checks do not care about
        await s.hub.refresh()
        await s.settle()
        out = drain(queue)
        await s.stop()
        return s, out

    s, out = run(main())
    assert s.checks.calls == 2 and [m["type"] for m in out] == ["graph"]


def test_triggers_during_a_turn_cost_exactly_one_more_turn():
    async def main():
        s = Setup(delay=0.2)
        await s.start()
        start = s.checks.calls
        s.runner.trigger("graph")
        await asyncio.sleep(0.05)  # the turn is running
        s.runner.trigger("graph")
        s.runner.trigger("graph")
        await s.settle(0.8)
        await s.stop()
        return s.checks.calls - start

    assert run(main()) == 2


def test_emulator_down_marks_every_check_pending_without_running_them():
    async def main():
        s = Setup()
        queue = await s.start()
        drain(queue)
        s.collector.down = True
        await s.hub.refresh()
        await s.settle()
        out = twins(drain(queue))
        await s.stop()
        return s, out

    s, out = run(main())
    assert s.checks.calls == 1  # only the turn at start
    assert set(statuses(out[-1]).values()) == {"pending"}
    assert "labctl up" in out[-1]["checks"][0]["message"]
    assert out[-1]["bound"] == {} and len(out[-1]["ghosts"]) == len(LAB06.lab.target.nodes)


def test_poll_reruns_while_a_check_fails_and_stops_once_all_pass():
    async def main():
        s = Setup()
        await s.start()
        await s.hub.refresh("poll")  # graph unchanged: a poll turn
        await s.settle()
        after_failing = s.checks.calls
        s.checks.passed = set(CHECK_IDS)
        await s.hub.refresh("poll")
        await s.settle()
        all_passed = s.checks.calls
        await s.hub.refresh("poll")
        await s.settle()
        await s.stop()
        return after_failing, all_passed, s.checks.calls, s.runner.state

    after_failing, all_passed, final, state = run(main())
    assert after_failing == 2 and all_passed == 3 and final == 3
    assert {c.status for c in state.checks} == {"passed"}


def test_a_new_attempt_reruns_on_poll_even_when_everything_passed():
    """`labctl reset` in another terminal opens a new attempt; the twin follows it."""
    async def main():
        s = Setup()
        s.checks.passed = set(CHECK_IDS)
        queue = await s.start()
        drain(queue)
        s.lab = (LAB06, Attempt(2, "fixture-lab-06", ""))
        s.checks.passed = set()
        await s.hub.refresh("poll")
        await s.settle()
        out = twins(drain(queue))
        await s.stop()
        return s, out

    s, out = run(main())
    assert out[-1]["attempt"] == 2 and set(statuses(out[-1]).values()) == {"failed"}
    assert [a for a, _ in s.recorded] == [1, 2]


def test_failures_inside_a_turn_do_not_stop_the_runner():
    async def main():
        s = Setup()
        queue = await s.start()
        drain(queue)
        s.checks.error = ConnectionError("the emulator is not answering; run `labctl up`")
        await s.runner.run("graph")
        broken_checks = twins(drain(queue))
        s.lab = LabError("lab 'gone' not found")
        await s.runner.run("graph")
        broken_lab = twins(drain(queue))
        s.lab, s.checks.error = None, None
        await s.runner.run("graph")
        no_lab = twins(drain(queue))
        await s.stop()
        return broken_checks, broken_lab, no_lab

    broken_checks, broken_lab, no_lab = run(main())
    assert set(statuses(broken_checks[0]).values()) == {"pending"}
    assert "labctl up" in broken_checks[0]["checks"][0]["message"]
    assert broken_lab == [{"lab": None, "attempt": None, "checks": [], "ghosts": [], "bound": {}}]
    assert no_lab == []  # same empty state: not sent again


def test_a_slow_emulator_keeps_the_last_result_and_the_next_poll_tries_again():
    async def main():
        s = Setup()
        s.checks.passed = set(CHECK_IDS)
        queue = await s.start()
        drain(queue)
        s.checks.error = EmulatorSlow("ReadTimeoutError: Read timeout on endpoint URL")
        s.collector.vpcs = ["vpc-1"]  # a write: the turn is forced
        await s.hub.refresh("tap")
        await s.settle()
        during = twins(drain(queue))
        s.checks.error = None
        s.checks.passed = {"vpc-exists"}
        await s.hub.refresh("poll")  # everything passed last time, yet the poll runs the checks
        await s.settle()
        after = twins(drain(queue))
        await s.stop()
        return s, during, after

    s, during, after = run(main())
    assert during == [] and [a for a, _ in s.recorded] == [1, 1]  # start, then the poll; nothing for the slow turn
    assert s.checks.calls == 3
    assert statuses(after[-1])["vpc-exists"] == "passed" and statuses(after[-1])["igw-attached"] == "failed"


def test_a_slow_emulator_on_a_new_attempt_shows_every_check_pending():
    async def main():
        s = Setup()
        s.checks.error = EmulatorSlow("ConnectTimeoutError: Connect timeout")
        queue = await s.start()
        out = twins(drain(queue))
        await s.stop()
        return s, out

    s, out = run(main())
    assert set(statuses(out[-1]).values()) == {"pending"} and "slow" in out[-1]["checks"][0]["message"]
    assert s.recorded == []


class Unreachable:
    """Answers health, but every request fails to connect, as when the emulator stalls."""

    def health(self) -> bool:
        return True

    def client(self, service, credentials=None, *, direct, config, session):
        return session.client(service, endpoint_url="http://127.0.0.1:9", region_name="us-east-1",
                              aws_access_key_id="test", aws_secret_access_key="test", config=config)


def test_requests_that_cannot_connect_raise_emulator_slow_not_failed_checks(monkeypatch):
    monkeypatch.setattr(twin_runner, "get_provider", lambda *_: Unreachable())
    try:
        run_lab_checks(LAB06)
    except EmulatorSlow as e:
        assert "EndpointConnectionError" in str(e)
    else:
        raise AssertionError("no EmulatorSlow")
