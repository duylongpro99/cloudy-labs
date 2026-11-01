"""The edge and front-door kinds (CloudFront, API Gateway REST and HTTP APIs, Global Accelerator, ACM,
WAF, Route 53 health checks): drawn with a real icon in their own view-order band, built only from
APIs Floci has, each create op proved by a contract, links to their origins and integrations found
the way AWS spells them, and no certificate body, key or lock token ever read into a prop."""
import json
from pathlib import Path

import jmespath
import pytest

from cloudy_labs.registry import CHAT_PROPS_DENY, REGISTRY_DIR, default_registry

KINDS = [
    "cloudfront-distribution", "apigateway-rest-api", "apigateway-http-api", "global-accelerator",
    "acm-certificate", "waf-web-acl", "route53-health-check",
]
GLOBAL = {"cloudfront-distribution", "global-accelerator", "route53-health-check"}
ICONS = Path(__file__).resolve().parents[2] / "aws-icon-pkg"
FLOCI = json.loads((REGISTRY_DIR / "floci-ops-2.3.0.json").read_text())["services"]
REGION = "ap-southeast-2"
FUNCTION = f"arn:aws:lambda:{REGION}:000000000000:function:orders"


@pytest.fixture(scope="module")
def registry():
    return default_registry()


def _edge(registry, kind: str, edge_kind: str, to: str):
    return next(e for e in registry.by_kind[kind].edges if e.kind == edge_kind and to in e.to)


@pytest.mark.parametrize("kind", KINDS)
def test_each_kind_is_drawn_with_a_real_icon_in_its_band(registry, kind: str) -> None:
    view = registry.by_kind[kind].view
    assert 500 <= view.order <= 549
    assert view.source and (ICONS / view.source).is_file(), view.source
    assert view.source.endswith("/" + view.icon)


def test_view_orders_of_the_band_are_unique(registry) -> None:
    orders = [t.view.order for t in registry.types if t.kind in KINDS]
    assert len(orders) == len(set(orders))
    others = {t.view.order for t in registry.types if t.kind not in KINDS}
    assert not others & set(orders)


@pytest.mark.parametrize("kind", KINDS)
def test_global_services_sit_under_the_global_group(registry, kind: str) -> None:
    t = registry.by_kind[kind]
    if kind in GLOBAL:
        assert t.scope == "global" and [p.kind for p in t.parent] == ["global"]
    else:
        assert t.scope == "regional" and [p.kind for p in t.parent] == ["region"]


@pytest.mark.parametrize("kind", KINDS)
def test_every_op_uses_an_api_floci_has(registry, kind: str) -> None:
    t = registry.by_kind[kind]
    for op in t.ops:
        service = op.service or t.service
        assert op.api in FLOCI[service]["supported"], f"{op.id}: {service} {op.api}"


@pytest.mark.parametrize("kind", KINDS)
def test_each_kind_can_be_created_and_deleted_and_its_contract_creates_it(registry, kind: str) -> None:
    t = registry.by_kind[kind]
    assert {"create", "delete"} <= {op.gesture for op in t.ops}
    own = {op.id: op for op in t.ops}
    assert t.contract and own[t.contract.create.op].gesture == "create"
    for step in [*t.contract.needs, t.contract.create, *t.contract.then]:
        for name, value in step.params.items():
            assert isinstance(value, str), f"{step.op}.{name} must be a string"


@pytest.mark.parametrize("kind", KINDS)
def test_no_prop_reads_a_certificate_body_key_or_lock_token(registry, kind: str) -> None:
    t = registry.by_kind[kind]
    assert not {e.method for e in t.enrich} & {"get_certificate", "export_certificate"}
    for name, spec in t.props.items():
        assert not any(w in name.lower() for w in CHAT_PROPS_DENY), f"{kind}.{name}"
        if isinstance(spec, str):
            assert not any(f in spec for f in ("PrivateKey", "CertificateChain", "LockToken", "Passphrase")), f"{kind}.{name}"
    assert set(t.chat_props) <= set(t.props)


def test_a_rest_api_invokes_the_function_its_lambda_integration_wraps(registry) -> None:
    rule = _edge(registry, "apigateway-rest-api", "invokes", "lambda-function")
    uri = f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{FUNCTION}/invocations"
    api = {"_Resources": [{"path": "/"}, {"path": "/orders", "resourceMethods": {
        "GET": {"httpMethod": "GET", "methodIntegration": {"type": "AWS_PROXY", "uri": uri}},
        "OPTIONS": {"httpMethod": "OPTIONS", "methodIntegration": {"type": "MOCK"}}}}]}
    assert jmespath.search(rule.target, api) == [uri]
    assert jmespath.search(rule.match, {"FunctionArn": FUNCTION, "_Region": REGION}) == uri


def test_a_distribution_finds_its_bucket_origin_in_any_s3_spelling(registry) -> None:
    rule = _edge(registry, "cloudfront-distribution", "origin", "s3-bucket")
    names = jmespath.search(rule.match, {"Name": "site", "_Region": REGION})
    for domain in ("site.s3.amazonaws.com", f"site.s3.{REGION}.amazonaws.com",
                   f"site.s3-website-{REGION}.amazonaws.com", f"site.s3-website.{REGION}.amazonaws.com"):
        assert domain in names
    item = {"_Config": {"DistributionConfig": {"Origins": {"Items": [{"DomainName": f"site.s3.{REGION}.amazonaws.com"}]}}}}
    assert jmespath.search(rule.target, item) == [f"site.s3.{REGION}.amazonaws.com"]


def test_a_distribution_finds_its_load_balancer_origin_by_dns_name(registry) -> None:
    rule = _edge(registry, "cloudfront-distribution", "origin", "load-balancer")
    assert "dualstack.web-1.elb.amazonaws.com" in jmespath.search(rule.match, {"DNSName": "web-1.elb.amazonaws.com"})


def test_a_failover_record_points_at_its_health_check(registry) -> None:
    rule = _edge(registry, "route53-health-check", "uses-health-check", "record-set")
    assert rule.reverse and rule.match == "HealthCheckId"


def test_an_https_listener_points_at_its_certificate(registry) -> None:
    rule = _edge(registry, "acm-certificate", "uses-certificate", "listener")
    arn = f"arn:aws:acm:{REGION}:000000000000:certificate/abc"
    assert rule.reverse and arn in jmespath.search(rule.match, {"Certificates": [{"CertificateArn": arn}]})


def test_web_acl_props_survive_rules_without_an_action(registry) -> None:
    rules = registry.by_kind["waf-web-acl"].props["rules"]
    acl = {"_Acl": {"Rules": [
        {"Name": "managed", "Priority": 1, "OverrideAction": {"None": {}}, "Statement": {"ManagedRuleGroupStatement": {}}},
        {"Name": "ip", "Priority": 0, "Action": {"Block": {}}, "Statement": {"IPSetReferenceStatement": {}}}]}}
    assert jmespath.search(rules, acl) == [
        {"name": "ip", "priority": 0, "action": "Block", "statement": "IPSetReferenceStatement"},
        {"name": "managed", "priority": 1, "action": "None", "statement": "ManagedRuleGroupStatement"}]
