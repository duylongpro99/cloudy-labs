"""Follow api-tap's event stream: every write the learner makes triggers a graph refresh."""

import asyncio
import json
import logging

import httpx

from ..config import HOST, TAP_EVENTS_PORT
from .hub import GraphHub

log = logging.getLogger(__name__)

EVENTS_URL = f"http://{HOST}:{TAP_EVENTS_PORT}/events"
BACKOFF_S = (0.5, 5.0)  # first and longest wait between reconnects
READ_TIMEOUT_S = 40.0  # api-tap pings every 15 s, so silence this long means a dead stream


class TapListener:
    def __init__(self, hub: GraphHub, url: str = EVENTS_URL):
        self.hub, self.url = hub, url
        self.connected = False

    def handle(self, event: dict) -> None:
        write = bool(event.get("write"))
        self.hub.broadcast({"type": "api-event", "service": event.get("service"), "action": event.get("action"), "seq": event.get("seq"), "write": write})
        if write:
            self.hub.notify("tap")

    async def run(self) -> None:
        wait = BACKOFF_S[0]
        while True:
            try:
                timeout = httpx.Timeout(5.0, read=READ_TIMEOUT_S)
                async with httpx.AsyncClient(timeout=timeout) as client, client.stream("GET", self.url) as resp:
                    resp.raise_for_status()
                    self.connected, wait = True, BACKOFF_S[0]
                    self.hub.notify("tap-connected")  # writes made while we were away were missed
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                self.handle(json.loads(line[6:]))
                            except ValueError:
                                log.warning("ignoring malformed event from api-tap: %r", line)
            except httpx.HTTPError as e:
                log.debug("api-tap stream unavailable: %s", e)
            finally:
                self.connected = False
            await asyncio.sleep(wait)
            wait = min(wait * 2, BACKOFF_S[1])
