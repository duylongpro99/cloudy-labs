# Code review: M2 resource graph, collector, live scene (uncommitted working tree)

Date: 2026-10-29. Read-only review. Ran one scratch reproduction script against `ApiTap` with a local stub upstream (no docker, no dev servers). Did not re-run the suites the lead had already run.

## Scope
- Server: `tap/api_tap.py`, `graph/{collector,schema,host_ports}.py`, `server/{hub,app,tap_listener}.py`, diffs in `cli.py`, `config.py`, `emulator/{compose.yaml,stack.py,orphans.py}`, `providers/aws.py`, `pyproject.toml`
- Web: `src/graph/*`, `src/scene/{live-scene,api-fly-layer,property-panel,scene-rig,edge-layer,tray-layer,layout,object-placements}.tsx/ts`, `aws-objects/{aws-object-layer.tsx,entrance.ts}`, `app.tsx`, `vite.config.ts`
- Focus: proxy correctness and header handling, hub/listener concurrency, local-server exposure, React/three lifecycle, whether the schema and parser agree

## Overall assessment
The core design holds up. The hub's single-flight refresh with a dirty flag is correct for one asyncio loop. The tap keeps `Host`/`Authorization` intact, so SigV4 stays valid. The WS origin allowlist is enforced before `accept`. The web client guards against stale sockets (`ws !== sock`) and clears its timers on unmount. Particles and edge meshes are R3F-owned, so they get disposed. The schema and the parser agree: kinds, edge kinds, the default `label`, and `props`/`warnings` always being present. I found one proxy correctness regression (HEAD responses), one destructive cleanup scope issue, and several robustness gaps in how failures turn into what the browser shows.

---

## High

### H1. api-tap rewrites `Content-Length` to 0 on HEAD (and 304) responses
`server/src/cloudy_labs/tap/api_tap.py:173-187`

`resp.read()` returns `b""` for HEAD/304. The handler drops the upstream `Content-Length` (line 182) and sends `len(data)` = 0 (line 184).

**Reproduced** with a stub upstream that answers HEAD with `Content-Length: 12345`:
```
direct HEAD CL: 12345
via tap HEAD CL: 0
via tap 304 CL: 0 304
```
**Impact:** In M1 the learner's CLI and the checkers talked to Floci directly. They now go through the tap (`providers/aws.py:19`, `PORTS["floci"] = API_PORT`), so this is a regression. `aws s3api head-object` / boto3 `head_object()["ContentLength"]` now returns 0. Any S3 lab or checker that asserts object size through HEAD will fail. Tools that size downloads from HeadObject (s3transfer) also get a wrong size.

**Fix:** for HEAD and for 1xx/204/304 statuses, pass the upstream `Content-Length` through unchanged instead of recomputing it:
```python
no_body = self.command == "HEAD" or resp.status in (204, 304) or 100 <= resp.status < 200
for k, v in resp.getheaders():
    lk = k.lower()
    if lk in HOP_BY_HOP or (lk == "content-length" and not no_body):
        continue
    self.send_header(k, v)
if not no_body:
    self.send_header("Content-Length", str(len(data)))
```
Add a `test_api_tap.py` case: a stub upstream HEAD with a non-zero `Content-Length` must reach the client unchanged.

### H2. Orphan cleanup now also deletes another Floci's port-forwarder containers (owner-label scope was already too wide)
`server/src/cloudy_labs/emulator/orphans.py:18,40`, called from `stack.py:94` (`recreate_floci`, which runs on **every `labctl reset`**), `:119` and `:137-139`.

`FORWARDER_FILTERS` (`label=floci_emulator=floci-aws` + `name=floci-aws-ec2-fwd-`) matches the socat forwarders of **any** Floci on the machine, and the code comment says so. `owner_filters(4566)` has the same problem. The note `floci-port-move.md` shows that `io.floci.owner` is the port inside the container (4566 for every Floci with default settings), not the host port. Moving labctl's Floci to host 4567 is also what now lets a second Floci run beside it. Before M2, both Flocis would have needed host 4566.

**Failure scenario:** This machine has a separate `floci` container (`docker ps -a` shows `floci`, `floci-ui`). If that Floci has EC2 instances, `labctl reset <lab>` or `labctl down` removes its instance containers, VPC networks, volumes and, new in M2, its forwarders. The user said those containers must not be touched.

