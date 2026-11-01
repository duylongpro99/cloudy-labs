"""The governance and security kinds (CloudTrail, Config, Cognito, Budgets, Organizations, GuardDuty,
Inspector, Security Hub, Network Firewall, Control Tower): drawn with a real icon in their own
view-order band, built only from APIs Floci has, every builder kind proved by a contract, read
without any secret, email or provider credential, and named by the coverage dictionary."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cloudy_labs.builder.catalog import op_named, prepare
from cloudy_labs.coverage.extract import dictionary
from cloudy_labs.graph.collector import CollectContext, build_graph
from cloudy_labs.graph.schema import ResourceGraph
from cloudy_labs.registry import CHAT_PROPS_DENY, REGISTRY_DIR, default_registry

KINDS = [
    "cloudtrail-trail", "config-recorder", "config-rule", "cognito-user-pool", "cognito-identity-provider",
    "cognito-identity-pool", "budget", "organization", "organizational-unit", "org-account",
    "guardduty-detector", "inspector", "securityhub-hub", "network-firewall", "firewall-policy",
    "firewall-rule-group", "landing-zone",
]
BUILDER = {
    "cloudtrail-trail", "config-recorder", "config-rule", "cognito-user-pool", "cognito-identity-provider",
    "cognito-identity-pool", "budget", "network-firewall", "firewall-policy", "firewall-rule-group",
}
GLOBAL = {"budget", "organization", "organizational-unit", "org-account"}
ICONS = Path(__file__).resolve().parents[2] / "aws-icon-pkg"
FLOCI = json.loads((REGISTRY_DIR / "floci-ops-2.3.0.json").read_text())["services"]
REGION = "ap-southeast-2"
OTHER = "us-east-1"
ACCOUNT = "000000000000"
TRAIL = f"arn:aws:cloudtrail:{REGION}:{ACCOUNT}:trail/audit"
ROOT = "r-ab12"


@pytest.fixture(scope="module")
def registry():
    return default_registry()


def graph(registry, raw: dict[str, list[dict]]) -> ResourceGraph:
    ctx = CollectContext(clients=lambda s: None, now=datetime(2026, 1, 1, tzinfo=timezone.utc), ports=lambda: {}, region=REGION)
    return build_graph(registry, raw, ctx, regions=[REGION, OTHER], account=ACCOUNT)


@pytest.mark.parametrize("kind", KINDS)
def test_each_kind_is_drawn_with_a_real_icon_in_its_band(registry, kind: str) -> None:
    view = registry.by_kind[kind].view
    assert 700 <= view.order <= 749
    assert view.source and (ICONS / view.source).is_file(), view.source
    assert view.source.endswith("/" + view.icon)


def test_view_orders_of_the_band_are_unique(registry) -> None:
    orders = [registry.by_kind[k].view.order for k in KINDS]
    assert len(orders) == len(set(orders))
    others = {t.view.order for t in registry.types if t.kind not in KINDS}
    assert not others & set(orders)


@pytest.mark.parametrize("kind", KINDS)
def test_global_services_sit_under_the_global_group(registry, kind: str) -> None:
    t = registry.by_kind[kind]
    if kind in GLOBAL:
        assert t.scope == "global" and [p.kind for p in t.parent] == ["global"]
    else:
        assert t.scope == "regional" and "global" not in [p.kind for p in t.parent]


@pytest.mark.parametrize("kind", KINDS)
def test_every_op_uses_an_api_floci_has(registry, kind: str) -> None:
    t = registry.by_kind[kind]
    for op in t.ops:
        service = op.service or t.service
        assert op.api in FLOCI[service]["supported"], f"{op.id}: {service} {op.api}"


@pytest.mark.parametrize("kind", sorted(BUILDER))
def test_each_builder_kind_can_be_created_and_deleted_and_its_contract_creates_it(registry, kind: str) -> None:
    t = registry.by_kind[kind]
    assert t.builder
    assert {"create", "delete"} <= {op.gesture for op in t.ops}
    own = {op.id: op for op in t.ops}
    assert t.contract and own[t.contract.create.op].gesture == "create"
    for step in [*t.contract.needs, t.contract.create, *t.contract.then]:
        for name, value in step.params.items():
            assert isinstance(value, str), f"{step.op}.{name} must be a string"


@pytest.mark.parametrize("kind", sorted(set(KINDS) - BUILDER))
def test_the_read_only_kinds_offer_no_ops(registry, kind: str) -> None:
    t = registry.by_kind[kind]
    assert not t.builder and not t.ops


@pytest.mark.parametrize("kind", KINDS)
def test_no_prop_reads_a_secret_email_or_provider_credential(registry, kind: str) -> None:
    t = registry.by_kind[kind]
    for name, spec in t.props.items():
        assert not any(w in name.lower() for w in CHAT_PROPS_DENY), f"{kind}.{name}"
        if isinstance(spec, str):
            # The user pool's password policy (a minimum length) is a setting, not a secret.
            assert not any(f in spec for f in ("ProviderDetails", "ClientSecret", "Email", "TemporaryPassword")), f"{kind}.{name}"
    assert set(t.chat_props) <= set(t.props)


def test_an_identity_provider_never_reads_its_provider_details(registry) -> None:
    """ProviderDetails holds the OIDC client secret or the SAML metadata; only the mapping is picked."""
    enrich = registry.by_kind["cognito-identity-provider"].enrich
    assert [e.method for e in enrich] == ["describe_identity_provider"]
    assert enrich[0].pick and "ProviderDetails" not in enrich[0].pick
    assert "IdentityProvider.{" in enrich[0].pick


def test_coverage_names_the_governance_nouns_with_their_kinds(registry) -> None:
    terms = {t.text: set(t.kinds) for t in dictionary(registry)}
    expected = {
        "user pool": "cognito-user-pool", "identity provider": "cognito-identity-provider",
        "identity pool": "cognito-identity-pool", "rule group": "firewall-rule-group",
        "firewall policy": "firewall-policy", "configuration recorder": "config-recorder",
        "config rule": "config-rule", "trail": "cloudtrail-trail", "budget": "budget",
        "organizational unit": "organizational-unit", "detector": "guardduty-detector",
        "landing zone": "landing-zone",
    }
    for noun, kind in expected.items():
        assert kind in terms.get(noun, set()), noun


def test_a_trail_is_drawn_once_in_its_home_region(registry) -> None:
    trail = {"TrailARN": TRAIL, "Name": "audit", "HomeRegion": REGION, "S3BucketName": "audit-logs",
             "_Status": {"IsLogging": True}}
    g = graph(registry, {"cloudtrail-trail": [{**trail, "_Region": REGION}, {**trail, "_Region": OTHER}]})
    trails = [n for n in g.nodes if n.kind == "cloudtrail-trail"]
    assert [n.id for n in trails] == [TRAIL] and trails[0].label == "audit"
    assert {c.child: c.parent for c in g.contains}[TRAIL] == REGION


def test_no_organization_draws_no_organization_node(registry) -> None:
    g = graph(registry, {"organization": [{"Handshakes": []}]})
    assert not [n for n in g.nodes if n.kind == "organization"]


def test_ous_and_accounts_are_members_of_their_organization(registry) -> None:
    org = {"Handshakes": [], "_Org": {"Id": "o-ab12", "Arn": "arn:aws:organizations::0:organization/o-ab12",
                                       "FeatureSet": "ALL", "MasterAccountId": ACCOUNT},
           "_Root": {"Id": ROOT}}
    ou_arn = f"arn:aws:organizations::{ACCOUNT}:ou/o-ab12/ou-ab12-x"
    ou = {"Id": "ou-ab12-x", "Arn": ou_arn, "Name": "Workloads", "_Parent": ROOT}
    acct_arn = f"arn:aws:organizations::{ACCOUNT}:account/o-ab12/111122223333"
    acct = {"Id": "111122223333", "Arn": acct_arn, "Name": "dev", "Status": "ACTIVE",
            "_ParentRef": {"Id": "ou-ab12-x", "Type": "ORGANIZATIONAL_UNIT"}}
    g = graph(registry, {"organization": [org], "organizational-unit": [ou], "org-account": [acct]})
    parents = {c.child: c.parent for c in g.contains}
    assert parents[ROOT] == parents[ou_arn] == parents[acct_arn] == "global"
    edges = {(e.kind, e.from_, e.to) for e in g.edges}
    assert ("member-of", ou_arn, ROOT) in edges and ("member-of", acct_arn, ou_arn) in edges


def test_config_ops_run_the_cli_configservice_command(registry) -> None:
    g = graph(registry, {})
    prepared = prepare(op_named("put-config-rule"),
                       {"ConfigRule.ConfigRuleName": "versioning", "ConfigRule.Source.Owner": "AWS",
                        "ConfigRule.Source.SourceIdentifier": "S3_BUCKET_VERSIONING_ENABLED"},
                       graph=g, azs=[], choices={}, tags={})
    assert prepared.problems == []
    assert prepared.argv[1:3] == ["configservice", "put-config-rule"]
