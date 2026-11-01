"""Labs pick their region; the graph has an account root with one group per region plus a global group."""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from cloudy_labs.graph.collector import collect
from cloudy_labs.graph.schema import ResourceGraph
from cloudy_labs.labs import Lab, LabError
from cloudy_labs.labs.loader import lab_path

from graph_fixtures import LATER, FakeEc2, dns_hostnames, ports, raw
from test_schema import base

SRC = Path(__file__).parents[1] / "src" / "cloudy_labs"


@pytest.mark.parametrize(
    "over, needle",
    [
        ({"region": "mars-north-1"}, "not an AWS region"),
        ({"regions": ["ap-southeast-2", "nowhere-1"]}, "not an AWS region"),
        ({"regions": ["eu-west-1"]}, "must include the lab's region"),
        ({"regions": ["ap-southeast-2", "ap-southeast-2"]}, "twice"),
        ({"target": {"region": "eu-west-1", "nodes": []}}, "not one of the lab's regions"),
    ],
)
def test_bad_regions_are_rejected(over, needle):
    with pytest.raises(ValidationError, match=needle):
        Lab.model_validate(base(**over))


def test_a_lab_defaults_to_sydney_and_lists_its_own_region_first():
    assert Lab.model_validate(base()).all_regions == ["ap-southeast-2"]
    lab = Lab.model_validate(base(region="eu-west-1", regions=["ap-southeast-2", "eu-west-1"]))
    assert lab.all_regions == ["eu-west-1", "ap-southeast-2"] and lab.target_region() == "eu-west-1"


@pytest.mark.parametrize("slug", ["../x", "a/b", "X", "", "-x", "a" * 82])
def test_lab_ids_that_are_not_slugs_are_refused(tmp_path, slug):
    with pytest.raises(LabError):
        lab_path(slug, tmp_path)


def test_a_symlinked_lab_outside_the_labs_directory_is_refused(tmp_path):
    (tmp_path / "labs").mkdir()
    (tmp_path / "labs" / "away").symlink_to(tmp_path)
    with pytest.raises(LabError, match="outside"):
        lab_path("away", tmp_path / "labs")


def test_the_server_names_no_fixed_region():
    hits = [f"{p.relative_to(SRC)}:{n}" for p in SRC.rglob("*.py")
            for n, line in enumerate(p.read_text().splitlines(), 1) if re.search(r"us-east-1", line) and not line.startswith("S3_NULL_LOCATION_REGION =")]
    assert hits == []


class Things:
    def __init__(self, things):
        self.things, self.calls = things, 0

    def can_paginate(self, method):
        return False

    def list_things(self, **_):
        self.calls += 1
        return {"Things": self.things}


class RegionalProvider:
    """One set of clients per region, as the real provider gives with `region=`."""

    def __init__(self, by_region):
        self.by_region = by_region
        self.calls: list[tuple[str, str]] = []

    def client(self, service, credentials=None, *, direct=False, config=None, region=None):
        self.calls.append((service, region))
        return self.by_region[region][service]


def test_two_regions_and_a_global_kind(extra_registry):
    registry = extra_registry("test-global")
    eu_vpc = {**raw()["Vpcs"][0], "VpcId": "vpc-eu1", "IsDefault": False}
    empty = {k: [] for k in raw()}
    sydney_global, eu_global = Things([{"Id": "user-1"}]), Things([{"Id": "user-1"}])
    provider = RegionalProvider({
        "ap-southeast-2": {"ec2": FakeEc2(raw(), dns=dns_hostnames()), "testglobal": sydney_global},
        "eu-west-1": {"ec2": FakeEc2({**empty, "Vpcs": [eu_vpc]}, dns={"vpc-eu1": False}), "testglobal": eu_global},
    })
    g = collect(provider, regions=["ap-southeast-2", "eu-west-1"], clock=lambda: LATER, ports=ports,
                kinds=["vpc", "test-global"], registry=registry)
    ResourceGraph.model_validate_json(g.to_json())
    parent = {c.child: c.parent for c in g.contains}
    assert [n.id for n in g.nodes if n.kind == "account"] == ["000000000000"]
    assert {parent["ap-southeast-2"], parent["eu-west-1"], parent["global"]} == {"000000000000"}
    assert parent["vpc-eu1"] == "eu-west-1"
    assert {v for v, p in parent.items() if p == "ap-southeast-2"} and "vpc-eu1" not in {
        v for v, p in parent.items() if p == "ap-southeast-2"}
    assert parent["user-1"] == "global" and [n.id for n in g.nodes].count("user-1") == 1
    assert (sydney_global.calls, eu_global.calls) == (1, 0)  # a global kind is listed once
