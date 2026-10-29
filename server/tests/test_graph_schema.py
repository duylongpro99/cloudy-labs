import json

import pytest
from pydantic import ValidationError

from cloudy_labs.graph.schema import ResourceGraph


def graph(nodes, contains=(), edges=()):
    return {
        "takenAt": "2026-10-29T00:00:00Z",
        "nodes": [{"id": i, "kind": k, "label": i} for i, k in nodes],
        "contains": [{"parent": p, "child": c} for p, c in contains],
        "edges": [{"id": f"{k}:{a}->{b}", "kind": k, "from": a, "to": b} for k, a, b in edges],
    }


BASE = [("us-east-1", "region"), ("vpc-1", "vpc"), ("igw-1", "igw")]
TREE = [("us-east-1", "vpc-1"), ("vpc-1", "igw-1")]


def test_valid_graph_round_trips_with_camel_case():
    g = ResourceGraph.model_validate(graph(BASE, TREE, [("attached", "igw-1", "vpc-1")]))
    data = json.loads(g.to_json())
    assert data["takenAt"] == "2026-10-29T00:00:00Z" and data["status"] == "ok"
    assert data["edges"][0]["from"] == "igw-1"
    assert ResourceGraph.model_validate(data) == g


def test_json_is_deterministic():
    g = ResourceGraph.model_validate(graph(BASE, TREE))
    assert g.to_json(indent=2) == ResourceGraph.model_validate(json.loads(g.to_json())).to_json(indent=2)


def test_content_hash_ignores_version_and_time():
    a = ResourceGraph.model_validate(graph(BASE, TREE))
    b = a.model_copy(update={"version": 7, "taken_at": "2027-01-01T00:00:00Z"})
    assert a.content_hash() == b.content_hash()
    c = ResourceGraph.model_validate(graph(BASE[:2], TREE[:1]))
    assert a.content_hash() != c.content_hash()


@pytest.mark.parametrize(
    "nodes, contains, edges, message",
    [
        (BASE, TREE[:1], (), "exactly one root"),  # igw-1 is an orphan
        (BASE, TREE + [("us-east-1", "igw-1")], (), "two parents"),
        (BASE, TREE, [("route", "vpc-1", "nat-9")], "unknown node nat-9"),
        (BASE, TREE + [("vpc-1", "subnet-9")], (), "unknown node subnet-9"),
        (BASE + [("vpc-1", "vpc")], TREE, (), "duplicate"),
        ([("vpc-1", "vpc")], (), (), "must be a region"),
    ],
)
def test_validator_rejects_malformed_graphs(nodes, contains, edges, message):
    with pytest.raises(ValidationError, match=message):
        ResourceGraph.model_validate(graph(nodes, contains, edges))


def test_unknown_kind_is_rejected():
    with pytest.raises(ValidationError):
        ResourceGraph.model_validate(graph([("us-east-1", "region"), ("x", "lambda")], [("us-east-1", "x")]))
