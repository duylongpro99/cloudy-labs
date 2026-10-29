"""FastAPI app: the current graph over HTTP and live updates over a WebSocket."""

import asyncio
import contextlib
from collections.abc import Callable
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..config import WEB_DEV_PORT
from ..graph.collector import collect
from ..graph.schema import ResourceGraph
from .hub import GraphHub
from .tap_listener import TapListener

# Only the web app may read lab state over the socket; tools without an Origin (CLI) are fine.
# Without this, any page open in the learner's browser could connect to ws://127.0.0.1.
ALLOWED_ORIGINS = {f"http://127.0.0.1:{WEB_DEV_PORT}", f"http://localhost:{WEB_DEV_PORT}"}
POLICY_VIOLATION = 1008
# Binding to loopback does not stop DNS rebinding: a page whose own name resolves to 127.0.0.1
# would read /api/graph same-origin. Requests must name the loopback host (any port).
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


def create_app(collector: Callable[[], ResourceGraph] = collect, *, hub: GraphHub | None = None, listen: bool = True) -> FastAPI:
    hub = hub or GraphHub(collector)
    listener = TapListener(hub)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await hub.start()
        task = asyncio.create_task(listener.run()) if listen else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await hub.stop()

    app = FastAPI(title="Cloudy Labs lab-server", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.state.hub, app.state.listener = hub, listener

    @app.get("/api/health")
    def health() -> dict:
        graph = hub.graph
        return {"floci": bool(graph and graph.status == "ok"), "tap": listener.connected, "version": graph.version if graph else 0}

    @app.get("/api/graph")
    def graph() -> dict:
        if hub.graph is None:
            raise HTTPException(503, "no graph collected yet")
        return hub.graph.to_dict()

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        origin = socket.headers.get("origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            await socket.close(code=POLICY_VIOLATION)
            return
        await socket.accept()
        queue = hub.subscribe()

        dropped = False

        async def send() -> None:
            nonlocal dropped
            try:
                while (message := await queue.get()) is not None:
                    await socket.send_json(message)
            except WebSocketDisconnect:  # the tab closed while a message was in flight
                tasks.cancel_scope.cancel()
                return
            dropped = True  # the hub gave up on this browser
            tasks.cancel_scope.cancel()

        async def receive() -> None:  # nothing is accepted from the browser; this only notices it leaving
            while (await socket.receive())["type"] != "websocket.disconnect":
                pass
            tasks.cancel_scope.cancel()

        try:
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(send)
                tasks.start_soon(receive)
            if dropped:
                await socket.close()
        finally:
            hub.unsubscribe(queue)

    return app
