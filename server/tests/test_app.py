import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from cloudy_labs.server.app import create_app
from test_hub import FakeCollector


WS = "ws://127.0.0.1:8730/ws"  # absolute: the test client otherwise sends Host: testserver


@pytest.fixture
def served():
    collector = FakeCollector()
    app = create_app(collector, listen=False)
    with TestClient(app, base_url="http://127.0.0.1:8730") as client:
        yield client, app.state.hub, collector


def test_foreign_host_is_refused(served):
    client, _, _ = served
    assert client.get("/api/graph", headers={"Host": "attacker.example:8730"}).status_code == 400
    assert client.get("/api/graph", headers={"Host": "localhost:8730"}).status_code == 200


def test_health_and_graph(served):
    client, _, _ = served
    assert client.get("/api/health").json() == {"floci": True, "tap": False, "version": 1}
    body = client.get("/api/graph").json()
    assert body["version"] == 1 and body["status"] == "ok" and body["nodes"][0]["kind"] == "region"


def test_websocket_gets_current_graph_then_updates(served):
    client, hub, collector = served
    with client.websocket_connect(WS, headers={"Origin": "http://127.0.0.1:5174"}) as ws:
        assert ws.receive_json()["graph"]["version"] == 1
        collector.vpcs = ["vpc-1"]
        client.portal.call(hub.refresh)
        message = ws.receive_json()
        assert message["type"] == "graph" and message["graph"]["version"] == 2
        client.portal.call(hub.broadcast, {"type": "api-event", "service": "ec2", "action": "CreateVpc", "seq": 3})
        assert ws.receive_json() == {"type": "api-event", "service": "ec2", "action": "CreateVpc", "seq": 3}


def test_websocket_without_origin_is_allowed(served):
    client, _, _ = served
    with client.websocket_connect(WS) as ws:
        assert ws.receive_json()["type"] == "graph"


@pytest.mark.parametrize("origin", ["http://evil.example", "http://127.0.0.1:8080", "null"])
def test_websocket_from_another_origin_is_refused(served, origin):
    client, _, _ = served
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(WS, headers={"Origin": origin}) as ws:
            ws.receive_json()
    assert e.value.code == 1008


def test_listener_events_reach_browsers_and_writes_refresh(served):
    client, hub, collector = served
    with client.websocket_connect(WS) as ws:
        ws.receive_json()
        collector.vpcs = ["vpc-2"]
        listener = client.app.state.listener
        client.portal.call(lambda: listener.handle({"seq": 1, "service": "ec2", "action": "CreateVpc", "write": True}))
        assert ws.receive_json() == {"type": "api-event", "service": "ec2", "action": "CreateVpc", "seq": 1, "write": True}
        message = ws.receive_json()  # after the debounce
        assert message["type"] == "graph" and [n["id"] for n in message["graph"]["nodes"]] == ["us-east-1", "vpc-2"]


# --- builder ---------------------------------------------------------------------------------

from pathlib import Path  # noqa: E402

from cloudy_labs.builder.runner import RunResult, Runner  # noqa: E402
from cloudy_labs.graph.schema import ResourceGraph  # noqa: E402
from cloudy_labs.labs import LabError, load_lab  # noqa: E402
from cloudy_labs.progress import Attempt  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = ResourceGraph.model_validate_json((FIXTURES / "graph" / "lab-06-07.graph.json").read_text())
LAB06 = load_lab("fixture-lab-06", FIXTURES / "labs")
ORIGIN = {"Origin": "http://127.0.0.1:5174"}
VPC = "vpc-149d0439"


class FakeRunner(Runner):
    def __init__(self, result: RunResult):
        super().__init__()
        self.result = result
        self.calls: list[list[str]] = []

    async def run(self, argv):
        self.calls.append(argv)
        return self.result


@pytest.fixture
def builder():
    """An app on the golden lab-06 graph with fixture-lab-06 open and a fake aws CLI."""
    state = {"lab": (LAB06, Attempt(7, "fixture-lab-06", "2026-10-29T00:00:00Z")), "block": None}
    runner = FakeRunner(RunResult(0, '{"Vpc": {"VpcId": "vpc-new1"}}', "", 12))

    def lab():
        if isinstance(state["lab"], Exception):
            raise state["lab"]
        return state["lab"]

    app = create_app(lambda: GOLDEN, listen=False, lab=lab, runner=runner,
                     azs=lambda: ["us-east-1a", "us-east-1b"], blocker=lambda: state["block"])
    with TestClient(app, base_url="http://127.0.0.1:8730") as client:
        yield client, state, runner