**Fix (pick one, then verify with a docker test that runs a second Floci):**
- Scope by membership in the compose project. Instance containers join the compose network (see the `down()` comment), so `docker ps -a --filter network=cloudy-labs_default` can filter instances. Check whether forwarders attach to the same network.
- Or, before `recreate_floci`/`down`, list instance ids from labctl's Floci (direct `describe_instances`) and remove only `floci-aws-ec2-{,fwd-}<id>*`. Networks would be filtered by the VPC ids from `describe_vpcs`.
- At minimum, give labctl's Floci a distinct internal port (e.g. `FLOCI_PORT` env inside the container, if Floci supports it), so its `io.floci.owner` differs from a stock Floci.

---

## Medium

### M1. A single transient collect failure wipes the whole scene, then rebuilds it
`collector.py:277-281`, `hub.py:105-111`, `web/src/graph/graph-to-scene.ts:23-25`

Any `BotoCoreError` (e.g. `ReadTimeoutError` with `read_timeout=5`, `max_attempts=1`) returns `emulator_down`. `_safe_collect` also turns any other exception into `emulator-down`, including a `ClientError` from `describe_instance_attribute` (e.g. `InvalidInstanceID.NotFound` when an instance is terminated between `describe_instances` and the attribute call, `collector.py:263`) and a schema `ValidationError`. The web then reduces the scene to the region tray. Every object plays its exit animation, then everything plays its entrance animation again on the next good collect, and the version goes up twice.

**Scenario:** Floci is busy launching instance containers. One of the 9 parallel describes exceeds 5 s, and the learner sees the whole architecture vanish and re-enter.

**Fix:**
- In `recent_user_data`, catch `ClientError` per instance and skip that instance.
- In the hub, publish `emulator-down` only after N consecutive failures (e.g. 2–3) or after a time threshold, and keep the last good graph until then.
- Optionally, on the web side, keep the last good nodes (dimmed) while `status === 'emulator-down'` instead of collapsing them. Collapsing is the right behaviour after `labctl reset`, and the hub threshold already covers that case.

### M2. A burst of api-events disconnects healthy browsers
`hub.py:66-72` (`CLIENT_QUEUE = 64`), `tap_listener.py:24-28, 39-42`

`aiter_lines()` yields every line already buffered in one read without awaiting, so `handle()` → `broadcast()` runs back-to-back while the WS `send()` task gets no chance to drain. More than 64 events in one chunk (the tap reconnecting after a burst, a scripted `for` loop of CLI writes, terraform) fill the queue. The hub then treats a fully responsive browser as "stopped reading" and closes it. The browser reconnects after 500 ms and replays the graph, but the fly animations for that burst are lost and a warning is logged.

**Fix:** `api-event` is cosmetic, so it can be lossy. On `QueueFull`, drop the event instead of the client. Keep the drop-client policy for `graph` messages only. Alternatively, put the newest graph in a separate one-slot slot rather than in the queue.

### M3. `docker` CLI calls have no timeout; one hang stops all graph updates
`emulator/docker.py:12` (`subprocess.run` without `timeout`), reached from `collector.py:285` → `host_ports.py:33` on every collect while any instance reports `127.0.0.1`

`GraphHub.refresh` holds `_running = True` for the whole `to_thread(collect)` (`hub.py:97-103`). If `docker ps` hangs (Docker Desktop under memory pressure is a known case), every later `refresh()` returns early (`hub.py:95-96`). The scene then stays frozen with no "emulator-down" signal until the process returns, and it may never return. `labctl serve` startup (`hub.start()` awaits the first collect) can hang the same way.

**Fix:** pass `timeout=` (e.g. 5 s) to `subprocess.run` in `docker()` and map `subprocess.TimeoutExpired` to `DockerError`. `host_ports()` already degrades to `{}` on `DockerError`.

### M4. `/api/graph` (and the tap's SSE) is readable through DNS rebinding; only `/ws` checks the caller
`server/src/cloudy_labs/server/app.py:43-52`; `tap/api_tap.py:209-220`

Binding to loopback does not stop DNS rebinding. A page on `attacker.example` whose name re-resolves to 127.0.0.1 can `fetch('http://attacker.example:8730/api/graph')` same-origin and read the full graph: CIDRs, tags, key fingerprints, host ports. Nothing checks `Host`. The plan's own rationale for the WS origin check ("any page open in the learner's browser…") applies equally here. The data comes from a local emulator, so impact is limited, which is why this is Medium rather than High.

