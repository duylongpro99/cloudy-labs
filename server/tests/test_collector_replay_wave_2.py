"""The collector over a recording of the second Floci scenario: monitoring, events, data, config and
network kinds, their props and the edges between them."""

import os
from collections import Counter

from cloudy_labs.graph.schema import ResourceGraph

from graph_fixtures import WAVE_2_DESCRIBED, WAVE_2_GOLDEN, wave_2_graph

BUILT = {
    "cloudwatch-alarm", "cloudwatch-dashboard", "log-group", "metric-filter", "event-bus", "event-rule", "schedule",
    "backup-vault", "backup-plan", "backup-selection", "kms-key", "kms-alias", "dynamodb-table", "ssm-parameter",
    "secretsmanager-secret", "cloudformation-stack", "efs-file-system", "efs-mount-target", "efs-access-point",
    "load-balancer", "target-group", "listener", "listener-rule", "autoscaling-group", "scaling-policy",
    "hosted-zone", "record-set",
}


def test_the_recorded_scenario_gives_the_golden_graph():
    text = wave_2_graph().to_json(indent=2) + "\n"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        WAVE_2_GOLDEN.write_text(text)
    assert WAVE_2_GOLDEN.exists(), "run with UPDATE_GOLDEN=1 to create the golden graph"
    assert text == WAVE_2_GOLDEN.read_text(), "graph differs from the golden file; rerun with UPDATE_GOLDEN=1 if the change is intended"
    ResourceGraph.model_validate_json(text)


def test_the_recording_draws_every_kind_the_scenario_built():
    g = wave_2_graph()
    kinds = set(Counter(n.kind for n in g.nodes))
    assert BUILT <= kinds, sorted(BUILT - kinds)
    assert g.warnings == []


def test_every_recorded_edge_joins_two_drawn_nodes_and_the_services_link_up():
    g = wave_2_graph()
    ids = {n.id for n in g.nodes}
    assert all(e.from_ in ids and e.to in ids for e in g.edges)
    assert {"watches", "filter-of", "targets", "backs-up-to", "selects", "encrypted-by", "managed-by", "mount-of",
            "forwards-to", "listener-of", "uses-launch-template", "record-of", "zone-vpc"} <= {e.kind for e in g.edges}


def test_no_parameter_or_secret_value_is_recorded_or_drawn():
    recorded = "".join(p.read_text() for p in WAVE_2_DESCRIBED.rglob("*.json"))
    drawn = wave_2_graph().to_json()
    for value in ("w2-dummy", "w2-dummy-token", "db.internal", "from-cfn"):
        assert value not in recorded and value not in drawn, value