def post(client, path, op, params, headers=ORIGIN):
    return client.post(path, json={"op": op, "params": params}, headers=headers)


def test_lab_info(builder):
    client, _, _ = builder
    body = client.get("/api/lab").json()
    assert body["id"] == "fixture-lab-06" and body["attempt"] == 7
    assert body["palette"] == ["vpc", "subnet", "igw", "elastic-ip", "nat", "route-table"]
    assert body["tags"] == {"lab": "fixture-lab-06"} and body["cidrs"] == ["10.66.0.0/16"]
    assert body["azs"] == ["us-east-1a", "us-east-1b"] and body["canRun"] is True and body["runBlocker"] is None
    assert {o["name"] for o in body["ops"]} >= {"create-vpc", "create-route", "modify-subnet-attribute"}
    assert [t["id"] for t in body["tasks"]][0] == "vpc"


def test_lab_info_without_attempt(builder):
    client, state, _ = builder
    state["lab"] = None
    assert client.get("/api/lab").json() == {"id": None}


def test_lab_info_broken_lab(builder):
    client, state, _ = builder
    state["lab"] = LabError("no lab 'ghost'")
    assert client.get("/api/lab").status_code == 409


def test_preview_shows_exact_command(builder):
    client, _, runner = builder
    r = post(client, "/api/preview", "create-vpc", {"name": "lab06-vpc", "cidr": "10.66.0.0/16"})
    assert r.status_code == 200
    body = r.json()
    assert body["problems"] == []
    assert body["command"] == ("aws ec2 create-vpc --cidr-block 10.66.0.0/16 --tag-specifications "
                               "'ResourceType=vpc,Tags=[{Key=Name,Value=lab06-vpc},{Key=lab,Value=fixture-lab-06}]' "
                               "--profile lab --output json")
    assert body["argv"][-4:] == ["--profile", "lab", "--output", "json"]
    assert runner.calls == []  # preview never runs anything


def test_preview_explains_problems(builder):
    client, _, _ = builder
    r = post(client, "/api/preview", "create-subnet", {"name": "x", "vpcId": VPC, "cidr": "10.0.1.5/24", "az": "us-east-1z"})
    assert r.status_code == 200
    fields = {p["field"]: p["message"] for p in r.json()["problems"]}
    assert "host bits" in fields["cidr"] and "us-east-1a, us-east-1b" in fields["az"]


@pytest.mark.parametrize("body, status", [
    ({"op": "delete-vpc", "params": {}}, 422),
    ({"op": "create-vpc", "params": {"name": "x"}}, 422),
    ({"op": "create-vpc", "params": {"name": "x", "cidr": "10.0.0.0/16", "extra": 1}}, 422),
    ({"op": "create-vpc"}, 422),
    ({"command": "aws ec2 delete-vpc"}, 422),
    (["create-vpc"], 422),
])
def test_malformed_requests(builder, body, status):
    client, _, runner = builder
    assert client.post("/api/run", json=body, headers=ORIGIN).status_code == status
    assert runner.calls == []


@pytest.mark.parametrize("headers, status", [
    ({}, 403),
    ({"Origin": "http://evil.example"}, 403),
    ({"Origin": "null"}, 403),
    ({"Origin": "http://127.0.0.1:5174", "Content-Type": "text/plain"}, 415),
    ({"Origin": "http://127.0.0.1:5174", "Content-Type": "application/x-www-form-urlencoded"}, 415),
])
def test_cross_site_writes_are_refused(builder, headers, status):
    client, _, runner = builder
    body = '{"op": "create-vpc", "params": {"name": "x", "cidr": "10.0.0.0/16"}}'
    headers = {"Content-Type": "application/json", **headers}
    assert client.post("/api/run", content=body, headers=headers).status_code == status
    assert runner.calls == []


def test_body_that_is_not_json(builder):
    client, _, _ = builder
    r = client.post("/api/run", content="{nope", headers={**ORIGIN, "Content-Type": "application/json"})
    assert r.status_code == 400


def test_run_returns_output_and_expectation(builder):
    client, _, runner = builder
    r = post(client, "/api/run", "create-vpc", {"name": "lab06-vpc", "cidr": "10.66.0.0/16"})
    assert r.status_code == 200
    body = r.json()
    assert body["exitCode"] == 0 and body["stdout"].startswith('{"Vpc"') and body["durationMs"] == 12
    assert body["expect"] == {"node": "vpc-new1"}
    assert runner.calls == [body["argv"]]


