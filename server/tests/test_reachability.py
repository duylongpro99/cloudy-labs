"""Static reachability over the network recorded on Floci, judged against AWS-documented answers."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from cloudy_labs.graph.collector import collect
from cloudy_labs.reachability import NETWORK_KINDS, EndpointError, analyze, resolve_endpoint
from cloudy_labs.reachability.model import Index
from cloudy_labs.registry import default_registry
from graph_fixtures import FixtureClients

REACH = Path(__file__).parent / "fixtures" / "reachability"
SCENARIOS = yaml.safe_load((REACH / "scenarios.yaml").read_text())
CLOCK = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _name(resource: dict) -> str | None:
    return next((t["Value"] for t in resource.get("Tags") or [] if t["Key"] == "Name"), None)


def _patched_clients() -> FixtureClients:
    """The recording, with the TGW route targets Floci drops put back (patches.yaml)."""
    clients = FixtureClients(root=REACH / "floci")
    ec2 = clients.clients["ec2"]
    vpcs = {_name(v): v["VpcId"] for c in ec2.calls["describe_vpcs"] for v in c["response"]["Vpcs"]}
    tgws = {_name(t): t["TransitGatewayId"]
            for c in ec2.calls["describe_transit_gateways"] for t in c["response"]["TransitGateways"]}
    for patch in yaml.safe_load((REACH / "patches.yaml").read_text()):
        hits = 0
        for call in ec2.calls["describe_route_tables"]:
            for rt in call["response"]["RouteTables"]:
                if rt["VpcId"] != vpcs[patch["vpc"]]:
                    continue
                for route in rt["Routes"]:
                    if route.get("DestinationCidrBlock") == patch["destination"] and not route.get("GatewayId"):
                        route["TransitGatewayId"] = tgws[patch["transit_gateway"]]
                        hits += 1
        assert hits, f"patch matched no route: {patch}"
    return clients


@pytest.fixture(scope="module")
def graph():
    return collect(_patched_clients(), clock=lambda: CLOCK, ports=lambda: {}, kinds=list(NETWORK_KINDS),
                   registry=default_registry())


@pytest.fixture(scope="module")
def index(graph):
    return Index(graph)


@pytest.mark.parametrize("case", SCENARIOS, ids=[c["name"] for c in SCENARIOS])
def test_documented_answer(index, case):
    result = analyze(index, case["src"], case["dst"], case["port"], case.get("proto", "tcp"))
    expect = case["expect"]
    got = {"ok": result.ok}
    if not expect["ok"]:
        got.update(blocked_at=index.label(result.blocked_at), reason=result.reason)
    assert got == expect, [(index.label(h.resource_id), h.verdict, h.reason, h.rule) for h in result.hops]


def test_every_hop_names_a_collected_resource_or_the_internet(index):
    for case in SCENARIOS:
        result = analyze(index, case["src"], case["dst"], case["port"], case.get("proto", "tcp"))
        for hop in result.hops:
            assert hop.resource_id in index.nodes or hop.resource_id == "internet", (case["name"], hop)


def test_result_is_labelled_as_analysis(index):
    data = analyze(index, "internet", "rx-web", 80).to_dict()
    assert data["label"] == "analysed"
    assert set(data) == {"ok", "blockedAt", "reason", "label", "hops"}


@pytest.mark.parametrize("text", ["nope", "rx-missing", "999.1.1.1", "10.0.0.0/33", "", "fe80::1"])
def test_unknown_endpoint_is_rejected(index, text):
    with pytest.raises(EndpointError):
        resolve_endpoint(index, text)


def test_address_endpoints(index):
    inside = resolve_endpoint(index, "10.60.1.200")
    assert inside.subnet and index.label(inside.subnet) == "rx-a-pub" and not inside.public
    outside = resolve_endpoint(index, "198.51.100.7")
    assert outside.subnet is None and outside.public
