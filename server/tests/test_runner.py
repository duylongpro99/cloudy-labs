import asyncio
import os
import stat
import time

import pytest

from cloudy_labs.builder.runner import Runner, run_env

FAKE_AWS = """#!/bin/sh
# Stand-in for the aws CLI: echoes its argv and what of the environment matters.
case "$2" in
  sleep) sleep 5 ;;
  hang) echo partial-out; echo partial-err >&2; echo $$ > "$3"; sleep 30 ;;
  fail) echo "An error occurred (InvalidParameterValue)" >&2; exit 254 ;;
esac
printf '{"argv": "%s", "awsVars": "%s"}\\n' "$*" "$(env | grep '^AWS_' | grep -v '^AWS_CONFIG_FILE=' | tr '\\n' ' ')"
"""


@pytest.fixture
def fake_aws(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    aws = bin_dir / "aws"
    aws.write_text(FAKE_AWS)
    aws.chmod(aws.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("AWS_PROFILE", "work")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAREALKEY")
    return aws


def test_run_env_drops_aws_vars_but_keeps_config_file():
    env = run_env({"PATH": "/bin", "AWS_PROFILE": "work", "AWS_ENDPOINT_URL": "x", "AWS_CONFIG_FILE": "/c"})
    assert env == {"PATH": "/bin", "AWS_CONFIG_FILE": "/c"}


def test_runs_argv_without_aws_env(fake_aws):
    result = asyncio.run(Runner().run(["aws", "ec2", "create-vpc", "--profile", "lab", "--output", "json"]))
    assert result.exit_code == 0 and result.stderr == ""
    assert '"argv": "ec2 create-vpc --profile lab --output json"' in result.stdout
    assert '"awsVars": ""' in result.stdout
    assert result.to_dict().keys() == {"exitCode", "stdout", "stderr", "durationMs"}


def test_failure_keeps_output_verbatim(fake_aws):
    result = asyncio.run(Runner().run(["aws", "ec2", "fail"]))
    assert result.exit_code == 254
    assert result.stderr == "An error occurred (InvalidParameterValue)\n"


def test_timeout_kills_the_command(fake_aws):
    result = asyncio.run(Runner(timeout=0.2).run(["aws", "ec2", "sleep"]))
    assert result.exit_code is None
    assert "stopped after" in result.stderr and result.duration_ms < 4000


def test_runs_one_command_at_a_time(fake_aws):
    async def both():
        runner = Runner()
        first = asyncio.create_task(runner.run(["aws", "ec2", "one"]))
        await asyncio.sleep(0)
        assert runner.busy
        second = await runner.run(["aws", "ec2", "two"])
        return await first, second, runner.busy

    first, second, busy = asyncio.run(both())
    assert first.exit_code == second.exit_code == 0 and not busy


def test_timeout_keeps_what_was_printed_before(fake_aws, tmp_path):
    result = asyncio.run(Runner(timeout=0.5).run(["aws", "ec2", "hang", str(tmp_path / "pid")]))
    assert result.exit_code is None
    assert result.stdout == "partial-out\n"
    assert result.stderr.startswith("partial-err\n") and "stopped after" in result.stderr


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_cancelled_run_leaves_no_process_behind(fake_aws, tmp_path):
    pid_file = tmp_path / "pid"

    async def cancel_midway():
        task = asyncio.create_task(Runner().run(["aws", "ec2", "hang", str(pid_file)]))
        while not pid_file.exists() or not pid_file.read_text().strip():
            await asyncio.sleep(0.02)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(cancel_midway())
    pid = int(pid_file.read_text())
    deadline = time.monotonic() + 3
    while alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not alive(pid)
