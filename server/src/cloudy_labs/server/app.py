"""FastAPI app: the current graph over HTTP and live updates over a WebSocket, plus the
builder's preview and run endpoints (PRD F4) and the chat's suggestions (PRD F5)."""

import asyncio
import contextlib
import json
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

import anyio
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..builder.ec2_choices import choices
from ..builder.ops import OPS, ModifyInstanceAttribute, Op, Params, catalog, display, expectation, practice_expectation
from ..builder.runner import Runner, run_blocker
from ..builder.validate import attached_groups, validate
from ..chat import provider
from ..chat.provider import Message, ProviderError
from ..chat.settings import LlmSettings, Missing, load_settings
from ..chat.suggest import Complete, suggest
from ..config import WEB_DEV_PORT, home
from ..graph.collector import collect, region_azs
from ..graph.schema import ResourceGraph
from ..labs import LabError, LoadedLab, load_lab
from ..progress import Attempt, Progress
from .hub import GraphHub
from .tap_listener import TapListener
from .twin_runner import ChecksRunner, TwinRunner, run_lab_checks

# Only the web app may read lab state over the socket; tools without an Origin (CLI) are fine.
# Without this, any page open in the learner's browser could connect to ws://127.0.0.1.
ALLOWED_ORIGINS = {f"http://127.0.0.1:{WEB_DEV_PORT}", f"http://localhost:{WEB_DEV_PORT}"}
POLICY_VIOLATION = 1008
AZ_RETRY_S = 5.0
# Binding to loopback does not stop DNS rebinding: a page whose own name resolves to 127.0.0.1
# would read /api/graph same-origin. Requests must name the loopback host (any port).
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
CHAT_TURNS_MAX, CHAT_TURN_CHARS_MAX = 12, 8000
CHAT_SETUP = ("set LLM_BASE_URL, LLM_API_KEY, LLM_MODEL and LLM_API_FORMAT in the environment of `labctl serve` "
              "or in ~/.cloudy-labs/llm.env")

CurrentLab = Callable[[], tuple[LoadedLab, Attempt] | None]
_loaded: dict[str, LoadedLab] = {}


def current_lab() -> tuple[LoadedLab, Attempt] | None:
    """The lab of the open attempt (whatever `labctl start` opened last), read per request so a
    new `labctl start` in another terminal takes effect without restarting the server."""
    progress = Progress(home() / "progress.db")  # one connection per call: sqlite3 objects stay in their thread
    try:
        attempt = progress.current_attempt()
    finally:
        progress.close()
    if attempt is None:
        return None
    if attempt.lab_id not in _loaded:
        _loaded[attempt.lab_id] = load_lab(attempt.lab_id)
    return _loaded[attempt.lab_id], attempt


def _refuse(status: int, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"detail": message, **extra}, status_code=status)


async def guard_request(request: Request) -> Any:
    """The JSON body of a request that may change lab state or spend the learner's LLM tokens,
    or the response refusing it.

    A page on another site can POST text/plain to 127.0.0.1 without a CORS preflight, so every
    such request must come from the web app and carry a JSON body.
    """
    if request.headers.get("origin") not in ALLOWED_ORIGINS:
        return _refuse(403, "builder requests are accepted from the Cloudy Labs web app only")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        return _refuse(415, "send the request as application/json")
    try:
        return json.loads(await request.body())
    except ValueError:
        return _refuse(400, "the request body is not valid JSON")


def chat_status(settings: LlmSettings | Missing) -> dict[str, Any]:
    """Whether the chat is on, for the web app. Never the key or the base URL."""
    if isinstance(settings, Missing):
        return {"enabled": False, "missing": settings.names, **({"error": settings.error} if settings.error else {})}
    return {"enabled": True, "model": settings.model, "format": settings.api_format}


def chat_messages(body: Any) -> list[Message] | str:
    """The conversation the browser sent, or why it is refused."""
    shape = 'expected {"messages": [{"role": "user" | "assistant", "content": "..."}]}'
    if not isinstance(body, dict) or set(body) != {"messages"} or not isinstance(body["messages"], list):
        return shape
    turns = body["messages"]
    if not turns or len(turns) > CHAT_TURNS_MAX:
        return f"send between 1 and {CHAT_TURNS_MAX} messages"
    out: list[Message] = []
    for turn in turns:
        if not isinstance(turn, dict) or set(turn) != {"role", "content"} or turn["role"] not in ("user", "assistant") \
                or not isinstance(turn["content"], str):
            return shape
        if not turn["content"].strip() or len(turn["content"]) > CHAT_TURN_CHARS_MAX:
            return f"each message must have between 1 and {CHAT_TURN_CHARS_MAX} characters"
        out.append({"role": turn["role"], "content": turn["content"]})
    if out[-1]["role"] != "user":
        return "the last message must be the learner's"
    return out


