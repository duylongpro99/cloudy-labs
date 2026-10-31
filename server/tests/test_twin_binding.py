"""bind_target and twin_state on the golden lab-06/07 graph with hand-made check results."""

import json
import os
from pathlib import Path

import pytest

from cloudy_labs.checks import CheckResult
from cloudy_labs.graph.schema import ResourceGraph
from cloudy_labs.labs import load_lab
from cloudy_labs.labs.schema import Target
from cloudy_labs.progress import Attempt
from cloudy_labs.twin import bind_target, ghost_id, twin_state

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = ResourceGraph.model_validate_json((FIXTURES / "graph" / "lab-06-07.graph.json").read_text())
GOLDEN_TWIN = FIXTURES / "graph" / "lab-06-07.twin.json"  # read by the web tests too
VPC = "vpc-149d0439"
PUBLIC_A, PUBLIC_B, PRIVATE_A, PRIVATE_B = "subnet-83a1f79a", "subnet-b893d7ba", "subnet-e917cc42", "subnet-44acdeb7"
NAT, EIP, IGW = "nat-235f142ec41b5d904", "eipalloc-2cc57421a05781343", "igw-34ddd4cd"
RT_PUBLIC, RT_PRIVATE = "rtb-509e5b33", "rtb-02888668"
# What the lab-06 checkers report on that graph once everything is done (subnets listed B first,
# as a checker is free to order them).
DONE = {
    "vpc-exists": [VPC],
    "vpc-dns-hostnames": [VPC],
    "subnets-two-azs": [PUBLIC_B, PUBLIC_A, PRIVATE_B, PRIVATE_A],
    "public-ip-on-launch": [PUBLIC_B, PUBLIC_A],
    "igw-attached": [IGW],
    "nat-in-public-subnet": [NAT, PUBLIC_A, EIP],
    "public-route-table": [RT_PUBLIC, PUBLIC_A, PUBLIC_B],
    "private-route-table": [RT_PRIVATE, PRIVATE_A, PRIVATE_B],
}


@pytest.fixture(scope="module")
def target() -> Target:
    return load_lab("fixture-lab-06", FIXTURES / "labs").lab.target


def results(passed: dict[str, list[str]], failed: tuple[str, ...] = ()) -> list[CheckResult]:
    return [CheckResult(True, "ok", ids, cid) for cid, ids in passed.items()] + [CheckResult(False, "no", [], c) for c in failed]


def test_nothing_passed_everything_is_a_ghost_under_its_ghost_parent(target):
    b = bind_target(target, results({}, tuple(DONE)), GOLDEN)
    assert b.bound == {}
    parents = {g.id: g.parent for g in b.ghosts}
    assert [g.id for g in b.ghosts] == [ghost_id(n.id) for n in target.nodes]
    assert parents[ghost_id("vpc")] == "us-east-1" and parents[ghost_id("eip")] == "us-east-1"
    assert parents[ghost_id("public-1")] == ghost_id("az-1") and parents[ghost_id("az-1")] == ghost_id("vpc")
    assert next(g for g in b.ghosts if g.id == ghost_id("nat")).checks == ["nat-in-public-subnet"]


def test_everything_passed_binds_every_node(target):
    b = bind_target(target, results(DONE), GOLDEN)
    assert b.ghosts == []
    assert b.bound == {
        "vpc": VPC, "igw": IGW, "nat": NAT, "eip": EIP, "rt-public": RT_PUBLIC, "rt-private": RT_PRIVATE,
        "public-1": PUBLIC_A, "public-2": PUBLIC_B, "private-1": PRIVATE_A, "private-2": PRIVATE_B,
        "az-1": f"{VPC}/us-east-1a", "az-2": f"{VPC}/us-east-1b",
    }


def test_same_inputs_same_binding(target):
    shuffled = results(dict(reversed(list(DONE.items()))))
    assert bind_target(target, shuffled, GOLDEN) == bind_target(target, results(DONE), GOLDEN)


def test_ghost_under_a_bound_parent_hangs_from_the_real_id(target):
    b = bind_target(target, results({"vpc-exists": [VPC], "vpc-dns-hostnames": [VPC]}), GOLDEN)
    assert b.bound == {"vpc": VPC}
    parents = {g.id: g.parent for g in b.ghosts}
    assert parents[ghost_id("igw")] == VPC and parents[ghost_id("az-1")] == VPC
    assert parents[ghost_id("public-1")] == ghost_id("az-1")


def test_a_node_needs_every_check_it_lists(target):
    b = bind_target(target, results({"vpc-exists": [VPC]}, ("vpc-dns-hostnames",)), GOLDEN)
    assert "vpc" not in b.bound


def test_passed_check_with_ids_the_graph_lacks_keeps_the_ghost(target):
    b = bind_target(target, results({"vpc-exists": ["vpc-gone"], "vpc-dns-hostnames": ["vpc-gone"]}), GOLDEN)
    assert b.bound == {} and ghost_id("vpc") in {g.id for g in b.ghosts}


