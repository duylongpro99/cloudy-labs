"""GraphHub: keeps the latest resource graph and pushes changes to every connected browser."""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from ..graph.collector import emulator_down
from ..graph.schema import ResourceGraph

log = logging.getLogger(__name__)

DEBOUNCE_S = 0.15  # write events closer together than this cost one collect
POLL_S = 5.0  # safety net for changes that do not go through api-tap
DOWN_POLL_S = 1.0  # while Floci is down, notice quickly when it is back (after `labctl reset`)
# Failed collects in a row before a live scene turns into "emulator down" when the failure may
# be transient (a timeout, an unexpected error): one slow describe while Floci starts instance
# containers must not wipe the scene and rebuild it. Floci refusing connections shows at once.
DOWN_AFTER = 2
CLIENT_QUEUE = 64  # messages buffered per browser before it counts as too slow and is dropped

Message = dict[str, Any]


class GraphHub:
    def __init__(
        self,
        collect: Callable[[], ResourceGraph],
        *,
        debounce: float = DEBOUNCE_S,
        poll: float = POLL_S,
        down_poll: float = DOWN_POLL_S,
    ):
        self._collect = collect
        self._debounce, self._poll, self._down_poll = debounce, poll, down_poll
        self.graph: ResourceGraph | None = None
        self.collects = 0
        self._hash: str | None = None
        self._clients: set[asyncio.Queue] = set()
        self._timer: asyncio.Task | None = None
        self._debounces: set[asyncio.Task] = set()
        self._running = False
        self._dirty = False
        self._failures = 0  # possibly transient failed collects in a row
        self._poller: asyncio.Task | None = None

    async def start(self) -> None:
        await self.refresh("start")
        self._poller = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        # Debounce tasks outlive their window while they collect, so cancel every one still pending.
        tasks = [t for t in (self._poller, *self._debounces) if t]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for queue in list(self._clients):
            self._close(queue)

    # -- clients ---------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        """A queue of messages for one browser, starting with the current graph. None means: disconnect."""
        queue: asyncio.Queue = asyncio.Queue(CLIENT_QUEUE)
        if self.graph is not None:
            queue.put_nowait(self._graph_message())
        self._clients.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._clients.discard(queue)

    def broadcast(self, message: Message) -> None:
        for queue in list(self._clients):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                if message["type"] == "api-event":
                    continue  # cosmetic: a burst of writes may outrun the socket; skip it, keep the browser
                log.warning("dropping a browser that stopped reading")
                self._close(queue)

    def _close(self, queue: asyncio.Queue) -> None:
        self.unsubscribe(queue)
        while not queue.empty():
            queue.get_nowait()
        queue.put_nowait(None)

    # -- refreshing ------------------------------------------------------------

    def notify(self, reason: str = "tap") -> None:
        """A write happened: refresh soon, folding a burst of writes into one collect."""
        if self._timer is None or self._timer.done():
            self._timer = asyncio.create_task(self._after_debounce(reason))
            self._debounces.add(self._timer)
            self._timer.add_done_callback(self._debounces.discard)

    async def _after_debounce(self, reason: str) -> None:
        await asyncio.sleep(self._debounce)
        self._timer = None  # writes from here on start a new window
        await self.refresh(reason)

    async def refresh(self, reason: str = "") -> None:
        """Collect and publish; if asked again while collecting, collect exactly once more after."""
        self._dirty = True
        if self._running:
            return
        self._running = True
        try:
            while self._dirty:
                self._dirty = False
                self._publish(*await asyncio.to_thread(self._safe_collect))
        finally:
            self._running = False

    def collect_now(self) -> ResourceGraph:
        """A graph collected now and not published, for a caller that cannot act on a stale one.
        Blocking: call it from a thread."""
        return self._safe_collect()[0]

    def _safe_collect(self) -> tuple[ResourceGraph, bool]:
        """The graph, and whether it stands for a failure that may be transient."""
        self.collects += 1
        try:
            return self._collect(), False
        except Exception as e:  # never let a collector bug take the server down; show it as down
            log.warning("collect failed: %s: %s", type(e).__name__, e)
            return emulator_down(datetime.now(timezone.utc), reason=type(e).__name__), True

    def _publish(self, graph: ResourceGraph, transient: bool = False) -> None:
        if not transient:
            self._failures = 0
        else:
            self._failures += 1
            if self.graph is not None and self.graph.status == "ok" and self._failures < DOWN_AFTER:
                return  # keep the last good graph; the poll loop retries soon
        digest = graph.content_hash()
        if digest == self._hash:
            return
        version = self.graph.version + 1 if self.graph else 1
        self._hash = digest
        self.graph = graph.model_copy(update={"version": version})
        self.broadcast(self._graph_message())

    def _graph_message(self) -> Message:
        return {"type": "graph", "graph": self.graph.to_dict()}

    async def _poll_loop(self) -> None:
        while True:
            down = self._failures > 0 or (self.graph is not None and self.graph.status != "ok")
            await asyncio.sleep(self._down_poll if down else self._poll)
            await self.refresh("poll")
