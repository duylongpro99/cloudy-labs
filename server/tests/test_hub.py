import asyncio
import threading
import time
from datetime import datetime, timezone

from cloudy_labs.graph.collector import emulator_down
from cloudy_labs.graph.schema import ResourceGraph
from cloudy_labs.server.hub import GraphHub


def graph(*vpcs: str) -> ResourceGraph:
    return ResourceGraph.model_validate({
        "takenAt": f"2026-10-29T00:00:{time.time() % 60:09.6f}Z",  # differs every time; must not count as a change
        "nodes": [{"id": "us-east-1", "kind": "region", "label": "us-east-1"}]
        + [{"id": v, "kind": "vpc", "label": v} for v in vpcs],
        "contains": [{"parent": "us-east-1", "child": v} for v in vpcs],
        "edges": [],
    })


class FakeCollector:
    def __init__(self, delay: float = 0.0):
        self.vpcs: list[str] = []
        self.calls = 0
        self.delay = delay
        self.fail = False  # raise, as a timeout or a collector bug would
        self.down = False  # answer the way collect() does when Floci refuses connections
        self.lock = threading.Lock()

    def __call__(self) -> ResourceGraph:
        with self.lock:
            self.calls += 1
        time.sleep(self.delay)
        if self.fail:
            raise ConnectionError("floci went away")
        if self.down:
            return emulator_down(datetime.now(timezone.utc), reason="EndpointConnectionError")
        return graph(*self.vpcs)


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, 10))


def drain(queue: asyncio.Queue) -> list:
    out = []
    while not queue.empty():
        out.append(queue.get_nowait())
    return out


def test_burst_of_writes_costs_one_or_two_collects():
    async def main():
        collector = FakeCollector(delay=0.02)
        hub = GraphHub(collector, debounce=0.15, poll=60)
        await hub.start()
        start = collector.calls
        for _ in range(10):
            hub.notify()
            await asyncio.sleep(0.01)  # 10 writes in ~100 ms
        await asyncio.sleep(0.5)
        await hub.stop()
        return collector.calls - start

    assert 1 <= run(main()) <= 2


def test_write_during_collect_gets_exactly_one_more_collect():
    async def main():
        collector = FakeCollector(delay=0.2)
        hub = GraphHub(collector, debounce=0.01, poll=60)
        await hub.start()
        start = collector.calls
        hub.notify()
        await asyncio.sleep(0.05)  # first collect is now running
        hub.notify()
        hub.notify()
        await asyncio.sleep(0.8)
        await hub.stop()
        return collector.calls - start

    assert run(main()) == 2


def test_a_poll_during_a_collect_still_reaches_the_watchers():
    async def main():
        collector = FakeCollector(delay=0.2)
        hub = GraphHub(collector, poll=60)
        await hub.start()
        calls: list[str] = []
        hub.watch(calls.append)
        write = asyncio.create_task(hub.refresh("tap"))
        await asyncio.sleep(0.05)
        await hub.refresh("poll")  # arrives mid-collect, graph unchanged
        await write
        await hub.stop()
        return calls

    assert run(main()) == ["poll"]


def test_only_changed_graphs_are_published_and_versioned():
    async def main():
        collector = FakeCollector()
        hub = GraphHub(collector, poll=60)
        await hub.start()
        queue = hub.subscribe()
        first = drain(queue)
        await hub.refresh()  # nothing changed
        unchanged = drain(queue)
        collector.vpcs = ["vpc-1"]
        await hub.refresh()
        changed = drain(queue)
        await hub.stop()
        return first, unchanged, changed

    first, unchanged, changed = run(main())
    assert [m["graph"]["version"] for m in first] == [1]
    assert unchanged == []
    assert [m["graph"]["version"] for m in changed] == [2]
    assert [n["id"] for n in changed[0]["graph"]["nodes"]] == ["us-east-1", "vpc-1"]


