import copy
import json
import os
import random
from datetime import timedelta


from cloudy_labs.graph.collector import USER_DATA_NOTE, collect
from cloudy_labs.graph.host_ports import parse_ps

from graph_fixtures import GOLDEN, INSTANCE, LAB_KINDS, LAUNCHED, LATER, FakeEc2, FakeProvider, dns_hostnames, lab_graph, ports, raw


def by_id(g):
    return {n.id: n for n in g.nodes}


def parent_of(g):
    return {c.child: c.parent for c in g.contains}


def edge_set(g):
    return {(e.kind, e.from_, e.to, e.label) for e in g.edges}


def test_lab_06_07_structure():
    g = lab_graph()
    nodes, parent = by_id(g), parent_of(g)
    vpc = "vpc-149d0439"
    assert parent[vpc] == "ap-southeast-2" and nodes[vpc].label == "lab06-vpc"
    assert {s: nodes[s].kind for s in ("subnet-83a1f79a", "subnet-b893d7ba", "subnet-e917cc42", "subnet-44acdeb7")} == {
        "subnet-83a1f79a": "subnet-public", "subnet-b893d7ba": "subnet-public",
        "subnet-e917cc42": "subnet-private", "subnet-44acdeb7": "subnet-private",
    }
    assert parent["subnet-83a1f79a"] == f"{vpc}/ap-southeast-2a" and parent[f"{vpc}/ap-southeast-2a"] == vpc
    assert parent["subnet-b893d7ba"] == f"{vpc}/ap-southeast-2b"
    assert parent["igw-34ddd4cd"] == vpc
    assert parent["nat-235f142ec41b5d904"] == "subnet-83a1f79a"
    assert parent[INSTANCE] == "subnet-83a1f79a"
    for rt in ("rtb-509e5b33", "rtb-02888668", "rtb-157470092a6fefa4a"):
        assert parent[rt] == vpc and nodes[rt].kind == "route-table"
    assert parent["sg-dbd2e6007fa2e7eef"] == vpc
    assert parent["key-856759379e524ce96"] == "ap-southeast-2"
    assert parent["eipalloc-2cc57421a05781343"] == "ap-southeast-2"
    edges = edge_set(g)
    assert ("route", "rtb-509e5b33", "igw-34ddd4cd", "0.0.0.0/0") in edges
    assert ("route", "rtb-02888668", "nat-235f142ec41b5d904", "0.0.0.0/0") in edges
    assert {("association", "rtb-509e5b33", s, "") for s in ("subnet-83a1f79a", "subnet-b893d7ba")} <= edges
    assert {("association", "rtb-02888668", s, "") for s in ("subnet-e917cc42", "subnet-44acdeb7")} <= edges
    assert ("attached", "sg-dbd2e6007fa2e7eef", INSTANCE, "") in edges
    assert ("attached", "eipalloc-2cc57421a05781343", "nat-235f142ec41b5d904", "") in edges
    assert ("uses-key", INSTANCE, "key-856759379e524ce96", "") in edges
    assert not any(kind == "route" and label == "10.0.0.0/16" for kind, _, _, label in edges)  # local routes skipped


def test_main_route_table_decides_subnets_without_an_association():
    data = raw()
    for rt in data["RouteTables"]:  # drop the public table's explicit associations
        if rt["RouteTableId"] == "rtb-509e5b33":
            rt["Associations"] = []
        if rt["RouteTableId"] == "rtb-157470092a6fefa4a":  # and give the main table the IGW route
            rt["Routes"].append({"DestinationCidrBlock": "0.0.0.0/0", "GatewayId": "igw-34ddd4cd"})
    nodes = by_id(lab_graph(data=data))
    assert nodes["subnet-83a1f79a"].kind == "subnet-public"
    assert nodes["subnet-e917cc42"].kind == "subnet-private"  # still explicitly on the NAT table


def test_instance_is_placed_by_subnet_and_flags_ip_outside_cidr():
    g = lab_graph()
    props = by_id(g)[INSTANCE].props
    assert props["privateIp"] == "10.240.0.11" and props["privateIpOutOfCidr"] is True
    assert any(INSTANCE in w and "10.0.1.0/24" in w for w in g.warnings)
    assert "reservationId" not in json.dumps(g.to_dict()).lower().replace("_", "")


