"""The data movement kinds (DMS, DataSync, ElastiCache, Athena, Glue, Transfer Family, RDS event
subscriptions): drawn with a real icon in their own view-order band, built only from APIs Floci has,
each create op proved by a contract, and no password or credential ever read into a prop."""
import json
from pathlib import Path

import pytest

from cloudy_labs.registry import CHAT_PROPS_DENY, REGISTRY_DIR, default_registry
from cloudy_labs.registry.hooks import HOOKS

KINDS = [
    "dms-replication-instance", "dms-endpoint", "dms-replication-task",
    "datasync-location", "datasync-task",
    "elasticache-replication-group", "elasticache-cache-cluster",
    "athena-workgroup", "glue-database", "glue-crawler", "transfer-server",
    "rds-event-subscription",
]
ICONS = Path(__file__).resolve().parents[2] / "aws-icon-pkg"
FLOCI = json.loads((REGISTRY_DIR / "floci-ops-2.3.0.json").read_text())["services"]


@pytest.fixture(scope="module")
def registry():
    return default_registry()


@pytest.mark.parametrize("kind", KINDS)
def test_each_kind_is_drawn_with_a_real_icon_in_its_band(registry, kind: str) -> None:
    view = registry.by_kind[kind].view
    assert 650 <= view.order <= 699
    assert view.source and (ICONS / view.source).is_file(), view.source
    assert view.source.endswith("/" + view.icon)


def test_view_orders_of_the_band_are_unique(registry) -> None:
    orders = [t.view.order for t in registry.types if t.kind in KINDS]
    assert len(orders) == len(set(orders))
    others = {t.view.order for t in registry.types if t.kind not in KINDS}
    assert not others & set(orders)


@pytest.mark.parametrize("kind", KINDS)
def test_every_op_uses_an_api_floci_has(registry, kind: str) -> None:
    t = registry.by_kind[kind]
    for op in t.ops:
        service = op.service or t.service
        assert op.api in FLOCI[service]["supported"], f"{op.id}: {service} {op.api}"


@pytest.mark.parametrize("kind", KINDS)
def test_each_kind_can_be_created_changed_and_deleted_by_its_contract(registry, kind: str) -> None:
    t = registry.by_kind[kind]
    gestures = {op.gesture for op in t.ops}
    assert {"create", "delete"} <= gestures
    own = {op.id: op for op in t.ops}
    assert t.contract and t.contract.create.op in own and own[t.contract.create.op].gesture == "create"
    then = [own[s.op].gesture for s in t.contract.then if s.op in own]
    assert then and then[-1] == "delete", "the contract ends by deleting what it made"
    for step in [*t.contract.needs, t.contract.create, *t.contract.then]:
        for name, value in step.params.items():
            assert isinstance(value, str), f"{step.op}.{name} must be a string"


@pytest.mark.parametrize("kind", KINDS)
def test_no_prop_reads_a_password_or_key(registry, kind: str) -> None:
    t = registry.by_kind[kind]
    for name, spec in t.props.items():
        assert not any(w in name.lower() for w in CHAT_PROPS_DENY), f"{kind}.{name}"
        if isinstance(spec, str):
            assert not any(f in spec for f in ("Password", "Secret", "AuthToken", "HostKey")), f"{kind}.{name} reads {spec!r}"
    assert set(t.chat_props) <= set(t.props)


def test_the_rds_event_subscription_links_its_sources_and_topic(registry) -> None:
    t = registry.by_kind["rds-event-subscription"]
    assert {(e.kind, tuple(e.to)) for e in t.edges} >= {
        ("watches", ("db-instance",)),
        ("watches", ("db-cluster",)),
        ("notifies", ("sns-topic",)),
    }


def test_replication_group_members_are_not_drawn_twice(registry) -> None:
    t = registry.by_kind["elasticache-cache-cluster"]
    assert any(f.path == "ReplicationGroupId" and f.in_ == [None] for f in t.filter)


def test_an_s3_uri_names_its_bucket():
    hook = HOOKS["common.s3_uri_bucket"]
    assert hook(None, None, {"LocationUri": "s3://raw-data/in/"}, {"field": "LocationUri"}) == {"_Buckets": ["arn:aws:s3:::raw-data"]}
    paths = {"T": [{"Path": "s3://a/x/"}, {"Path": "s3://a/y/"}, {"Path": "s3://b"}, {"Path": "jdbc://db"}]}
    assert hook(None, None, paths, {"field": "T[].Path", "as": "_B"}) == {"_B": ["arn:aws:s3:::a", "arn:aws:s3:::b"]}
    assert hook(None, None, {"LocationUri": "nfs://10.0.0.5/share/"}, {"field": "LocationUri"}) == {}
    assert hook(None, None, {}, {"field": "LocationUri"}) == {}


@pytest.mark.parametrize(("kind", "edge"), [
    ("datasync-location", "uses-bucket"), ("athena-workgroup", "delivers-to"),
    ("glue-crawler", "crawls"), ("glue-database", "located-in"),
])
def test_kinds_that_name_a_bucket_by_uri_point_at_it(registry, kind: str, edge: str) -> None:
    t = registry.by_kind[kind]
    assert any(e.kind == edge and e.to == ["s3-bucket"] and e.target == "_Buckets" for e in t.edges)
    assert any(e.hook == "common.s3_uri_bucket" for e in t.enrich)