def create_app(
    collector: Callable[[], ResourceGraph] = collect,
    *,
    hub: GraphHub | None = None,
    listen: bool = True,
    lab: CurrentLab = current_lab,
    runner: Runner | None = None,
    azs: Callable[[], list[str]] = region_azs,
    blocker: Callable[[], str | None] = run_blocker,
    llm: Callable[[], LlmSettings | Missing] = load_settings,
    complete: Complete = provider.complete,
    checks_runner: ChecksRunner = run_lab_checks,
) -> FastAPI:
    hub = hub or GraphHub(collector)
    listener = TapListener(hub)
    twin = TwinRunner(hub, lab, checks=checks_runner)
    runner = runner or Runner()
    zones: list[str] = []  # read once per server run, the first time the emulator answers
    zones_retry_at = 0.0  # while it does not, ask again at most every AZ_RETRY_S, not on every preview

    async def region_zones() -> list[str]:
        nonlocal zones, zones_retry_at
        if not zones and time.monotonic() >= zones_retry_at:
            zones = await asyncio.to_thread(azs)
            zones_retry_at = time.monotonic() + AZ_RETRY_S
        return zones

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await hub.start()
        hub.watch(twin.trigger)
        await twin.run("start")  # browsers that connect from here on get a twin right after the graph
        task = asyncio.create_task(listener.run()) if listen else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await hub.stop()  # first, so no refresh triggers a twin turn after the runner stopped
            await twin.stop()

    app = FastAPI(title="Cloudy Labs lab-server", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.state.hub, app.state.listener, app.state.twin = hub, listener, twin

    @app.get("/api/health")
    def health() -> dict:
        graph = hub.graph
        return {"floci": bool(graph and graph.status == "ok"), "tap": listener.connected, "version": graph.version if graph else 0}

    @app.get("/api/graph")
    def graph() -> dict:
        if hub.graph is None:
            raise HTTPException(503, "no graph collected yet")
        return hub.graph.to_dict()

    @app.get("/api/lab")
    async def lab_info() -> dict:
        try:
            current = await asyncio.to_thread(lab)
        except LabError as e:
            raise HTTPException(409, str(e)) from e
        if current is None:
            return {"id": None}
        loaded, attempt = current
        info = loaded.lab
        return {
            "id": info.id,
            "title": info.title,
            "attempt": attempt.id,
            "tasks": [{"id": t.id, "text": t.text} for t in info.tasks],
            "palette": list(info.builder.palette),
            "tags": info.builder.tags,
            "cidrs": [str(c) for c in info.cidrs],  # the blocks the lab plans to use, to suggest in the form
            "ops": catalog(list(info.builder.palette)),
            "azs": await region_zones(),
            **choices(),  # images and instanceTypes this machine can run
            "userData": info.builder.user_data,
            "runBlocker": (why := await asyncio.to_thread(blocker)),
            "canRun": why is None,
            "chat": chat_status(llm()),
        }

    async def op_request(request: Request) -> tuple[Op, Params, LoadedLab] | JSONResponse:
        """The op a builder request asks for, or the response refusing it."""
        body = await guard_request(request)
        if isinstance(body, JSONResponse):
            return body
        if not isinstance(body, dict) or set(body) != {"op", "params"} or not isinstance(body["params"], dict):
            return _refuse(422, 'expected {"op": ..., "params": {...}}')
        op = OPS.get(body["op"]) if isinstance(body["op"], str) else None
        if op is None:
            return _refuse(422, f"unknown op {body['op']!r}")
        # Either spelling: the models accept field names as well as the camelCase aliases.
        server_fields = {*op.server_fields, *(name for name, f in op.params.model_fields.items() if f.alias in op.server_fields)}
        if refused := sorted(server_fields & set(body["params"])):
            return _refuse(422, f"{op.name}: wrong parameters: {', '.join(refused)} (the server fills these in)")
        try:
            params = op.params.model_validate(body["params"])
        except ValidationError as e:
            fields = [".".join(map(str, err["loc"])) for err in e.errors()]
            return _refuse(422, f"{op.name}: wrong parameters: {', '.join(fields)}")
        try:
            current = await asyncio.to_thread(lab)
        except LabError as e:
            return _refuse(409, str(e))
        if current is None:
            return _refuse(409, "no lab is open; run `labctl start <lab>` first")
        loaded = current[0]
        if op.palette_kind() not in loaded.lab.builder.palette:
            return _refuse(422, f"{loaded.lab.id} does not offer {op.name} in its builder")
        if hub.graph is None or hub.graph.status != "ok":
            return _refuse(503, "the emulator is not answering; run `labctl up`")
        return op, params, loaded

    async def checked(request: Request, *, fresh: bool = False) -> tuple[Op, Params, list[str], list[dict]] | JSONResponse:
        """`fresh`: about to run, so read the instance's groups from a new collect rather than the
        last graph, which may not show a group attached a moment ago; `--groups` would drop it."""
        parsed = await op_request(request)
        if isinstance(parsed, JSONResponse):
            return parsed
        op, params, loaded = parsed
        graph = hub.graph
        if isinstance(params, ModifyInstanceAttribute):
            if fresh:
                graph = await asyncio.to_thread(hub.collect_now)
                if graph.status != "ok":
                    return _refuse(503, "the emulator is not answering; run `labctl up`")
            params = params.model_copy(update={"current_groups": attached_groups(graph, params.instance_id)})
        argv = op.argv(params, loaded.lab.builder.tags)
        problems = validate(op.name, params, graph, await region_zones(), choices())
        return op, params, argv, [asdict(p) for p in problems]

    @app.post("/api/preview")
    async def preview(request: Request) -> Any:
        result = await checked(request)
        if isinstance(result, JSONResponse):
            return result
        op, params, argv, problems = result
        return {"command": display(argv), "argv": argv, "problems": problems,
                "practiceExpect": practice_expectation(op, params)}

    @app.post("/api/run")
    async def run(request: Request) -> Any:
        result = await checked(request, fresh=True)
        if isinstance(result, JSONResponse):
            return result
        op, params, argv, problems = result
        if problems:  # validated again here: a preview the browser holds may be stale
            return _refuse(409, "the command was not run", command=display(argv), problems=problems)
        if why := await asyncio.to_thread(blocker):
            return _refuse(503, why)
        if runner.busy:  # it was validated against a graph the running command is about to change
            return _refuse(409, "another builder command is still running; wait for it, then press Run again")
        before = hub.graph.version if hub.graph else 0
        outcome = await runner.run(argv)  # no await between the check and taking the lock
        hub.notify("builder")  # do not rely on api-tap alone to bring the new graph
        expect = expectation(op, params, outcome.stdout, before) if outcome.exit_code == 0 else None
        return {"command": display(argv), "argv": argv, **outcome.to_dict(), "expect": expect}

    @app.post("/api/chat")
    async def chat(request: Request) -> Any:
        """Suggested steps for the learner's question. Suggests only: nothing runs here (F5.4)."""
        body = await guard_request(request)
        if isinstance(body, JSONResponse):
            return body
        messages = chat_messages(body)
        if isinstance(messages, str):
            return _refuse(422, messages)
        try:
            current = await asyncio.to_thread(lab)
        except LabError as e:
            return _refuse(409, str(e))
        if current is None:
            return _refuse(409, "no lab is open; run `labctl start <lab>` first")
        graph = hub.graph
        if graph is None or graph.status != "ok":
            return _refuse(503, "the emulator is not answering; run `labctl up`")
        settings = await asyncio.to_thread(llm)
        if isinstance(settings, Missing):
            why = settings.error or f"missing {', '.join(settings.names)}"
            return _refuse(409, f"the chat is not set up ({why}); {CHAT_SETUP}")
        try:
            result = await suggest(messages, lab=current[0].lab, graph=graph, azs=await region_zones(),
                                   choices=choices(), settings=settings, complete=complete)
        except ProviderError as e:
            return _refuse(502, provider.redact(str(e), settings))  # already redacted; once more costs nothing
        return result.to_dict()

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
