"""The digital twin against a real emulator: one browser on `/ws` while a learner works each
fixture lab from a shell, with the aws CLI and boto3 through the `lab` profile `labctl up` writes.

Real stack: Floci behind api-tap and the lab-server in this process. Run with
`uv run pytest -m docker tests/test_twin_docker.py -v -s` to see the measured latencies.
"""

import json
import shutil
import socket
import sqlite3
import statistics
import subprocess
import threading
import time
from pathlib import Path

import boto3
import pytest
import uvicorn
from websockets.sync.client import connect

from cloudy_labs.builder.ec2_choices import choices
from cloudy_labs.builder.runner import run_env
from cloudy_labs.cli import main
from cloudy_labs.labs import load_lab
from cloudy_labs.server.app import create_app
from cloudy_labs.server.twin_runner import run_lab_checks

pytestmark = pytest.mark.docker

LAB06 = "fixture-lab-06"
LAB07 = "fixture-lab-07"
RUNS = 5
GRAPH_S = 2.0  # a write shows in the graph
GHOST_S = 3.0  # then its ghost goes
WEB_ANSWERS_S = 90  # UserData keeps starting the web server after the instance reports running
WORLD = "0.0.0.0/0"


@pytest.fixture(autouse=True)
def isolated_home():
    """The module-scoped `lab` fixture owns CLOUDY_LABS_HOME here; do not swap it per test."""


@pytest.fixture(scope="module")
def lab(tmp_path_factory):
    if not shutil.which("aws"):
        pytest.skip("needs the aws CLI on PATH")
    home = tmp_path_factory.mktemp("home")
    labs = tmp_path_factory.mktemp("labs")
    for lab_id in (LAB06, LAB07):
        shutil.copytree(Path(__file__).parent / "fixtures" / "labs" / lab_id, labs / lab_id)
    mp = pytest.MonkeyPatch()
    mp.setenv("CLOUDY_LABS_HOME", str(home))
    mp.setenv("CLOUDY_LABS_LABS_DIR", str(labs))
    mp.setenv("AWS_CONFIG_FILE", str(home / "aws-config"))  # `up` writes the lab profile here
    try:
        assert main(["up"]) == 0
        assert main(["start", LAB06]) == 0
        yield home
    finally:
        main(["down"])  # always, so a failing test leaves no containers behind
        mp.undo()


@pytest.fixture(scope="module")
def ws_url(lab):
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


class Feed:
    """The latest graph and twin one browser has seen."""

    def __init__(self, ws):
        self.ws = ws
        self.graph: dict = {"nodes": []}
        self.twin: dict = {}
        self.graphs = 0  # graph messages received

    def nodes(self) -> set[str]:
        return {n["id"] for n in self.graph["nodes"]}

    def ghosts(self) -> set[str]:
        return {g["id"] for g in self.twin.get("ghosts", [])}

    def passed(self) -> set[str]:
        return {c["id"] for c in self.twin.get("checks", []) if c["status"] == "passed"}

    def wait(self, what: str, pred, timeout: float) -> float:
        """When `pred(self)` first held; fails after `timeout` seconds."""
        deadline = time.monotonic() + timeout
        while not pred(self):
            left = deadline - time.monotonic()
            if left <= 0:
                checks = {c["id"]: c["status"] for c in self.twin.get("checks", [])}
                raise AssertionError(f"{what}: not within {timeout}s; twin checks {checks}, ghosts {sorted(self.ghosts())}")
            try:
                message = json.loads(self.ws.recv(timeout=left))
            except TimeoutError:
                continue
            if message["type"] == "graph":
                self.graph, self.graphs = message["graph"], self.graphs + 1
            elif message["type"] == "twin":
                self.twin = message["twin"]
        return time.monotonic()


def aws(*args: str) -> dict:
    out = subprocess.run(["aws", "--profile", "lab", "--output", "json", *args], env=run_env(),
                         capture_output=True, text=True, timeout=180)
    assert out.returncode == 0, f"aws {' '.join(args[:2])}: {out.stderr}"
    return json.loads(out.stdout) if out.stdout.strip() else {}


def tags(resource_type: str, lab_id: str) -> list[str]:
    return ["--tag-specifications", f"ResourceType={resource_type},Tags=[{{Key=lab,Value={lab_id}}}]"]


def all_ghosts(lab_id: str) -> set[str]:
    return {f"ghost:{n.id}" for n in load_lab(lab_id).lab.target.nodes}


def check_seconds(lab_id: str) -> float:
    loaded = load_lab(lab_id)
    times = []
    for _ in range(RUNS):
        t0 = time.monotonic()
        run_lab_checks(loaded)
        times.append(time.monotonic() - t0)
    return statistics.median(times)