**Fix:** `app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])`. It ignores the port, and the Vite proxy forwards `Host: 127.0.0.1:5174` because `changeOrigin` is false, so the dev path keeps working. For api-tap's 4568, compare the `Host` header against `127.0.0.1:4568`/`localhost:4568` in `events_handler`. Port 4566 has the same exposure but it predates M2 (Floci itself had it).

---

## Low

### L1. Proxy errors outside `OSError` drop the connection with no response
`api_tap.py:162-177`. `http.client.IncompleteRead`/`BadStatusLine` (subclasses of `HTTPException`, not `OSError`) are not caught. This can happen when Floci is recreated mid-request during `labctl reset`. A malformed chunk size (`ValueError` in `read_body`, line 144) is not caught either. The handler thread prints a traceback and the client gets "connection aborted" instead of a clean 502. **Fix:** `except (OSError, http.client.HTTPException) as e:` and handle `ValueError` from `read_body` with a 400.

### L2. Duplicate React keys for route labels
`web/src/scene/edge-layer.tsx:66`. The label id is `${from}>${to}`. Two routes from the same route table to the same IGW/NAT with different CIDRs (e.g. `0.0.0.0/0` and `::/0`, or `0.0.0.0/0` plus a specific prefix) collide. The server keeps them distinct (`collector.py:115` puts the label in the edge id). React warns, and one label can be dropped or reused wrongly on update. **Fix:** key on `${from}>${to}:${label}`, or carry `GraphEdge.id` through `graphToScene` into `FixtureEdge`.

### L3. A WS disconnect that races a send is logged as an ASGI error
`server/app.py:65-80`. Starlette 1.10 `send` raises `WebSocketDisconnect(1006)` on `OSError`. Inside the anyio task group it comes out as an `ExceptionGroup`, which Starlette does not treat as a normal disconnect. Uvicorn then logs "Exception in ASGI application" when a tab closes or reloads while a graph is being sent. **Fix:** wrap the `send()` loop body in `try/except WebSocketDisconnect: tasks.cancel_scope.cancel(); return`, or use `except* WebSocketDisconnect` around the task group.

### L4. `labctl serve` crashes when `lsof` is missing
`cli.py:115`. `subprocess.run(["lsof", ...])` raises `FileNotFoundError` on minimal Linux, so the user sees a traceback instead of the "port in use" message. **Fix:** wrap it in `try/except FileNotFoundError` and leave out the PID.

### L5. Upgrading with an M1 stack still running recreates Floci without orphan cleanup
`stack.py:110-120`. `states` is non-empty, `is_running()` is false (no `api-tap` yet) and Floci is "running", so the `rm`/`remove_orphans` step is skipped. `compose up -d --wait` then recreates Floci because its port mapping changed. The old Floci's instance containers and VPC networks are left behind, which is exactly what `recreate_floci`'s docstring warns about. **Fix:** in the not-running branch, if Floci's published port differs from `FLOCI_PORT` (or simply whenever `api-tap` is missing), go through `recreate_floci()`, or document "run `labctl down` before upgrading".

### L6. `GraphHub.stop()` does not cancel a debounced refresh that is already running
`hub.py:87-90`. `_timer` is set to `None` before `await self.refresh(...)`, so `stop()` cannot cancel that task. At shutdown it may log "Task was destroyed but it is pending". **Fix:** keep the task reference until refresh completes (e.g. `try: await refresh finally: if self._timer is current: self._timer = None`), and have `stop()` await the cancelled tasks with `suppress(CancelledError)`.

---

## Scout findings: edge cases checked and found OK
- Hub refresh concurrency: poll, debounce and start share `_running`/`_dirty` correctly on one loop. A write during a collect costs exactly one more collect (covered by `test_hub.py:63`).
- `recreate_floci` with `api-tap depends_on floci`: the tap opens a new `HTTPConnection` per request, so Docker DNS re-resolves `floci` after the container is replaced. A docker test covers the reset path.
- WS reconnect: the server version restarting from 1 is handled by tracking the version per connection (`graph-client.ts:31`). Unmount clears the timer and ignores the late `onclose`.
- `ApiFlyLayer`: pending timers are cleared on unmount. `launch()` reassigns `pending.current` while the loop iterates the old array, which is safe.
- `Presence.update` runs inside `useMemo` (a side effect during render) but is idempotent for identical input, so a StrictMode double invoke is harmless.
- `httpx2` in the dev group is legitimate: Starlette 1.10's `TestClient` imports `httpx2`.
- The Vite proxy preserves `Origin` (the WS allowlist still applies). Vite binds to 127.0.0.1.
- Botocore over plain `http` uses header checksums, not aws-chunked trailers, so the tap's de-chunking plus `Content-Length` keeps SigV4 valid.

