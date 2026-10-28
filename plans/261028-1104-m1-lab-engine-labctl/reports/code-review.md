# Code Review: M1 lab engine (`labctl`)

Date: 2026-10-28
Scope: `server/src/cloudy_labs/**`, `server/tests/**`, `server/pyproject.toml`, checked against `plan.md`, phases 1-5 and `notes/floci-labels.md`.
LOC reviewed: about 900 source lines and 630 test lines.
Verification run: `cd server && uv run pytest -q`, which gave 51 passed and 3 deselected (the docker tests). I did not run any Docker command.
I reproduced findings H1, H2 and M3 with a small Python script against the package. I verified the other findings by reading the code.

Known decisions I did not re-raise: checkers run arbitrary code from trusted lab dirs, the test/test credentials, `Provider.reset()` taking no lab argument, and moto returning 500 for unsigned requests.

## Overall assessment

The code is small and easy to follow. The docker cleanup is safe in the way that matters:
- Every removal comes from a listing that uses two label filters, `label=io.floci.owner=4566` and `label=io.floci=aws`. Docker combines repeated `label` filters with AND.
- There is no wildcard or name-prefix removal.
- The compose `floci` container does not have the owner label (see `notes/floci-labels.md`).

I found no path that can remove a user container that lacks both labels.

The main problems are elsewhere:
- The port preflight does not work on macOS, the target platform.
- `up` can delete live Floci resources.
- Malformed checker output crashes `check` and breaks its documented exit-code contract.
- A failed `start` or `reset` leaves the progress store pointing at a lab whose emulator state was just wiped.

## Critical

None.

## High

### H1. The port preflight misses wildcard listeners on macOS
`emulator/preflight.py:12-20`, used by `emulator/stack.py:56-59`

`port_free()` sets `SO_REUSEADDR` and binds `127.0.0.1:<port>`. On macOS and other BSDs, `SO_REUSEADDR` lets a socket bind a specific address while another socket listens on the wildcard address for the same port. So any process listening on `0.0.0.0:4566` or `*:5050` is reported as "free".

Reproduced on this machine: I listened on `0.0.0.0:<n>`, called `port_free(n)`, and it returned `True`.

Failure scenario: LocalStack, an old Floci, or any dev server publishes `4566` on all interfaces, and the user runs `labctl up`.
- The preflight passes.
- One of two things happens next, depending on Docker Desktop's bind behaviour:
  - `compose up` fails with Docker's raw "address already in use" / "port is already allocated" text instead of the `lsof` hint, or
  - both listeners coexist and loopback traffic reaches whichever bind is more specific.

Either way, this misses the plan's success criterion that `labctl up` reports a clear error when 4566 or 5050 is taken. The unit test `test_port_free_detects_listener` only binds `127.0.0.1`, so it does not cover this case.

Fix: probe with a connect instead of a bind. If `socket.create_connection((HOST, port), timeout=0.5)` succeeds, the port is busy. This catches every listener reachable on loopback and does not need the TIME_WAIT workaround. Add a test that uses a `0.0.0.0` listener.

### H2. Malformed checker output crashes `check`, loses the run, and exits 1 ("checks failed") instead of 2
`checks.py:31-36`, `progress.py:74-80`, `cli.py:114-120`

`run_checks` only checks that the return value is a `CheckResult`. It does not check the fields. `record_checks` then binds those fields into SQLite:

| Checker returns | Effect (reproduced) |
|---|---|
| `CheckResult(match, ...)` where `match` is a list (an easy slip for `bool(match)`) | `sqlite3.ProgrammingError: Error binding parameter 3: type 'list' is not supported` |
| `CheckResult(None, ...)` or `message=None` | `sqlite3.IntegrityError: NOT NULL constraint failed` |
| `resource_ids` containing a non-JSON value, e.g. a `datetime` from boto3 | `TypeError` from `json.dumps` |
| `passed="no"` | Stored as text, and `latest_results`/`lab_summary` report it as passed: `bool("no")` is `True` (reproduced: `{'x': True}`) |
| `resource_ids="vpc-1"` | `list("vpc-1")` turns it into `['v','p','c','-','1']` |

`main()` only catches `DockerError`, `LabError` and `EngineError`, so the sqlite and json exceptions escape with a traceback and Python exits with code 1.

Failure scenario: a lab author writes `return CheckResult(vpcs, "found", ids)`. Every `labctl check` prints a traceback and records nothing, and the exit code is 1. `docs/labctl.md:32` defines 1 as "a check failed" and 2 as "could not grade". Scripts and the future M2 server will read this as an ordinary failure. This also breaks the stated runner contract ("one broken checker must not hide the others").

