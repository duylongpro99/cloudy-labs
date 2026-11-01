import pytest
import yaml

from cloudy_labs.graph.schema import ResourceGraph
from cloudy_labs.registry import REGISTRY_DIR, ResourceType, default_registry, load_registry
from cloudy_labs.registry.hooks import HOOKS

from graph_fixtures import LAB_KINDS, FakeEc2, FakeProvider, LATER, dns_hostnames, lab_graph, ports, raw


def entry(**over):
    base = {"kind": "thing", "service": "svc", "label": "Thing", "list": {"method": "list_things", "items": "Things"},
            "id": "Id", "parent": [{"kind": "region"}], "view": {"icon": "Thing_48.svg"}}
    return {**base, **over}


def write(tmp_path, *entries):
    (tmp_path / "x.yaml").write_text(yaml.safe_dump(list(entries)))
    return tmp_path


def test_the_shipped_registry_loads_and_keeps_the_old_parent_rules():
    r = default_registry()
    old = {
        "region": {"account"}, "global": {"account"}, "vpc": {"region"}, "key-pair": {"region"}, "elastic-ip": {"region"}, "igw": {"region", "vpc"},
        "az": {"vpc"}, "route-table": {"vpc"}, "security-group": {"vpc"},
        "subnet-public": {"az"}, "subnet-private": {"az"},
        "nat": {"subnet-public", "subnet-private"}, "instance": {"subnet-public", "subnet-private"},
    }
    parents = r.parent_kinds()
    assert {k: parents[k] for k in old} == old
    assert parents["iam-role"] == {"global"} and parents["db-instance"] == {"db-cluster", "db-subnet-group", "region"}
    assert {"association", "attached", "route", "uses-key"} <= set(r.edge_kinds())
    assert {"vpc", "subnet", "igw", "elastic-ip", "nat", "route-table", "security-group", "key-pair", "instance"} <= set(r.builder_kinds())
    assert "region" not in r.target_kinds() and "az" in r.target_kinds()


def test_every_hook_named_in_the_shipped_yaml_exists():
    text = "\n".join(p.read_text() for p in REGISTRY_DIR.glob("*.yaml"))
    for name in __import__("re").findall(r"hook: ([\w.]+)", text):
        assert name in HOOKS


@pytest.mark.parametrize(
    "bad, needle",
    [
        (entry(parent=[{"kind": "nowhere"}]), "parent kind 'nowhere'"),
        (entry(edges=[{"kind": "x", "target": "A", "to": "ghost"}]), "edge to unknown kind"),
        (entry(filter={"hook": "no.such.hook"}), "unknown hook"),
        (entry(props={"a": "A"}, chat_props=["b"]), "chat_props"),
        (entry(id="A[[["), "Expected|Invalid|Unexpected|Lexer|Parse"),
        (entry(surprise=1), "Extra inputs"),
        (entry(view={"role": "block"}), "a block view needs an icon"),
        (entry(list={"method": "list_things"}), "needs items"),
        (entry(list={"scope": {"parent_kind": "nowhere", "param": "Id", "field": "Id"}, "method": "m", "items": "X"}),
         "scope parent kind 'nowhere'"),
    ],
)
def test_bad_entries_fail_to_load(tmp_path, bad, needle):
    with pytest.raises(Exception, match=needle):
        load_registry(write(tmp_path, bad))


def test_a_kind_declared_twice_fails(tmp_path):
    with pytest.raises(ValueError, match="'vpc' is declared twice"):
        load_registry(write(tmp_path, entry(kind="vpc")))


def test_parent_cycles_fail(tmp_path):
    with pytest.raises(ValueError, match="cycle"):
        load_registry(write(tmp_path, entry(kind="a", parent=[{"kind": "b", "path": "B"}]),
                            entry(kind="b", parent=[{"kind": "a", "path": "A"}])))


def test_entries_are_strict_models():
    with pytest.raises(Exception):
        ResourceType.model_validate(entry(view={"role": "spinning"}))


def test_protected_items_are_hidden(tmp_path, monkeypatch):
    from cloudy_labs.graph.collector import collect

    hidden = entry(kind="any-vpc", service="ec2", list={"method": "describe_vpcs", "items": "Vpcs"}, id="VpcId",
                   protected="IsDefault")
    monkeypatch.setenv("CLOUDY_LABS_REGISTRY_EXTRA", str(write(tmp_path, hidden)))
    default_registry.cache_clear()
    try:
        provider = FakeProvider({"ec2": FakeEc2(raw(), dns=dns_hostnames())})
        g = collect(provider, clock=lambda: LATER, ports=ports, kinds=["any-vpc"], registry=default_registry())
    finally:
        default_registry.cache_clear()
    defaults = {v["VpcId"] for v in raw()["Vpcs"] if v.get("IsDefault")}
    assert defaults and {n.id for n in g.nodes if n.kind == "any-vpc"}.isdisjoint(defaults)
    assert {n.id for n in g.nodes if n.kind == "any-vpc"}