## Recommended actions (priority order)
1. H1: pass through `Content-Length` for HEAD/204/304 and add a regression test.
2. H2: narrow orphan/forwarder cleanup to labctl's own Floci before anyone runs `labctl reset` next to their own Floci.
3. M1: require N consecutive failures before `emulator-down`, and catch `ClientError` per instance in `recent_user_data`.
4. M3: add a timeout to `docker()`.
5. M2: make `api-event` lossy instead of dropping clients.
6. M4: add `TrustedHostMiddleware` and a Host check on 4568.
7. L1–L6 as cleanup.

## Metrics
- Type coverage: web `tsc` clean (per lead). Server is untyped-checked (no mypy configured).
- Tests: per lead, server 136 + 6 docker, web 97. No test covers HEAD passthrough, cross-Floci cleanup, transient collect failure, or an api-event burst.
- Lint: formatting drift is pre-existing and ignored.

## Unresolved questions
- Does Floci honour an env var to change its in-container port? That decides whether the simplest H2 fix is available.
- Product intent for `emulator-down`: should the scene keep the last known resources (dimmed) or collapse? M1's web-side suggestion depends on this.

Status: DONE_WITH_CONCERNS
Summary: 2 High (HEAD Content-Length rewritten to 0 by api-tap, reproduced; orphan cleanup scoped to any Floci, now including forwarders), 4 Medium (scene wipe on transient collect error, api-event burst drops browsers, docker CLI without timeout wedges the hub, /api/graph open to DNS rebinding), 6 Low.
Concerns/Blockers: H2 can delete the user's own Floci instance containers on `labctl reset`/`down`; fix before running labctl alongside it.

---

## Xử lý (2026-10-29)

| Mục | Cách xử lý | Kiểm bằng |
|---|---|---|
| H1 | HEAD, 204, 304 giữ nguyên `Content-Length` của upstream; phản hồi có body vẫn đặt theo độ dài thật | `test_head_keeps_the_object_size` (đỏ khi bỏ sửa: `'0' != '12345'`); HeadObject qua tap trả ContentLength 11 |
| H2 | Floci nghe 4567 trong container (`FLOCI_PORT`), owner label thành 4567 và `orphans.py` lọc theo `config.FLOCI_PORT`; forwarder chỉ bị dọn khi tên chứa id instance của stack này | probe `FLOCI_PORT=4569` xác nhận owner đi theo cổng; `test_forwarders_of_another_flocis_instances_stay`, `test_floci_listens_on_its_own_port_inside_the_container`; `pytest -m docker` 6 passed |
| M1 | Collector chỉ trả `emulator-down` khi Floci từ chối kết nối (`EndpointConnectionError`), hiện ngay. Timeout và lỗi khác để hub xử lý: phải lỗi 2 lần liền (`DOWN_AFTER`) mới bỏ graph cũ | `test_one_failed_collect_keeps_the_scene`, `test_floci_refusing_connections_shows_at_once` |
| M2 | Hàng đợi client đầy thì bỏ `api-event`, giữ client; chỉ graph mới làm client bị ngắt | `test_burst_of_api_events_skips_events_but_keeps_the_browser` |
| M3 | `docker()` nhận `timeout`, `host_ports` dùng 5 s; `TimeoutExpired` thành `DockerError` | test hiện có của host_ports |
| M4 | `TrustedHostMiddleware` (`127.0.0.1`, `localhost`) cho lab-server; `/events` của tap trả 403 với Host lạ | `test_foreign_host_is_refused`, `test_events_refuse_a_foreign_host` |
| L1 | Body chunked hỏng trả 400; lỗi upstream `OSError`/`HTTPException` trả 502 | `test_malformed_chunked_body_answers_400` |
| L2 | Key nhãn route gồm cả `from>to:label` | `pnpm test`, `pnpm typecheck` |
| L3 | Vòng gửi WS bắt `WebSocketDisconnect` và đóng gọn | test WS hiện có |
| L4 | Thiếu `lsof` thì coi như không có tiến trình nào giữ cổng | đọc code |
| L5 | Ghi vào `docs/emulator-differences.md`: chạy `labctl down` bằng bản cũ trước khi nâng cấp | tài liệu |
| L6 | Hub giữ các task debounce, `stop()` huỷ và chờ hết | `test_stop_cancels_a_debounced_refresh_that_is_collecting` |