Fix: normalise each result in `run_checks`.
- Require `isinstance(r.passed, bool)` and `isinstance(r.message, str)`.
- Require `resource_ids` to be a list or tuple of `str`.
- Otherwise turn the result into a failing result that explains the type error.

Separately, map unexpected exceptions in `main()` to exit 2 for `check`, e.g. with a final `except Exception` that prints a short message. Add tests for the list, None and str cases.

## Medium

### M1. `labctl up` deletes live Floci instances when only moto, or only health, is not ready
`emulator/stack.py:38-43, 52-62`

`up()` calls `remove_orphans()` whenever `is_running()` is false. `is_running()` requires both services to be running and healthy.

Failure scenario:
1. The user is mid-lab with an EC2 instance on Floci.
2. moto exits, or the user stops it, or moto is still in `Health: starting`.
3. The user runs `labctl up`.
4. Floci is still running with the instance and VPC in memory, but `remove_orphans()` force-removes the instance container and the VPC network.
5. `compose up` only starts moto.
6. Floci now reports an instance whose container no longer exists. Checks that need the instance give misleading results until the next `reset`.

Fix: only clean orphans when the `floci` service is not running, e.g. `if states.get("floci", {}).get("State") != "running": remove_orphans()`. Alternatively, restart Floci as part of the same step so its memory and Docker agree.

### M2. A failed `start` or `reset` leaves the previous attempt "current" against a wiped emulator
`engine.py:65-76`, `engine.py:78-86`

`_fresh_attempt` does three things in this order: `provider.reset()`, the setup steps, then `start_attempt`. If a setup step fails, `reset()` raises, or the user presses Ctrl-C, the emulator is already wiped but no attempt is recorded. `current_attempt()` still returns the previous lab's attempt.

Failure scenario:
1. The user finishes lab A on Floci.
2. They run `labctl start B` (also on Floci), and B's setup raises.
3. `labctl status` still shows "current lab: A".
4. `labctl check A` is accepted. It runs against the emptied emulator and records failures into A's old attempt, overwriting what `latest_results("A")` shows.

The unit test `test_failing_setup_step_is_reported` only covers the first-ever attempt, where `current_attempt()` is `None`.

Fix: record the new attempt (or a "reset pending" marker) before calling `provider.reset()`, and mark it failed if setup fails. At minimum, make `check` refuse an attempt that was started before the last reset of that emulator.

### M3. Checker modules are not registered in `sys.modules`, so common Python constructs fail to import
`labs/loader.py:37-45`

`module_from_spec` plus `exec_module` without `sys.modules[spec.name] = module` breaks anything that looks the module up by name.

Reproduced: a `checks.py` containing `from __future__ import annotations` and a `@dataclass` fails to load with `LabError: demo: cannot import checks.py: 'NoneType' object has no attribute '__dict__'`.

`typing.get_type_hints`, pickling and pydantic forward references inside checkers fail the same way. Lab authors will hit this with ordinary code, and the error does not point to the cause.

Fix: follow the importlib recipe. Insert `sys.modules[spec.name] = module` before `exec_module`, and pop it if `exec_module` raises. The per-lab module name already prevents collisions between labs.

### M4. `labctl down` stops halfway if one orphan cannot be removed
`emulator/stack.py:72-79`, `emulator/orphans.py:37-46`

The cleanup steps run in sequence with no recovery. If `docker network rm` fails, `compose down -v` and the volume removal never run. Example: the user connected one of their own containers to a `floci-aws-vpc-*` network to debug. Docker refuses with "has active endpoints".

This failure is safe, because the user's container is not touched. But the stack is left stopped and not removed, and every later `down` fails the same way.

Fix: in `down()`, run `compose down` even if the first orphan pass fails, and collect and report each failed removal instead of aborting on the first one. Keep the current refusal to force-disconnect foreign containers.

## Low

### L1. Orphans are removed by name instead of ID
`orphans.py:31-33`

`{{.Names}}` can contain comma-joined aliases, and network names are not guaranteed to be unique, so `network rm <name>` can be ambiguous. Listing with `-q` (IDs) and removing by ID is equally safe and more robust. Nothing is broken today with Floci's naming.

### L2. Check runs are grouped by `ran_at`
`progress.py:74-105`

Runs are identified by a wall-clock string. Two runs in the same microsecond, for example from the CLI and the future lab-server, would merge into one run. A backwards clock step (NTP) makes `MAX(ran_at)` return an older run. A `run_id` column (or a `check_runs_runs` table) gives a stable key. This is cheap now and needs a migration later.