def test_two_ghosts_of_one_kind_and_check_take_two_ids(target):
    only = {k: DONE[k] for k in ("vpc-exists", "vpc-dns-hostnames", "subnets-two-azs")}
    b = bind_target(target, results(only), GOLDEN)
    assert (b.bound["private-1"], b.bound["private-2"]) == (PRIVATE_A, PRIVATE_B)


def test_child_must_sit_in_its_bound_parent():
    t = Target.model_validate({"nodes": [
        {"id": "vpc", "kind": "vpc", "label": "v", "checks": ["vpc"]},
        {"id": "rt", "kind": "route-table", "parent": "vpc", "label": "r", "checks": ["rt"]},
    ]})
    b = bind_target(t, results({"vpc": [VPC], "rt": ["rtb-default"]}), GOLDEN)  # rtb-default is in the default VPC
    assert b.bound == {"vpc": VPC}
    assert [(g.id, g.parent) for g in b.ghosts] == [(ghost_id("rt"), VPC)]


def test_az_whose_children_landed_in_two_real_azs_stays_a_ghost():
    t = Target.model_validate({"nodes": [
        {"id": "vpc", "kind": "vpc", "label": "v", "checks": ["vpc"]},
        {"id": "az", "kind": "az", "parent": "vpc", "label": "a"},
        {"id": "public", "kind": "subnet-public", "parent": "az", "label": "p", "checks": ["pub"]},
        {"id": "private", "kind": "subnet-private", "parent": "az", "label": "q", "checks": ["priv"]},
    ]})
    b = bind_target(t, results({"vpc": [VPC], "pub": [PUBLIC_A], "priv": [PRIVATE_B]}), GOLDEN)
    assert (b.bound["public"], b.bound["private"]) == (PUBLIC_A, PRIVATE_B)
    assert "az" not in b.bound
    assert [(g.id, g.parent) for g in b.ghosts] == [(ghost_id("az"), VPC)]


def test_subnet_under_an_az_must_still_be_in_the_bound_vpc():
    t = Target.model_validate({"nodes": [
        {"id": "vpc", "kind": "vpc", "label": "v", "checks": ["vpc"]},
        {"id": "az", "kind": "az", "parent": "vpc", "label": "a"},
        {"id": "public", "kind": "subnet-public", "parent": "az", "label": "p", "checks": ["pub"]},
    ]})
    b = bind_target(t, results({"vpc": [VPC], "pub": ["subnet-default-us-east-1-a", PUBLIC_B]}), GOLDEN)
    assert b.bound == {"vpc": VPC, "public": PUBLIC_B, "az": f"{VPC}/us-east-1b"}


def test_emulator_down_graph_binds_nothing(target):
    down = ResourceGraph.model_validate({"takenAt": "2026-10-31T00:00:00Z", "status": "emulator-down",
                                         "nodes": [{"id": "us-east-1", "kind": "region", "label": "us-east-1"}],
                                         "contains": [], "edges": []})
    b = bind_target(target, results(DONE), down)
    assert b.bound == {} and len(b.ghosts) == len(target.nodes)


def test_twin_state_lists_every_check_and_matches_the_golden_file():
    """Half of lab-06 done: the VPC, its subnets and the IGW; no NAT or route tables yet."""
    loaded = load_lab("fixture-lab-06", FIXTURES / "labs")
    half = ("vpc-exists", "vpc-dns-hostnames", "subnets-two-azs", "igw-attached")
    state = twin_state(loaded, Attempt(3, "fixture-lab-06", ""), results(
        {c: DONE[c] for c in half}, tuple(c for c in DONE if c not in half)), GOLDEN)
    assert [c.id for c in state.checks] == [c.id for c in loaded.lab.checks]
    assert {c.id: c.status for c in state.checks}["igw-attached"] == "passed"
    assert {c.id: c.status for c in state.checks}["nat-in-public-subnet"] == "failed"
    assert state.bound["vpc"] == VPC and "nat" not in state.bound
    text = json.dumps(state.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN_TWIN.write_text(text)
    assert GOLDEN_TWIN.exists(), "run with UPDATE_GOLDEN=1 to create the golden twin"
    assert text == GOLDEN_TWIN.read_text(), "twin differs from the golden file; rerun with UPDATE_GOLDEN=1 if the change is intended"


def test_twin_state_while_the_checks_could_not_run():
    loaded = load_lab("fixture-lab-06", FIXTURES / "labs")
    state = twin_state(loaded, Attempt(3, "fixture-lab-06", ""), None, GOLDEN, note="emulator down")
    assert {c.status for c in state.checks} == {"pending"} and {c.message for c in state.checks} == {"emulator down"}
    assert state.bound == {} and len(state.ghosts) == len(loaded.lab.target.nodes)
    assert state.to_dict()["checks"][0].keys() == {"id", "task", "description", "status", "message", "resourceIds"}
