"""The contract test of every registry kind with a `contract`: on the pinned Floci, the builder's
create op makes a node of that kind in the right parent, each later op shows what its run expects,
and the graph shows each within the kind's time limit. Results go to registry/contract-results.json
(committed), stamped with the Floci image digest, for `labctl coverage` and docs/coverage.md.

Real stack: Floci behind api-tap and the lab-server on its fixed port, driven over its HTTP API.
Run with `uv run pytest -m docker tests/test_registry_contract_docker.py -q`.
"""

import json
import re
import shutil
import socket
import subprocess
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
import yaml

from cloudy_labs.builder.catalog import op_named
from cloudy_labs.cli import main
from cloudy_labs.config import HOST, SERVER_PORT, WEB_DEV_PORT
from cloudy_labs.coverage.evaluate import CONTRACT_RESULTS, pinned_image
from cloudy_labs.registry import ContractStep, default_registry
from cloudy_labs.server.app import create_app

pytestmark = pytest.mark.docker

LAB = "contract-lab"
API = f"http://{HOST}:{SERVER_PORT}"
WEB_ORIGIN = {"Origin": f"http://{HOST}:{WEB_DEV_PORT}"}
KINDS = [t for t in default_registry().types if t.contract and not t.test_only]
RESULTS: list[dict[str, Any]] = []


