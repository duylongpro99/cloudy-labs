"""The collector over a recording of a real Floci scenario: every wave-1 kind, its props and edges."""

import os
from collections import Counter

from cloudy_labs.graph.schema import ResourceGraph

from graph_fixtures import WAVE_1_GOLDEN, wave_1_graph


def test_the_recorded_scenario_gives_the_golden_graph():
    text = wave_1_graph().to_json(indent=2) + "\n"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        WAVE_1_GOLDEN.write_text(text)
    assert WAVE_1_GOLDEN.exists(), "run with UPDATE_GOLDEN=1 to create the golden graph"
    assert text == WAVE_1_GOLDEN.read_text(), "graph differs from the golden file; rerun with UPDATE_GOLDEN=1 if the change is intended"
    ResourceGraph.model_validate_json(text)


def test_the_recording_draws_every_kind_the_scenario_built():
    g = wave_1_graph()
    kinds = Counter(n.kind for n in g.nodes)
    built = {"network-acl", "vpc-endpoint", "vpc-peering", "flow-log", "transit-gateway", "tgw-attachment",
             "tgw-route-table", "network-interface", "ebs-volume", "launch-template", "prefix-list",
             "db-subnet-group", "db-parameter-group", "db-cluster", "db-instance", "s3-bucket",
             "s3-multipart-upload", "lambda-function", "lambda-version", "lambda-alias", "lambda-layer", "iam-role", "iam-user",
             "iam-group", "iam-policy", "iam-instance-profile"}
    assert built <= set(kinds), sorted(built - set(kinds))
    assert g.warnings == []


def test_internal_and_default_resources_stay_out():
    g = wave_1_graph()
    labels = {n.label for n in g.nodes}
    assert "cloudy-labs-admin" not in labels
    assert not any(label.startswith("awslambda-") for label in labels)
    assert not any(n.kind == "iam-role" and "/aws-service-role/" in str(n.props.get("path")) for n in g.nodes)
    assert not any(n.kind == "network-interface" and n.props.get("requesterManaged") for n in g.nodes)


def test_global_kinds_hang_under_the_global_group_and_rds_under_its_subnet_group():
    g = wave_1_graph()
    parent = {c.child: c.parent for c in g.contains}
    kind = {n.id: n.kind for n in g.nodes}
    assert {kind[parent[n.id]] for n in g.nodes if n.kind.startswith("iam-")} == {"global"}
    assert {kind[parent[n.id]] for n in g.nodes if n.kind == "db-cluster"} <= {"db-subnet-group", "region"}


def test_every_recorded_edge_joins_two_drawn_nodes():
    g = wave_1_graph()
    ids = {n.id for n in g.nodes}
    assert all(e.from_ in ids and e.to in ids for e in g.edges)
    assert {"replica-of", "execution-role", "attached-policy", "nacl-association", "replicates-to", "proxy-target"} <= {e.kind for e in g.edges}