### L3. Concurrent first open of `progress.db` can fail
`progress.py:50-53`

`PRAGMA user_version` is read outside the transaction, and the transaction is a deferred `BEGIN`. If two processes open a fresh DB at the same time, both see version 0. The second one fails with `table attempts already exists` (an `OperationalError` that escapes as a traceback). Use `BEGIN IMMEDIATE` and re-read `user_version` inside the transaction.

### L4. `status` and `env` import every lab's checker code
`engine.py:94-99`, `cli.py:53`

Both commands load `checks.py` modules just to read a title or an emulator. `status` imports every lab. A slow or broken import in one lab slows down or affects these read-only commands. The trust model is accepted, so this is only a cost issue. A YAML-only load path would avoid it.

### L5. A moto reset failure gives a misleading message
`providers/aws.py:72-73`

`HTTPError` is a subclass of `URLError`, so a moto 500 from `reset-auth` is reported as "is the stack up (`labctl up`)?". Catch `HTTPError` separately and include the status code.

### L6. The moto no-auth count is defined twice
`providers/aws.py:18`, `compose.yaml:30`

`MOTO_NO_AUTH_ACTIONS = 3` and `INITIAL_NO_AUTH_ACTION_COUNT: "3"` are kept in sync by hand. If they drift, `reset` restores a different budget than `up` provides.

### L7. `status <unknown-lab>` exits 0
`status <unknown-lab>` prints "no checks run yet for ghost" and exits 0 instead of reporting that the lab does not exist.

## Test gaps

- No unit test covers the sequence of `stack.up()` or `stack.down()` with a mocked `docker`:
  - the already-running path,
  - the port-busy path,
  - the order stop → orphans → compose down → orphans.

  These are the paths that protect user data and ports, and today only the opt-in docker test covers them.
- No test for the order inside `AwsProvider.reset()` on Floci (restart → wait → remove orphans).
- No CLI test for `check` exit codes 0, 1 and 2, or for the shape of the `--json` output for `check` and `status`. The M2 server will depend on these.
- No test for checker results with the wrong field types (H2).
- No test for a failed `start` after an earlier attempt exists (M2).
- `test_port_free_detects_listener` only uses a loopback-bound listener (H1).
- `test_orphans` checks the filters but has no negative case showing that unlabelled or other-owner resources are never passed to `rm`. That logic lives in Docker's filter, so the useful assertion is that every `rm` argument comes from a labelled listing. The current test partly covers this.

## Plan follow-ups (report only)

- `plan.md` front matter still says `status: pending`, while all five phases are marked Completed.
- Phase 5 step 5 says to record the `uv run pytest -m docker` result in the plan. I found no recorded result in `plan.md`, so the docker success criterion is not documented.
- These deviations are intentional or harmless, and I verified each one:
  - `down` order changed to stop → orphans → down → orphans, per `notes/floci-labels.md`.
  - `health()` returns `bool`, not `dict`.
  - The test file is `test_providers.py`, not `test_provider_env.py`.
  - `reset()` takes no lab argument (accepted).

## Positive observations (risk calibration)

- The cleanup filters are exact, ANDed and port-scoped. The removal order (containers, then networks, then volumes) matches the notes.
- Lab ids from the CLI cannot escape `labs_dir()` and execute code: `load_lab` requires `lab.id == lab_id` and a slug pattern before it resolves any module.
- Loader errors, setup errors and checker exceptions are wrapped with file and step context.

## Metrics

- Unit tests: 51 passed, 3 docker tests deselected (not run, per the constraints).
- Lint and type checks: no linter or type checker is configured in `pyproject.toml`, so I did not run either.
- Coverage: no coverage tool is configured, so I did not measure it.

## Unresolved questions

- Does Floci attach its own container to `floci-aws-vpc-*` networks, for example for the IMDS proxy? If it does, `remove_orphans()` inside `reset()` (where Floci is running) would hit "active endpoints" on `network rm`. The reported docker run suggests it does not, but only a VPC was created before `reset` there, not an instance.
- For moto labs, checkers and `setup` use test/test credentials. After `INITIAL_NO_AUTH_ACTION_COUNT` actions, are those calls denied unless the checker passes IAM credentials? This is a design question for lab authors, not a code defect.

Status: DONE_WITH_CONCERNS
Summary: No issue found in the docker cleanup's data safety. Two High findings: the port preflight misses wildcard listeners on macOS, and malformed checker results crash `check` with exit 1. Four Medium findings cover live-orphan removal in `up`, a stale current attempt after a failed start or reset, checker modules missing from `sys.modules`, and `down` aborting partway.