def test_loopback_public_ip_becomes_host_ports():
    props = by_id(lab_graph()).get(INSTANCE).props
    assert props["hostPorts"] == {"22/tcp": 2200, "80/tcp": 30000}
    assert "publicIp" not in props
    props = by_id(lab_graph(host_ports={}))[INSTANCE].props
    assert "hostPorts" not in props and "publicIp" not in props


def test_user_data_note_only_shortly_after_launch():
    assert by_id(lab_graph(now=LAUNCHED + timedelta(minutes=2)))[INSTANCE].props["note"] == USER_DATA_NOTE
    assert "note" not in by_id(lab_graph(now=LAUNCHED + timedelta(minutes=7)))[INSTANCE].props
    no_data = lab_graph(LAUNCHED + timedelta(minutes=2), user_data_={})
    assert "note" not in by_id(no_data)[INSTANCE].props


def test_gone_resources_are_skipped_and_pending_kept():
    data = raw()
    data["NatGateways"][0]["State"] = "deleted"
    data["Reservations"][0]["Instances"][0]["State"] = {"Name": "terminated"}
    nodes = by_id(lab_graph(data=data))
    assert "nat-235f142ec41b5d904" not in nodes and INSTANCE not in nodes
    data = raw()
    data["Reservations"][0]["Instances"][0]["State"] = {"Name": "pending"}
    assert by_id(lab_graph(data=data))[INSTANCE].props["state"] == "pending"


def test_same_input_gives_identical_bytes_whatever_the_order():
    first = lab_graph().to_json(indent=2)
    assert lab_graph().to_json(indent=2) == first
    rng = random.Random(7)
    for _ in range(5):
        shuffled = copy.deepcopy(raw())
        for items in shuffled.values():
            rng.shuffle(items)
        for rt in shuffled["RouteTables"]:
            rng.shuffle(rt["Routes"])
            rng.shuffle(rt["Associations"])
        assert lab_graph(data=shuffled).to_json(indent=2) == first


def test_golden_graph():
    text = lab_graph().to_json(indent=2) + "\n"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(text)
    assert GOLDEN.exists(), "run with UPDATE_GOLDEN=1 to create the golden graph"
    assert text == GOLDEN.read_text(), "graph differs from the golden file; rerun with UPDATE_GOLDEN=1 if the change is intended"


def test_parse_docker_ps_maps_forwarders_to_their_instance():
    out = (
        "floci-aws-ec2-fwd-i-abc-8080\t0.0.0.0:30001->8080/tcp, [::]:30001->8080/tcp\n"
        "floci-aws-ec2-i-abc\t0.0.0.0:2201->22/tcp\n"
        "floci-aws-ec2-i-def\t\n"
        "cloudy-labs-floci-1\t127.0.0.1:4567->4566/tcp\n"
    )
    assert parse_ps(out) == {"i-abc": {"22/tcp": 2201, "8080/tcp": 30001}}


def test_collect_reads_floci_directly_and_asks_user_data_only_for_fresh_instances():
    provider = FakeProvider(FakeEc2(raw(), dns=dns_hostnames(), user_data={INSTANCE: True}))
    g = collect(provider, clock=lambda: LATER, ports=ports, kinds=LAB_KINDS)
    assert provider.calls == [("ec2", True), ("sts", True)]  # sts: the account id; the fake has none
    assert provider.clients["ec2"].attribute_calls == []
    assert g.to_json() == lab_graph().to_json()
    g = collect(provider, clock=lambda: LAUNCHED + timedelta(minutes=1), ports=ports, kinds=LAB_KINDS)
    assert provider.clients["ec2"].attribute_calls == [INSTANCE]
    assert by_id(g)[INSTANCE].props["note"] == USER_DATA_NOTE


def test_collect_reports_emulator_down_when_floci_does_not_answer():
    from botocore.exceptions import EndpointConnectionError

    g = collect(FakeProvider(FakeEc2(raw(), fail=EndpointConnectionError(endpoint_url="http://127.0.0.1:4567"))),
                clock=lambda: LATER, ports=ports, kinds=["vpc", "instance"])
    assert g.status == "emulator-down" and [n.kind for n in g.nodes] == ["account", "region", "global"]
    assert {(c.parent, c.child) for c in g.contains} == {("000000000000", "ap-southeast-2"), ("000000000000", "global")}
    assert g.edges == []


