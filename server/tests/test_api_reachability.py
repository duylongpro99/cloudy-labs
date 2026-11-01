"""POST /api/reachability: guarded, validated, and answered from the network graph."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from cloudy_labs.graph.collector import collect, emulator_down
from cloudy_labs.reachability import NETWORK_KINDS
from cloudy_labs.registry import default_registry
from cloudy_labs.server.app import create_app
from test_app import GOLDEN, NO_CHECKS, ORIGIN
from test_reachability import CLOCK, _patched_clients

NETWORK = collect(_patched_clients(), clock=lambda: CLOCK, ports=lambda: {}, kinds=list(NETWORK_KINDS),
                  registry=default_registry())


@pytest.fixture
def client():
    state = {"network": NETWORK}
    app = create_app(lambda: GOLDEN, listen=False, lab=lambda: None, checks_runner=NO_CHECKS,
                     network=lambda: state["network"])
    with TestClient(app, base_url="http://127.0.0.1:8730") as c:
        yield c, state


def test_answers_with_hops_and_the_analysis_label(client):
    c, _ = client
    r = c.post("/api/reachability", json={"src": "internet", "dst": "rx-web", "port": 22}, headers=ORIGIN)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and body["reason"] == "no-matching-rule" and body["label"] == "analysed"
    assert body["blockedAt"] in {n.id for n in NETWORK.nodes}
    assert body["hops"][-1]["verdict"] == "deny"


def test_without_the_web_app_origin_it_is_refused(client):
    c, _ = client
    assert c.post("/api/reachability", json={"src": "internet", "dst": "rx-web", "port": 80}).status_code == 403
    assert c.post("/api/reachability", content='{"src": "internet", "dst": "rx-web", "port": 80}',
                  headers={**ORIGIN, "Content-Type": "text/plain"}).status_code == 415


@pytest.mark.parametrize("body", [
    {"src": "rx-nowhere", "dst": "rx-web", "port": 80},
    {"src": "internet", "dst": "rx-web", "port": 70000},
    {"src": "internet", "dst": "rx-web", "port": -1},
    {"src": "internet", "dst": "rx-web", "port": True},
    {"src": "internet", "dst": "rx-web", "port": "80"},
    {"src": "10.0.0.0/33", "dst": "rx-web", "port": 80},
    {"src": "internet", "dst": "rx-web", "port": 80, "proto": "sctp"},
    {"src": "internet", "dst": "rx-web", "port": 80, "extra": 1},
    {"src": "internet", "port": 80},
    ["internet", "rx-web", 80],
])
def test_bad_input_is_422(client, body):
    c, _ = client
    assert c.post("/api/reachability", json=body, headers=ORIGIN).status_code == 422


def test_emulator_down_is_503(client):
    c, state = client
    state["network"] = emulator_down(datetime(2026, 10, 31, tzinfo=timezone.utc))
    assert c.post("/api/reachability", json={"src": "internet", "dst": "rx-web", "port": 80},
                  headers=ORIGIN).status_code == 503
