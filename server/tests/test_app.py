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
