"""Build fixture-lab-06, then fixture-lab-07, through the web builder alone and `labctl check`
each; Lab 7 once with Run and once in practice mode, where the copied commands run in a shell.
Also launch a fixture-lab-07 instance through the builder API without a browser.

Real stack: Floci behind api-tap, the lab-server on its fixed port, the Vite dev server, Chrome
driven by web/scripts/e2e-builder-lab-0{6,7}.mjs and the aws CLI with the `lab` profile `labctl up`
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

import httpx
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
LAB07 = "fixture-lab-07"
WEB_ANSWERS_S = 60  # UserData keeps starting the web server after the instance reports running
API = f"http://{HOST}:{SERVER_PORT}"
WEB_ORIGIN = {"Origin": f"http://{HOST}:{WEB_DEV_PORT}"}


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
    for lab_id in (LAB, LAB07):
        shutil.copytree(Path(__file__).parent / "fixtures" / "labs" / lab_id, labs / lab_id)
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


@pytest.mark.parametrize("mode", ["run", "practice"])
def test_lab_07_built_with_the_builder_passes_its_checks(lab_server, web_dev, mode, tmp_path, capsys):
    assert main(["start", LAB07]) == 0  # a fresh network, and no key pair or instance of an earlier run
    out = Path(os.environ.get("BUILDER_E2E_OUT") or tmp_path)
    result = subprocess.run(["node", "scripts/e2e-builder-lab-07.mjs", mode, str(out)], cwd=WEB, env=run_env(), timeout=900)
    assert result.returncode == 0, "the builder run failed; see its PASS/FAIL lines above"

    steps = json.loads((out / f"e2e-builder-lab-07-{mode}.json").read_text())["steps"]
    assert len(steps) == 7 and all(s["exitCode"] == 0 for s in steps)
    assert "KeyMaterial" not in (out / f"e2e-builder-lab-07-{mode}.json").read_text()

    deadline = time.monotonic() + WEB_ANSWERS_S
    while main(["check", LAB07]) != 0:
        assert time.monotonic() < deadline, f"{LAB07} checks still fail after {WEB_ANSWERS_S}s"
        time.sleep(5)
    capsys.readouterr()
    with capsys.disabled():
        assert main(["check", LAB07]) == 0


def _node(graph: dict, kind: str, label: str) -> str:
    return next(n["id"] for n in graph["nodes"] if n["kind"] == kind and n["label"] == label)


def _wait_for(client: httpx.Client, node: str, seconds: float, kind: str | None = None) -> dict:
    """The graph once a node with this id or label (and kind, when given) shows up."""
    deadline = time.monotonic() + seconds
    while True:
        graph = client.get("/api/graph").json()
        if any(node in (n["id"], n["label"]) and kind in (None, n["kind"]) for n in graph["nodes"]):
            return graph
        assert time.monotonic() < deadline, f"{node} did not reach the graph within {seconds}s"
        time.sleep(0.2)


def _run(client: httpx.Client, op: str, params: dict) -> dict:
    body = client.post("/api/run", json={"op": op, "params": params}, headers=WEB_ORIGIN).json()
    assert body.get("exitCode") == 0, body
    return body


def test_run_instances_through_the_api_reaches_the_graph(lab_server):
    """Runs after the Lab 6 test: `labctl start` wipes the emulator for Lab 7's own network."""
    assert main(["start", LAB07]) == 0
    with httpx.Client(base_url=API, timeout=120) as client:
        info = client.get("/api/lab").json()
        assert info["id"] == LAB07 and info["canRun"], info
        # The network `start` built; the subnet is public once its route to the gateway is collected too.
        graph = _wait_for(client, "lab07-public", 15, kind="subnet-public")
        vpc, subnet = _node(graph, "vpc", "lab07-vpc"), _node(graph, "subnet-public", "lab07-public")
        sg = _run(client, "create-security-group", {"name": "lab07-web", "vpcId": vpc, "description": "web"})["expect"]["node"]
        _wait_for(client, sg, 5)
        launched = _run(client, "run-instances", {
            "name": "lab07-web", "subnetId": subnet, "imageId": info["images"][0], "instanceType": info["instanceTypes"][0],
            "securityGroupId": sg, "keyName": "", "userData": info["userData"]})
        instance = launched["expect"]["node"]
        assert instance.startswith("i-")
        graph = _wait_for(client, instance, 5)
        assert f"attached:{sg}->{instance}" in {e["id"] for e in graph["edges"]}
