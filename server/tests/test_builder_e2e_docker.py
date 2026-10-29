"""Build fixture-lab-06 through the web builder alone, then `labctl check` it.

Real stack: Floci behind api-tap, the lab-server on its fixed port, the Vite dev server, Chrome
driven by web/scripts/e2e-builder-lab-06.mjs and the aws CLI with the `lab` profile `labctl up`
writes. Run with `uv run pytest -m docker tests/test_builder_e2e_docker.py -s`.
"""

import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from cloudy_labs.builder.runner import run_env
from cloudy_labs.cli import main
from cloudy_labs.config import HOST, SERVER_PORT, WEB_DEV_PORT
from cloudy_labs.server.app import create_app

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
LAB = "fixture-lab-06"


def listening(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex((HOST, port)) == 0


@pytest.fixture(autouse=True)
def isolated_home():
    """The module-scoped `lab` fixture owns CLOUDY_LABS_HOME here; do not swap it per test."""


@pytest.fixture(scope="module")
def lab(tmp_path_factory):
    if not shutil.which("aws") or not shutil.which("node") or not shutil.which("pnpm"):
        pytest.skip("needs the aws CLI, node and pnpm on PATH")
    home = tmp_path_factory.mktemp("home")
    labs = tmp_path_factory.mktemp("labs")
    shutil.copytree(Path(__file__).parent / "fixtures" / "labs" / LAB, labs / LAB)
    mp = pytest.MonkeyPatch()
    mp.setenv("CLOUDY_LABS_HOME", str(home))
    mp.setenv("CLOUDY_LABS_LABS_DIR", str(labs))
    mp.setenv("AWS_CONFIG_FILE", str(home / "aws-config"))  # `up` writes the lab profile here
    try:
        assert main(["up"]) == 0
        assert main(["start", LAB]) == 0
        yield home
    finally:
        main(["down"])  # always, so a failing test leaves no containers behind
        mp.undo()


@pytest.fixture(scope="module")
def lab_server(lab):
    assert not listening(SERVER_PORT), f"port {SERVER_PORT} is taken; stop the other lab-server first"
    srv = uvicorn.Server(uvicorn.Config(create_app(), host=HOST, port=SERVER_PORT, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not srv.started:
        assert time.monotonic() < deadline, "lab-server did not start"
        time.sleep(0.05)
    yield
    srv.should_exit = True
    thread.join(10)


@pytest.fixture(scope="module")
def web_dev():
    """The Vite dev server; reuses one already running on its fixed port, else starts and stops one."""
    if listening(WEB_DEV_PORT):
        yield
        return
    proc = subprocess.Popen(["pnpm", "dev"], cwd=WEB, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    try:
        deadline = time.monotonic() + 30
        while not listening(WEB_DEV_PORT):
            assert proc.poll() is None and time.monotonic() < deadline, "the Vite dev server did not start"
            time.sleep(0.2)
        yield
    finally:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(10)


def test_lab_06_built_with_the_builder_passes_its_checks(lab_server, web_dev, tmp_path, capsys):
    out = Path(os.environ.get("BUILDER_E2E_OUT") or tmp_path)
    result = subprocess.run(["node", "scripts/e2e-builder-lab-06.mjs", str(out)], cwd=WEB, timeout=900)
    assert result.returncode == 0, "the builder run failed; see its PASS/FAIL lines above"

    steps = json.loads((out / "e2e-builder.json").read_text())["steps"]
    assert len(steps) == 20 and all(s["exitCode"] == 0 for s in steps)

    # A command copied from the panel runs as-is in a shell with no AWS_* settings but the config path.
    copied = next(s["command"] for s in steps if s["op"] == "modify-vpc-attribute")
    rerun = subprocess.run(shlex.split(copied), env=run_env(), capture_output=True, text=True, timeout=60)
    assert rerun.returncode == 0, rerun.stderr

    with capsys.disabled():
        assert main(["check", LAB]) == 0