def recorded_runs(home: Path, attempt: int) -> int:
    with sqlite3.connect(home / "progress.db") as db:
        return db.execute("SELECT COUNT(DISTINCT ran_at) FROM check_runs WHERE attempt_id = ?", (attempt,)).fetchone()[0]


def ms(seconds: list[float]) -> str:
    return f"median {statistics.median(seconds) * 1000:.0f} ms, max {max(seconds) * 1000:.0f} ms over {len(seconds)}"


def test_lab_06_ghosts_follow_the_learner_from_a_shell(lab, ws_url, capsys):
    ghosts = all_ghosts(LAB06)
    ec2 = boto3.Session(profile_name="lab").client("ec2")
    with connect(ws_url, open_timeout=10, max_size=None) as ws:
        feed = Feed(ws)
        feed.wait("a fresh attempt: every ghost, no check passed",
                  lambda f: f.twin.get("lab") == LAB06 and f.ghosts() == ghosts and f.twin["checks"] and not f.passed(), 15)
        attempt = feed.twin["attempt"]

        # The VPC from the CLI, five times: in the graph; once both its checks pass (DNS hostnames
        # on), its ghost gone; deleted, the ghost is back.
        to_graph, to_ghost = [], []
        for run in range(RUNS):
            out = aws("ec2", "create-vpc", "--cidr-block", "10.66.0.0/16", *tags("vpc", LAB06))
            t0 = time.monotonic()
            vpc = out["Vpc"]["VpcId"]
            to_graph.append(feed.wait(f"{vpc} in the graph", lambda f: vpc in f.nodes(), 10) - t0)
            assert to_graph[-1] <= GRAPH_S, f"{vpc} took {to_graph[-1]:.2f}s to reach the graph"
            feed.wait("vpc-exists passed, the VPC ghost still there",
                      lambda f: "vpc-exists" in f.passed() and "ghost:vpc" in f.ghosts(), 10)
            aws("ec2", "modify-vpc-attribute", "--vpc-id", vpc, "--enable-dns-hostnames", '{"Value":true}')
            t0 = time.monotonic()
            to_ghost.append(feed.wait("the VPC ghost gone", lambda f: "ghost:vpc" not in f.ghosts(), 10) - t0)
            assert feed.twin["bound"]["vpc"] == vpc
            assert to_ghost[-1] <= GHOST_S, f"the VPC ghost took {to_ghost[-1]:.2f}s to go after its last check passed"
            if run < RUNS - 1:
                aws("ec2", "delete-vpc", "--vpc-id", vpc)
                feed.wait("the VPC ghost back", lambda f: "ghost:vpc" in f.ghosts() and vpc not in f.nodes(), 10)

        # The subnets from boto3, which also goes through api-tap.
        subnet_to_graph, subnets = [], {}
        for name, cidr, az in [("public-1", "10.66.1.0/24", "us-east-1a"), ("public-2", "10.66.2.0/24", "us-east-1b"),
                               ("private-1", "10.66.11.0/24", "us-east-1a"), ("private-2", "10.66.12.0/24", "us-east-1b")]:
            subnet = ec2.create_subnet(VpcId=vpc, CidrBlock=cidr, AvailabilityZone=az)["Subnet"]["SubnetId"]
            t0 = time.monotonic()
            subnet_to_graph.append(feed.wait(f"{subnet} in the graph", lambda f: subnet in f.nodes(), 10) - t0)
            assert subnet_to_graph[-1] <= GRAPH_S, f"{subnet} took {subnet_to_graph[-1]:.2f}s to reach the graph"
            subnets[name] = subnet

        # The rest of the lab from the CLI.
        for name in ("public-1", "public-2"):
            aws("ec2", "modify-subnet-attribute", "--subnet-id", subnets[name], "--map-public-ip-on-launch")
        igw = aws("ec2", "create-internet-gateway", *tags("internet-gateway", LAB06))["InternetGateway"]["InternetGatewayId"]
        aws("ec2", "attach-internet-gateway", "--internet-gateway-id", igw, "--vpc-id", vpc)
        eip = aws("ec2", "allocate-address", "--domain", "vpc")["AllocationId"]
        nat = aws("ec2", "create-nat-gateway", "--subnet-id", subnets["public-1"], "--allocation-id", eip,
                  *tags("natgateway", LAB06))["NatGateway"]["NatGatewayId"]
        aws("ec2", "wait", "nat-gateway-available", "--nat-gateway-ids", nat)
        for side, gateway, names in [("public", ["--gateway-id", igw], ("public-1", "public-2")),
                                     ("private", ["--nat-gateway-id", nat], ("private-1", "private-2"))]:
            table = aws("ec2", "create-route-table", "--vpc-id", vpc, *tags("route-table", LAB06))["RouteTable"]["RouteTableId"]
            aws("ec2", "create-route", "--route-table-id", table, "--destination-cidr-block", WORLD, *gateway)
            for name in names:
                aws("ec2", "associate-route-table", "--route-table-id", table, "--subnet-id", subnets[name])
        feed.wait("every check passed and no ghost left",
                  lambda f: f.twin.get("attempt") == attempt and f.passed() == {c["id"] for c in f.twin["checks"]}
                  and not f.ghosts(), 30)
        assert feed.twin["bound"]["nat"] == nat and feed.twin["bound"]["public-1"] == subnets["public-1"]
        runs = recorded_runs(lab, attempt)
        seconds = check_seconds(LAB06)
        with capsys.disabled():
            assert main(["check", LAB06]) == 0

            # A reset opens a new attempt, and the twin starts over.
            t0 = time.monotonic()
            assert main(["reset", LAB06]) == 0
            t_reset = feed.wait("a new attempt with every ghost back",
                                lambda f: f.twin.get("attempt") not in (None, attempt) and f.ghosts() == ghosts and not f.passed(), 30)
            print(f"\n{LAB06}: write -> graph (CLI VPC) {ms(to_graph)}; last write -> VPC ghost gone {ms(to_ghost)}")
            print(f"{LAB06}: write -> graph (boto3 subnet) {ms(subnet_to_graph)}")
            print(f"{LAB06}: one check run {seconds * 1000:.0f} ms (median of {RUNS}); "
                  f"check_runs recorded by the lab-server during the attempt: {runs}")
            print(f"{LAB06}: labctl reset -> fresh twin on the WebSocket {t_reset - t0:.1f}s")


