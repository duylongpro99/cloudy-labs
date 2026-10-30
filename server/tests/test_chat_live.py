"""Ask a real model the sample questions of tests/fixtures/chat/questions.yaml, through the
lab-server's /api/chat on fixture-lab-06 and fixture-lab-07, and build each lab from one request.

Real stack (Floci behind api-tap, the aws CLI with the `lab` profile) and the learner's provider:
LLM_BASE_URL, LLM_API_KEY, LLM_MODEL and LLM_API_FORMAT in the environment or in
~/.cloudy-labs/llm.env. Skipped when they are not set. Run with
`uv run pytest -m llm tests/test_chat_live.py -v` (needs Docker as well).

A question that fails because of the model is a result to record, not a test to loosen.
"""

import json
import shutil
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from cloudy_labs.chat.settings import Missing, load_settings
from cloudy_labs.cli import main
from cloudy_labs.server.app import create_app

# Read before any fixture points CLOUDY_LABS_HOME at a temporary directory.
SETTINGS = load_settings()

pytestmark = [
    pytest.mark.llm,  # not `docker` too: `-m docker` must not spend the learner's tokens
    pytest.mark.skipif(isinstance(SETTINGS, Missing), reason="no LLM provider set (LLM_BASE_URL, LLM_API_KEY, "
                                                             "LLM_MODEL, LLM_API_FORMAT)"),
]

FIXTURES = Path(__file__).parent / "fixtures"
QUESTIONS = yaml.safe_load((FIXTURES / "chat" / "questions.yaml").read_text())
ORIGIN = {"Origin": "http://127.0.0.1:5174"}
SEEN_S = 30  # how long a run may take to show in the graph
CHECKS_S = 90  # Lab 7's web server starts after the instance reports running

# In run order: a lab's `labctl start` wipes the emulator, so each lab's cases stay together.
CASES = [
    pytest.param(lab, stage, item, id=f"{lab}-{stage}{'' if stage == 'build' else n}")
    for lab, sets in QUESTIONS.items()
    for stage, items in [("fresh", sets["fresh"]), ("build", [sets["build"]]), ("built", sets["built"])]
    for n, item in enumerate(items, start=1)
]


@pytest.fixture(autouse=True)
def isolated_home():
    """The module-scoped `stack` fixture owns CLOUDY_LABS_HOME here; do not swap it per test."""


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    if not shutil.which("aws"):
        pytest.skip("needs the aws CLI on PATH")
    home = tmp_path_factory.mktemp("home")
    labs = tmp_path_factory.mktemp("labs")
    for lab_id in QUESTIONS:
        shutil.copytree(FIXTURES / "labs" / lab_id, labs / lab_id)
    mp = pytest.MonkeyPatch()
    mp.setenv("CLOUDY_LABS_HOME", str(home))
    mp.setenv("CLOUDY_LABS_LABS_DIR", str(labs))
    mp.setenv("AWS_CONFIG_FILE", str(home / "aws-config"))
    try:
        assert main(["up"]) == 0
        app = create_app(llm=lambda: SETTINGS)
        with TestClient(app, base_url="http://127.0.0.1:8730") as client:
            yield {"client": client, "lab": None, "built": set()}
    finally:
        main(["down"])  # always, so a failing test leaves no containers behind
        mp.undo()


def graph(client: TestClient) -> dict[str, Any]:
    client.portal.call(client.app.state.hub.refresh, "test")
    return client.get("/api/graph").json()


def on_lab(stack: dict[str, Any], lab: str) -> TestClient:
    client = stack["client"]
    if stack["lab"] != lab:
        assert main(["start", lab]) == 0
        stack["lab"] = lab
        graph(client)
    return client


def ask(client: TestClient, question: str) -> dict[str, Any]:
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": question}]}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()


def seen(expect: dict[str, Any], g: dict[str, Any]) -> bool:
    """The web app's expectMet: whether the graph shows what a run was expected to make."""
    if "after" in expect:
        return g["version"] > expect["after"]
    if "edge" in expect:
        return any(e["id"] == expect["edge"] for e in g["edges"])
    node = next((n for n in g["nodes"] if n["id"] == expect["node"]), None)
    if node is None or "prop" not in expect:
        return node is not None
    value = node["props"].get(expect["prop"])
    if "includes" not in expect:
        return value == expect.get("value")
    rule = {k: v for k, v in expect["includes"].items() if k != "source"}
    return isinstance(value, list) and any(
        expect["includes"]["source"] in r.get("sources", []) and all(r.get(k) == v for k, v in rule.items()) for r in value)


def run_chain(client: TestClient, steps: list[dict[str, Any]]) -> None:
    """Run the steps in order as the web app's "Run cả chuỗi" does: refs filled in from earlier runs."""
    made: dict[int, str] = {}
    for n, step in enumerate(steps, start=1):
        params = {k: made[v["ref"]] if isinstance(v, dict) else v for k, v in step["params"].items()}
        r = client.post("/api/run", json={"op": step["op"], "params": params}, headers=ORIGIN)
        assert r.status_code == 200, f"step {n} {step['op']} refused: {r.text}"
        out = r.json()
        assert out["exitCode"] == 0, f"step {n} {step['op']} failed: {out['stderr']}"
        if expect := out["expect"]:
            deadline = time.monotonic() + SEEN_S
            while not seen(expect, graph(client)):
                assert time.monotonic() < deadline, f"step {n} {step['op']} never showed in the graph"
                time.sleep(1)
            if "node" in expect:
                made[n] = expect["node"]


def check_answer(answer: dict[str, Any], item: dict[str, Any], g: dict[str, Any]) -> None:
    steps = answer["steps"]
    if item.get("refusal"):
        assert answer["refusal"] and steps == [], json.dumps(answer, ensure_ascii=False)
        return
    assert not answer["refusal"], answer["refusal"]
    ops = [s["op"] for s in steps]
    assert set(item["ops"]) <= set(ops), f"expected {item['ops']}, got {ops}"
    ids = {n["id"] for n in g["nodes"]}
    for n, s in enumerate(steps, start=1):
        assert s["problems"] == [], f"step {n} {s['op']}: {s['problems']}"
        for name, value in s["params"].items():
            if isinstance(value, dict):
                assert 1 <= value["ref"] < n, f"step {n} {name}: bad ref {value}"
            elif name.endswith("Id") and name != "imageId":
                assert value in ids, f"step {n} {name}: {value} is not in the scene"


@pytest.mark.parametrize("lab, stage, item", CASES)
def test_chat(stack, lab, stage, item, capsys):
    client = on_lab(stack, lab)
    if stage == "built" and lab not in stack["built"]:
        pytest.skip(f"{lab} was not built from the chat's answer")
    question = item if stage == "build" else item["question"]
    answer = ask(client, question)
    if stage != "build":
        check_answer(answer, item, graph(client))
        return

    assert not answer["refusal"] and answer["steps"], json.dumps(answer, ensure_ascii=False)
    bad = [(n, s["op"], s["problems"]) for n, s in enumerate(answer["steps"], start=1) if s["problems"]]
    assert not bad, bad
    run_chain(client, answer["steps"])
    deadline = time.monotonic() + CHECKS_S
    while main(["check", lab, "--json"]) != 0:
        assert time.monotonic() < deadline, f"{lab} checks still fail after {CHECKS_S}s: {capsys.readouterr().out}"
        time.sleep(5)
    capsys.readouterr()
    stack["built"].add(lab)
