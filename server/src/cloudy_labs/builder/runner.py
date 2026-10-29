"""Run one builder command with the AWS CLI and keep its output verbatim (PRD F4.4).

The argv comes from ops.py and already carries `--profile lab`; it runs without a shell, one
command at a time. AWS_* variables are dropped so nothing in the server's environment can
override the profile: the command that runs is the one the learner can paste.
"""

import asyncio
import contextlib
import os
import shutil
import signal
import time
from dataclasses import asdict, dataclass

from ..emulator.aws_profile import cli_ignores_endpoint_url, credentials_overrides

TIMEOUT_S = 60.0
KEEP_ENV = {"AWS_CONFIG_FILE"}  # where the lab profile lives, when the learner moved the config


@dataclass(frozen=True)
class RunResult:
    exit_code: int | None  # None: killed after the timeout
    stdout: str
    stderr: str
    duration_ms: int

    def to_dict(self) -> dict:
        d = asdict(self)
        return {"exitCode": d["exit_code"], "stdout": d["stdout"], "stderr": d["stderr"], "durationMs": d["duration_ms"]}


def run_env(environ: dict[str, str] | None = None) -> dict[str, str]:
    environ = dict(os.environ if environ is None else environ)
    return {k: v for k, v in environ.items() if not k.startswith("AWS_") or k in KEEP_ENV}


def aws_available() -> bool:
    return shutil.which("aws") is not None


def run_blocker() -> str | None:
    """Why the builder must not run commands on this machine, or None. Each case would send a
    `--profile lab` command somewhere other than the emulator, or not at all."""
    if not aws_available():
        return "the aws CLI is not installed, so the builder can show commands but not run them"
    if old := cli_ignores_endpoint_url():
        return f"{old} ignores endpoint_url in profiles, so commands would go to real AWS; upgrade to AWS CLI v2.13 or later"
    if creds := credentials_overrides():
        return f"{creds} has a [lab] section whose keys would sign builder commands; rename that section"
    return None


class Runner:
    def __init__(self, timeout: float = TIMEOUT_S):
        self.timeout = timeout
        self._lock = asyncio.Lock()

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    async def run(self, argv: list[str]) -> RunResult:
        async with self._lock:  # one command at a time, in the order the learner clicked Run
            t0 = time.monotonic()
            proc = await asyncio.create_subprocess_exec(
                *argv, env=run_env(), stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                start_new_session=True,  # its own process group, so stopping it stops its children too
            )
            # Read the pipes apart from the wait, so what it printed before a timeout is kept.
            assert proc.stdout and proc.stderr
            out_t = asyncio.ensure_future(proc.stdout.read())
            err_t = asyncio.ensure_future(proc.stderr.read())
            note = b""
            try:
                code: int | None = await asyncio.wait_for(proc.wait(), self.timeout)
            except TimeoutError:
                note = f"\nlabctl: stopped after {self.timeout:g}s without an answer".encode()
                code = None
            finally:
                if proc.returncode is None:  # timed out, or the request was cancelled: leave no orphan
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(proc.pid, signal.SIGKILL)  # children would otherwise hold the pipes open
                    await asyncio.shield(proc.wait())
            out, err = await out_t, (await err_t) + note
            ms = round((time.monotonic() - t0) * 1000)
            return RunResult(code, out.decode("utf-8", "replace"), err.decode("utf-8", "replace"), ms)
