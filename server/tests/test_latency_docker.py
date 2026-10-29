"""Time from a learner's write (through api-tap) to the new graph on the WebSocket.

Run with `uv run pytest -m docker tests/test_latency_docker.py -s` to see p50/p95.
"""

import json
import socket
import statistics
import threading
import time

import boto3
import pytest
import uvicorn
from websockets.sync.client import connect

from cloudy_labs.emulator import stack
from cloudy_labs.server.app import create_app

pytestmark = pytest.mark.docker

RUNS = 20
P95_LIMIT_S = 2.0


@pytest.fixture(scope="module")
def emulator():
    was_running = stack.is_running()
    stack.up()
    yield
    if not was_running:  # leave a stack the learner started alone
        stack.down()


@pytest.fixture
def server(emulator):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not srv.started:
        assert time.monotonic() < deadline, "lab-server did not start"
        time.sleep(0.05)
    yield f"ws://127.0.0.1:{port}/ws"
    srv.should_exit = True
    thread.join(10)


def wait_for(ws, node_id: str, timeout: float = 10.0) -> float:
    deadline = time.monotonic() + timeout
    while True:
        message = json.loads(ws.recv(timeout=max(deadline - time.monotonic(), 0.01)))
        if message["type"] == "graph" and any(n["id"] == node_id for n in message["graph"]["nodes"]):
            return time.monotonic()


def test_write_reaches_the_websocket_within_two_seconds(server):
    ec2 = boto3.client("ec2", endpoint_url="http://127.0.0.1:4566", region_name="us-east-1",
                       aws_access_key_id="test", aws_secret_access_key="test")
    vpc = ec2.create_vpc(CidrBlock="10.99.0.0/16")["Vpc"]["VpcId"]
    subnets, latencies = [], []
    try:
        with connect(server, open_timeout=10) as ws:
            wait_for(ws, vpc)
            for i in range(RUNS):
                subnet = ec2.create_subnet(VpcId=vpc, CidrBlock=f"10.99.{i}.0/24", AvailabilityZone="us-east-1a")["Subnet"]["SubnetId"]
                t0 = time.monotonic()
                subnets.append(subnet)
                latencies.append(wait_for(ws, subnet) - t0)
    finally:
        for subnet in subnets:
            ec2.delete_subnet(SubnetId=subnet)
        ec2.delete_vpc(VpcId=vpc)
    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(0.95 * len(latencies)) - 1] if len(latencies) >= 20 else latencies[-1]
    print(f"\nwrite -> WebSocket over {RUNS} runs: p50 {p50 * 1000:.0f} ms, p95 {p95 * 1000:.0f} ms, max {latencies[-1] * 1000:.0f} ms")
    assert p95 <= P95_LIMIT_S