def test_failing_collector_publishes_emulator_down_once_then_recovers():
    async def main():
        collector = FakeCollector()
        hub = GraphHub(collector, poll=0.05, down_poll=0.05)
        await hub.start()
        queue = hub.subscribe()
        drain(queue)
        collector.fail = True
        await asyncio.sleep(0.3)  # several polls while down
        down = drain(queue)
        collector.fail = False
        await asyncio.sleep(0.2)
        back = drain(queue)
        await hub.stop()
        return down, back

    down, back = run(main())
    assert [m["graph"]["status"] for m in down] == ["emulator-down"]
    assert [m["graph"]["status"] for m in back] == ["ok"]


def test_one_failed_collect_keeps_the_scene():
    async def main():
        collector = FakeCollector()
        hub = GraphHub(collector, poll=60)
        await hub.start()
        queue = hub.subscribe()
        drain(queue)
        collector.fail = True
        await hub.refresh("tap")
        after_one = (drain(queue), hub.graph.status)
        await hub.refresh("tap")
        after_two = [m["graph"]["status"] for m in drain(queue)]
        await hub.stop()
        return after_one, after_two

    after_one, after_two = run(main())
    assert after_one == ([], "ok")
    assert after_two == ["emulator-down"]


def test_stop_cancels_a_debounced_refresh_that_is_collecting():
    async def main():
        collector = FakeCollector()
        hub = GraphHub(collector, poll=60, debounce=0.01)
        await hub.start()
        collector.delay = 0.5
        hub.notify()
        await asyncio.sleep(0.1)  # the window has closed and the collect is running
        pending = set(hub._debounces)
        await hub.stop()
        return pending

    pending = run(main())
    assert len(pending) == 1 and all(t.cancelled() for t in pending)


def test_floci_refusing_connections_shows_at_once():
    async def main():
        collector = FakeCollector()
        hub = GraphHub(collector, poll=60)
        await hub.start()
        queue = hub.subscribe()
        drain(queue)
        collector.down = True
        await hub.refresh("tap")
        got = [m["graph"]["status"] for m in drain(queue)]
        await hub.stop()
        return got

    assert run(main()) == ["emulator-down"]


def test_slow_client_is_dropped():
    async def main():
        collector = FakeCollector()
        hub = GraphHub(collector, poll=60)
        await hub.start()
        queue = hub.subscribe()
        for i in range(200):
            hub.broadcast({"type": "graph", "seq": i})
        dropped = queue not in hub._clients
        last = drain(queue)
        await hub.stop()
        return dropped, last

    dropped, last = run(main())
    assert dropped and last == [None]


def test_burst_of_api_events_skips_events_but_keeps_the_browser():
    async def main():
        hub = GraphHub(FakeCollector(), poll=60)
        await hub.start()
        queue = hub.subscribe()
        for i in range(200):
            hub.broadcast({"type": "api-event", "seq": i})
        kept = queue in hub._clients
        got = drain(queue)
        await hub.stop()
        return kept, got

    kept, got = run(main())
    assert kept and len(got) == 64 and got[0]["type"] == "graph" and got[-1]["seq"] == 62


def test_watchers_hear_new_graphs_and_quiet_polls():
    async def main():
        collector = FakeCollector()
        hub = GraphHub(collector, debounce=0.01, poll=60)
        await hub.start()
        heard: list[str] = []
        hub.watch(heard.append)
        await hub.refresh("tap")  # nothing changed, not a poll
        await hub.refresh("poll")
        collector.vpcs = ["vpc-1"]
        await hub.refresh("poll")
        await hub.stop()
        return heard

    assert run(main()) == ["poll", "graph"]


def test_new_browser_gets_the_graph_then_the_twin():
    async def main():
        hub = GraphHub(FakeCollector(), poll=60)
        await hub.start()
        hub.set_twin({"type": "twin", "twin": {"lab": None}})
        messages = drain(hub.subscribe())
        await hub.stop()
        return messages

    assert [m["type"] for m in run(main())] == ["graph", "twin"]