def test_run_failure_has_no_expectation(builder):
    client, _, runner = builder
    runner.result = RunResult(254, "", "An error occurred (VpcLimitExceeded)", 30)
    body = post(client, "/api/run", "create-vpc", {"name": "x", "cidr": "10.66.0.0/16"}).json()
    assert body["exitCode"] == 254 and body["stderr"].startswith("An error") and body["expect"] is None


def test_run_refuses_invalid_op(builder):
    client, _, runner = builder
    r = post(client, "/api/run", "attach-internet-gateway", {"igwId": "igw-34ddd4cd", "vpcId": VPC})
    assert r.status_code == 409
    assert "already attached" in r.json()["problems"][0]["message"]
    assert runner.calls == []


def test_run_without_attempt(builder):
    client, state, runner = builder
    state["lab"] = None
    r = post(client, "/api/run", "create-vpc", {"name": "x", "cidr": "10.66.0.0/16"})
    assert r.status_code == 409 and "labctl start" in r.json()["detail"]
    assert runner.calls == []


def test_run_without_aws_cli(builder):
    client, state, runner = builder
    state["block"] = "the aws CLI is not installed, so the builder can show commands but not run them"
    lab = client.get("/api/lab").json()
    assert lab["canRun"] is False and lab["runBlocker"] == state["block"]
    assert post(client, "/api/preview", "create-vpc", {"name": "x", "cidr": "10.66.0.0/16"}).status_code == 200
    r = post(client, "/api/run", "create-vpc", {"name": "x", "cidr": "10.66.0.0/16"})
    assert r.status_code == 503 and r.json()["detail"] == state["block"]
    assert runner.calls == []


def test_run_refused_while_another_runs(builder):
    client, _, runner = builder
    runner._lock = type("Held", (), {"locked": lambda self: True})()  # the lock as another run holds it
    r = post(client, "/api/run", "create-vpc", {"name": "x", "cidr": "10.66.0.0/16"})
    assert r.status_code == 409 and "still running" in r.json()["detail"]
    assert runner.calls == []


def test_subnet_refused_when_azs_are_unknown():
    app = create_app(lambda: GOLDEN, listen=False, lab=lambda: (LAB06, Attempt(1, "fixture-lab-06", "")),
                     runner=(runner := FakeRunner(RunResult(0, "", "", 1))), azs=lambda: [], blocker=lambda: None)
    params = {"name": "x", "vpcId": VPC, "cidr": "10.0.9.0/24", "az": "file:///etc/hosts"}
    with TestClient(app, base_url="http://127.0.0.1:8730") as client:
        r = post(client, "/api/run", "create-subnet", params)
        assert r.status_code == 409 and r.json()["problems"][0]["field"] == "az"
    assert runner.calls == []


def test_name_with_a_newline_is_refused(builder):
    client, _, _ = builder
    problems = post(client, "/api/preview", "create-vpc", {"name": "lab06-vpc\n", "cidr": "10.66.0.0/16"}).json()["problems"]
    assert [p["field"] for p in problems] == ["name"]


@pytest.mark.parametrize("headers, status", [
    ({}, 403),
    ({"Origin": "http://evil.example"}, 403),
    ({"Origin": "http://127.0.0.1:5174", "Content-Type": "text/plain"}, 415),
])
def test_cross_site_previews_are_refused(builder, headers, status):
    client, _, _ = builder
    body = '{"op": "create-vpc", "params": {"name": "x", "cidr": "10.0.0.0/16"}}'
    assert client.post("/api/preview", content=body, headers={"Content-Type": "application/json", **headers}).status_code == status


def test_op_outside_the_palette(builder):
    client, state, _ = builder
    narrow = load_lab("fixture-lab-06", FIXTURES / "labs")
    narrow.lab = narrow.lab.model_copy(update={"builder": narrow.lab.builder.model_copy(update={"palette": ["vpc"]})})
    state["lab"] = (narrow, state["lab"][1])
    r = post(client, "/api/preview", "create-internet-gateway", {"name": "x"})
    assert r.status_code == 422 and "does not offer" in r.json()["detail"]


def test_run_refused_while_emulator_down():
    down = GOLDEN.model_copy(update={"status": "down"})
    app = create_app(lambda: down, listen=False, lab=lambda: (LAB06, Attempt(1, "fixture-lab-06", "")),
                     runner=FakeRunner(RunResult(0, "", "", 1)), azs=lambda: [], blocker=lambda: None)
    with TestClient(app, base_url="http://127.0.0.1:8730") as client:
        assert post(client, "/api/run", "create-vpc", {"name": "x", "cidr": "10.66.0.0/16"}).status_code == 503