def test_builder_attributes_become_props():
    nodes = by_id(lab_graph())
    assert nodes["vpc-149d0439"].props["enableDnsHostnames"] is True
    flags = {n.id: n.props["mapPublicIpOnLaunch"] for n in nodes.values() if n.kind.startswith("subnet")}
    assert flags["subnet-83a1f79a"] is True and flags["subnet-e917cc42"] is False
    unknown = by_id(lab_graph(dns={}))["vpc-149d0439"]
    assert "enableDnsHostnames" not in unknown.props  # not asked: left out, not reported as off


def test_a_lab_lists_its_palette_target_reachability_and_seen_kinds():
    from cloudy_labs.graph.collector import REACHABILITY_KINDS, lab_kinds
    from cloudy_labs.registry import default_registry

    reg = default_registry()
    assert lab_kinds(reg, [], []) is None  # a lab that names no kind lists everything
    kinds = lab_kinds(reg, ["vpc", "subnet"], ["igw"], seen={"key-pair"})
    assert {"vpc", "subnet-public", "subnet-private", "igw", "key-pair"} <= set(kinds)
    assert REACHABILITY_KINDS & set(reg.kinds()) <= set(kinds)  # a lab with subnets gets every reachability kind
    assert "instance" not in kinds and "elastic-ip" not in kinds
    assert lab_kinds(reg, ["key-pair"], []) == ["key-pair"]  # no network kind, no reachability kinds
    # What a palette kind's ops make is listed too, though no palette offers it.
    assert {"lambda-function", "lambda-version", "lambda-alias"} <= set(lab_kinds(reg, ["lambda-function"], []))


def test_a_write_names_the_kinds_it_may_have_touched():
    from cloudy_labs.graph.collector import kinds_of_action
    from cloudy_labs.registry import default_registry

    reg = default_registry()
    assert kinds_of_action(reg, "ec2", "CreateVpc") == {"vpc"}
    assert kinds_of_action(reg, "ec2", "AuthorizeSecurityGroupIngress") == {"security-group"}
    assert kinds_of_action(reg, "ec2", "CreateNatGateway") == {"nat"}
    assert kinds_of_action(reg, "ec2", "CreateTransitGateway") == {"transit-gateway"}
    every_ec2 = kinds_of_action(reg, "ec2", "CreateDhcpOptions")  # no kind of its own: list all of ec2
    assert {"vpc", "instance", "nat", "elastic-ip", "transit-gateway"} <= every_ec2
    assert kinds_of_action(reg, "nosuchservice", "CreateThing") == set()
    assert kinds_of_action(reg, "lambda", "PublishVersion") == {"lambda-function", "lambda-version"}


def test_a_signing_name_several_services_share_reaches_each_of_their_kinds():
    # api-tap reports the SigV4 name: `rds` is also DocumentDB and Neptune, `elasticloadbalancing`
    # both ELB APIs, `events` EventBridge's two models, `apigateway` both API Gateway APIs.
    from cloudy_labs.graph.collector import kinds_of_action
    from cloudy_labs.registry import default_registry

    reg = default_registry()
    assert kinds_of_action(reg, "rds", "CreateDBInstance") == {"db-instance"}
    assert kinds_of_action(reg, "elasticloadbalancing", "CreateTargetGroup") == {"target-group"}
    assert kinds_of_action(reg, "events", "PutRule") == {"event-rule"}
    assert kinds_of_action(reg, "apigateway", "CreateRestApi") == {"apigateway-rest-api"}
    assert kinds_of_action(reg, "apigateway", "CreateApi") == {"apigateway-http-api"}


def test_a_kind_listed_per_parent_brings_that_parent_in():
    from cloudy_labs.graph.collector import _with_parents
    from cloudy_labs.registry import default_registry
    reg = default_registry()
    scoped = next(t for t in reg.types if t.listing and t.listing.scope)
    assert scoped.listing.scope.parent_kind in _with_parents(reg, [scoped.kind])
