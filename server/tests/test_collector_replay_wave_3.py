"""The collector over a recording of the third Floci scenario: edge, messaging, delivery, data movement
and governance kinds, their props and the edges between them and the older kinds."""

import os

from cloudy_labs.graph.schema import ResourceGraph

from graph_fixtures import WAVE_3_DESCRIBED, WAVE_3_GOLDEN, wave_3_graph

BUILT = {
    # edge
    "cloudfront-distribution", "apigateway-rest-api", "apigateway-http-api", "global-accelerator", "acm-certificate",
    "waf-web-acl", "route53-health-check",
    # messaging
    "sqs-queue", "sns-topic", "sns-subscription", "kinesis-stream", "state-machine",
    # delivery
    "ecr-repository", "ecs-cluster", "eks-cluster", "beanstalk-application", "beanstalk-environment", "codebuild-project",
    "codedeploy-application", "codepipeline-pipeline", "codeartifact-domain", "codeartifact-repository",
    # data movement
    "dms-replication-instance", "dms-endpoint", "dms-replication-task", "datasync-location", "datasync-task",
    "elasticache-cache-cluster", "elasticache-replication-group", "athena-workgroup", "glue-database", "glue-crawler",
    "transfer-server", "rds-event-subscription",
    # governance
    "cloudtrail-trail", "config-recorder", "config-rule", "cognito-user-pool", "cognito-identity-provider",
    "cognito-identity-pool", "budget", "organization", "organizational-unit", "org-account", "guardduty-detector",
    "inspector", "securityhub-hub", "network-firewall", "firewall-policy", "firewall-rule-group", "landing-zone",
}


def test_the_recorded_scenario_gives_the_golden_graph():
    text = wave_3_graph().to_json(indent=2) + "\n"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        WAVE_3_GOLDEN.write_text(text)
    assert WAVE_3_GOLDEN.exists(), "run with UPDATE_GOLDEN=1 to create the golden graph"
    assert text == WAVE_3_GOLDEN.read_text(), "graph differs from the golden file; rerun with UPDATE_GOLDEN=1 if the change is intended"
    ResourceGraph.model_validate_json(text)


def test_the_recording_draws_every_kind_the_scenario_built():
    g = wave_3_graph()
    kinds = {n.kind for n in g.nodes}
    assert BUILT <= kinds, sorted(BUILT - kinds)
    assert g.warnings == []


def test_every_recorded_edge_joins_two_drawn_nodes_and_the_services_link_up():
    g = wave_3_graph()
    ids = {n.id for n in g.nodes}
    assert all(e.from_ in ids and e.to in ids for e in g.edges)
    assert {
        "origin", "uses-certificate", "web-acl-for", "uses-health-check",  # edge
        "dead-letter", "event-source", "targets", "invokes",  # messaging
        "pipeline-source", "pipeline-action", "upload-to", "upstream", "runs-on",  # delivery
        "endpoint-database", "copies-from", "copies-to", "crawls", "crawls-into", "uses-bucket", "notifies",  # data
        "delivers-to", "federates", "pool-role", "member-of", "uses-firewall-policy", "uses-rule-group",  # governance
    } <= {e.kind for e in g.edges}


def test_uris_and_topics_link_to_their_bucket_and_topic():
    g = wave_3_graph()
    by_id = {n.id: n for n in g.nodes}
    linked = {(by_id[e.from_].kind, e.kind, by_id[e.to].kind) for e in g.edges}
    assert {("datasync-location", "uses-bucket", "s3-bucket"), ("athena-workgroup", "delivers-to", "s3-bucket"),
            ("glue-crawler", "crawls", "s3-bucket"), ("rds-event-subscription", "notifies", "sns-topic")} <= linked


def test_no_build_variable_value_is_recorded_or_drawn():
    recorded = "".join(p.read_text() for p in WAVE_3_DESCRIBED.rglob("*.json"))
    drawn = wave_3_graph().to_json()
    assert "w3-dummy-env" not in recorded and "w3-dummy-env" not in drawn