def listening(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex((HOST, port)) == 0


@pytest.fixture(autouse=True)
def isolated_home():
    """The module-scoped `stack` fixture owns CLOUDY_LABS_HOME here; do not swap it per test."""


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    if not shutil.which("aws"):
        pytest.skip("needs the aws CLI on PATH")
    home = tmp_path_factory.mktemp("home")
    labs = tmp_path_factory.mktemp("labs")
    # A lab whose palette offers every builder kind, so the lab-server runs any op.
    shutil.copytree(Path(__file__).parent / "fixtures" / "labs" / "fixture-lab-06", labs / LAB)
    spec = yaml.safe_load((labs / LAB / "lab.yaml").read_text())
    spec.update(id=LAB, title="Registry contract test")
    spec["builder"] = {"palette": default_registry().builder_kinds(), "tags": {"lab": LAB}}
    (labs / LAB / "lab.yaml").write_text(yaml.safe_dump(spec, allow_unicode=True))
    mp = pytest.MonkeyPatch()
    mp.setenv("CLOUDY_LABS_HOME", str(home))
    mp.setenv("CLOUDY_LABS_LABS_DIR", str(labs))
    mp.setenv("AWS_CONFIG_FILE", str(home / "aws-config"))
    try:
        assert main(["up"]) == 0
        assert main(["start", LAB]) == 0
        yield
    finally:
        main(["down"])
        mp.undo()


@pytest.fixture(scope="module")
def client(stack):
    assert not listening(SERVER_PORT), f"port {SERVER_PORT} is taken; stop the other lab-server first"
    srv = uvicorn.Server(uvicorn.Config(create_app(), host=HOST, port=SERVER_PORT, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not srv.started:
        assert time.monotonic() < deadline, "lab-server did not start"
        time.sleep(0.05)
    with httpx.Client(base_url=API, timeout=180) as c:
        yield c
    srv.should_exit = True
    thread.join(10)
    _write_results()


def _image_digest() -> str:
    version, pinned = pinned_image()
    out = subprocess.run(["docker", "image", "inspect", f"floci/floci:{version}", "--format", "{{json .RepoDigests}}"],
                         capture_output=True, text=True)
    digests = [d.split("@", 1)[1] for d in json.loads(out.stdout or "[]") if "@" in d]
    return pinned if pinned in digests else (digests[0] if digests else "unknown")


def _write_results() -> None:
    if not RESULTS:
        return
    data = {"floci_image_digest": _image_digest(), "date": date.today().isoformat(),
            "results": sorted(RESULTS, key=lambda r: (r["kind"], r["step"], r["op"]))}
    CONTRACT_RESULTS.write_text(json.dumps(data, indent=1) + "\n")


def _fill(value: Any, saved: dict[str, str]) -> Any:
    """"{name}" anywhere in a text value is the saved value; JSON objects ({"From": ...}) never match."""
    if isinstance(value, str):
        return re.sub(r"\{(\w+)\}", lambda m: saved[m.group(1)], value)
    return value


def _seen(graph: dict, expect: dict) -> bool:
    nodes = {n["id"]: n for n in graph["nodes"]}
    if "node" in expect:
        node = nodes.get(expect["node"])
        if node is None:
            return False
        if "prop" not in expect:
            return True
        value = node["props"].get(expect["prop"])
        if "includes" not in expect:
            return value == expect["value"]
        # As the web client reads it: `source` is one of the rule's `sources`.
        rule = dict(expect["includes"])
        source = rule.pop("source")
        return any(source in (r.get("sources") or []) and all(r.get(k) == v for k, v in rule.items())
                   for r in value or [])
    if "edge" in expect:
        return expect["edge"] in {e["id"] for e in graph["edges"]}
    if "gone" in expect:
        return expect["gone"] not in nodes
    return graph["version"] > expect.get("after", 0)


def _named(op_name: str, params: dict[str, Any]) -> dict | None:
    """For a create op whose output names no id (CreateBucket, PublishLayerVersion): the node of its
    kind carrying the name it was given, as the practice check finds it."""
    op = op_named(op_name)
    if op.gesture != "create" or op.result_id or not (op.spec.expect and op.spec.expect.label):
        return None
    label = params.get(op.spec.expect.label)
    label = label[0] if isinstance(label, list) else label
    return {"kinds": default_registry().expand([op.spec.expect.kind or op.creates]), "label": label}


def _named_node(graph: dict, named: dict) -> str | None:
    return next((n["id"] for n in graph["nodes"] if n["kind"] in named["kinds"] and n["label"] == named["label"]), None)


def _run(client: httpx.Client, step: ContractStep, saved: dict[str, str]) -> tuple[dict, dict, float]:
    """Run one op; (its response, the graph that shows its result, seconds from return to that graph).
    The response's `expect` gains the created node's id when the op's output had none."""
    params = {k: _fill(v, saved) for k, v in step.params.items()}
    body = client.post("/api/run", json={"op": step.op, "params": params}, headers=WEB_ORIGIN).json()
    assert body.get("exitCode") == 0, f"{step.op}: {body}"
    named = None if "node" in body["expect"] else _named(step.op, params)
    returned = time.monotonic()
    deadline = returned + 60
    while True:
        graph = client.get("/api/graph").json()
        if named and (node_id := _named_node(graph, named)):
            body["expect"] = {"node": node_id}
        if (not named or "node" in body["expect"]) and _seen(graph, body["expect"]):
            seconds = time.monotonic() - returned
            break
        assert time.monotonic() < deadline, f"{step.op}: the graph never showed {named or body['expect']}"
        time.sleep(0.1)
    if step.save:
        saved[step.save] = body["expect"]["node"]
    return body, graph, seconds


def _record(kind: str, step: str, op: str, seconds: float, limit: float) -> None:
    RESULTS.append({"kind": kind, "step": step, "op": op, "result": "pass" if seconds <= limit else "slow",
                    "seconds": round(seconds, 2), "max_seconds": limit})


@pytest.mark.parametrize("kind", [t.kind for t in KINDS])
def test_the_builder_creates_each_kind_on_floci(client, kind):
    t = default_registry().get(kind)
    contract = t.contract
    info = client.get("/api/lab").json()
    saved: dict[str, str] = {"az": info["azs"][0], "region": info["azs"][0][:-1], "image": info["images"][0],
                             "instanceType": info["instanceTypes"][0], "userData": info["userData"] or ""}
    for step in contract.needs:
        _run(client, step, saved)
    try:
        body, graph, seconds = _run(client, contract.create, saved)
    except AssertionError:
        RESULTS.append({"kind": kind, "step": "create", "op": contract.create.op, "result": "fail"})
        raise
    node_id = body["expect"]["node"]
    node = next(n for n in graph["nodes"] if n["id"] == node_id)
    op = op_named(contract.create.op)
    allowed = default_registry().expand([op.spec.creates or op.palette_kind() or kind]) | {kind}
    assert node["kind"] in allowed, f"{contract.create.op} made a {node['kind']}, not a {kind}"
    parents = {c["child"]: c["parent"] for c in graph["contains"]}
    parent = parents.get(node_id)
    nodes = {n["id"]: n for n in graph["nodes"]}
    if contract.parent:
        # Structural nodes (an AZ inside a VPC) may sit between the node and the parent it names.
        ancestors, up = [], parent
        while up is not None and up not in ancestors:
            ancestors.append(up)
            up = parents.get(up)
        assert saved[contract.parent] in ancestors, f"{kind} sits in {ancestors}, not in {saved[contract.parent]}"
    else:
        assert parent and nodes[parent]["kind"] in t.parent_kinds(), f"{kind} sits in {parent}"
    _record(kind, "create", contract.create.op, seconds, contract.max_seconds)

    for step in contract.then:
        try:
            _, _, seconds = _run(client, step, saved)
        except AssertionError:
            RESULTS.append({"kind": kind, "step": "then", "op": step.op, "result": "fail"})
            raise
        _record(kind, "then", step.op, seconds, contract.max_seconds)
    if not any(op.gesture == "delete" for op in t.ops):
        RESULTS.append({"kind": kind, "step": "delete", "op": "-", "result": "no-op"})
    slow = [r for r in RESULTS if r["kind"] == kind and r["result"] == "slow"]
    assert not slow, f"{kind}: slower than {contract.max_seconds}s: {slow}"