def test_a_failing_service_drops_only_its_kinds_and_warns(extra_registry):
    from cloudy_labs.graph.collector import collect

    class Broken:
        def can_paginate(self, method):
            return False

        def describe_db_instances(self, **_):
            raise TimeoutError("read timed out")

    registry = extra_registry("rds-broken")
    provider = FakeProvider({"ec2": FakeEc2(raw(), dns=dns_hostnames()), "rds": Broken()})
    g = collect(provider, clock=lambda: LATER, ports=ports, kinds=[*LAB_KINDS, "test-db"], registry=registry)
    assert g.status == "ok"
    assert {n.kind for n in g.nodes} >= {"vpc", "instance"} and "test-db" not in {n.kind for n in g.nodes}
    assert any(w.startswith("service rds lỗi: TimeoutError") for w in g.warnings)


def test_every_service_failing_raises_for_the_hub_to_judge(extra_registry):
    from cloudy_labs.graph.collector import collect

    with pytest.raises(TimeoutError):
        collect(FakeProvider(FakeEc2(raw(), fail=TimeoutError("slow"))), clock=lambda: LATER, ports=ports, kinds=LAB_KINDS)


def test_a_test_only_kind_needs_nothing_but_its_entry(extra_registry):
    from cloudy_labs.graph.collector import collect

    registry = extra_registry("test-only")
    provider = FakeProvider({"ec2": FakeEc2(raw(), dns=dns_hostnames())})
    g = collect(provider, clock=lambda: LATER, ports=ports, registry=registry)
    node = next(n for n in g.nodes if n.kind == "test-only")
    assert node.id == "test-only-1" and node.label == "test-only"
    assert {c.parent for c in g.contains if c.child == node.id} == {"ap-southeast-2"}
    ResourceGraph.model_validate_json(g.to_json())  # the graph schema accepts it too


def test_the_graph_schema_rejects_kinds_the_registry_lacks():
    g = lab_graph().to_dict()
    g["nodes"][0]["kind"] = "warp-drive"
    with pytest.raises(Exception, match="not in the registry"):
        ResourceGraph.model_validate(g)


def test_public_view_lists_kinds_and_edge_kinds():
    view = default_registry().public()
    kinds = {k["kind"]: k for k in view["kinds"]}
    assert kinds["instance"]["icon"] == "Res_Amazon-EC2_Instance_48.svg" and kinds["instance"]["role"] == "block"
    edges = view["edgeKinds"]
    assert edges == sorted(edges, key=lambda e: e["kind"])
    assert [e for e in edges if e["kind"] in {"association", "attached", "route", "uses-key"}] == [
        {"kind": "association", "style": "association"}, {"kind": "attached", "style": "attach"},
        {"kind": "route", "style": "route"}, {"kind": "uses-key", "style": "reference"}]
    assert {"kind": "replicates-to", "style": "replica"} in edges


def test_public_view_names_each_kind_service_as_api_tap_reports_it():
    kinds = {k["kind"]: k for k in default_registry().public()["kinds"]}
    assert kinds["route-table"]["signingName"] == "ec2"
    assert kinds["cloudwatch-alarm"]["signingName"] == "monitoring"
    assert kinds["apigateway-http-api"]["signingName"] == "apigateway"
    assert kinds["load-balancer"]["signingName"] == "elasticloadbalancing"
    assert kinds["region"]["signingName"] == kinds["region"]["service"]  # structural: no AWS service


def test_tags_skip_entries_without_a_key():
    pairs = [{"Key": "env", "Value": "lab"}, {"Value": "orphan"}, {"Key": "Name", "Value": "x"}, "junk", {"Key": "k"}]
    assert HOOKS["common.tags"](None, {"Tags": pairs}, {}) == {"tags": {"env": "lab", "k": ""}}


def test_the_private_ip_guard_ignores_a_malformed_address():
    class Ctx:
        warnings: list[str] = []

        def listed(self, service, method, items):
            return [{"SubnetId": "subnet-1", "CidrBlock": "not-a-cidr"}, {"SubnetId": "subnet-2", "CidrBlock": "10.0.1.0/24"}]

    guard, ctx = HOOKS["ec2.private_ip_guard"], Ctx()
    assert guard(ctx, {"InstanceId": "i-1", "SubnetId": "subnet-1", "PrivateIpAddress": "10.0.0.5"}, {}) == {}
    assert guard(ctx, {"InstanceId": "i-2", "SubnetId": "subnet-2", "PrivateIpAddress": "10.0.1.999"}, {}) == {}
    assert guard(ctx, {"InstanceId": "i-3", "SubnetId": "subnet-2", "PrivateIpAddress": "172.17.0.2"}, {}) == {"privateIpOutOfCidr": True}
    assert len(ctx.warnings) == 1