def test_lab_07_setup_shows_as_reached_and_the_web_server_check_follows(lab, ws_url, capsys):
    assert main(["start", LAB07]) == 0
    with connect(ws_url, open_timeout=10, max_size=None) as ws:
        feed = Feed(ws)
        feed.wait("the network setup built, reached",
                  lambda f: f.twin.get("lab") == LAB07 and "network-ready" in f.passed()
                  and {"vpc", "igw", "az", "public"} <= set(f.twin["bound"]), 20)
        attempt = feed.twin["attempt"]
        assert {"ghost:vpc", "ghost:public"}.isdisjoint(feed.ghosts())
        vpc, public = feed.twin["bound"]["vpc"], feed.twin["bound"]["public"]

        web = aws("ec2", "create-security-group", "--group-name", "web", "--description", "web", "--vpc-id", vpc)["GroupId"]
        aws("ec2", "authorize-security-group-ingress", "--group-id", web, "--protocol", "tcp", "--port", "22", "--cidr", "203.0.113.10/32")
        aws("ec2", "authorize-security-group-ingress", "--group-id", web, "--protocol", "tcp", "--port", "80", "--cidr", WORLD)
        aws("ec2", "create-key-pair", "--key-name", "lab07-key", "--query", "{KeyName:KeyName}")
        offered = choices()
        instance = aws("ec2", "run-instances", "--image-id", offered["images"][0], "--instance-type", offered["instanceTypes"][0],
                       "--subnet-id", public, "--security-group-ids", web, "--key-name", "lab07-key", "--count", "1",
                       "--user-data", load_lab(LAB07).lab.builder.user_data)["Instances"][0]["InstanceId"]
        aws("ec2", "wait", "instance-running", "--instance-ids", instance)
        admin = aws("ec2", "create-security-group", "--group-name", "admin", "--description", "admin", "--vpc-id", vpc)["GroupId"]
        aws("ec2", "modify-instance-attribute", "--instance-id", instance, "--groups", web, admin)

        t0 = time.monotonic()
        feed.wait("every check but the web server passed", lambda f: f.passed() >= {"instance-running", "instance-has-two-sgs"}, 30)
        graphs = feed.graphs
        t_web = feed.wait("the web server answering, with no write to set it off",
                          lambda f: f.twin.get("attempt") == attempt and f.passed() == {c["id"] for c in f.twin["checks"]}
                          and not f.ghosts(), WEB_ANSWERS_S)
        assert feed.twin["bound"]["web"] == instance
        assert {feed.twin["bound"]["sg-web"], feed.twin["bound"]["sg-admin"]} == {web, admin}
        runs = recorded_runs(lab, attempt)
        seconds = check_seconds(LAB07)
        with capsys.disabled():
            assert main(["check", LAB07]) == 0
            print(f"\n{LAB07}: web-server-answers passed {t_web - t0:.1f}s after the last write "
                  f"({feed.graphs - graphs} graph messages meanwhile)")
            print(f"{LAB07}: one check run {seconds * 1000:.0f} ms (median of {RUNS}); "
                  f"check_runs recorded by the lab-server during the attempt: {runs}")
