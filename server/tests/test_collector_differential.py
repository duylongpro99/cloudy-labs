"""The registry-driven collector against graphs the hand-written EC2 collector produced.

Each variant bends the recorded lab 06/07 responses one way (names gone, a route target gone, a
terminated instance, a real public IP, ...); its snapshot in fixtures/graph/variants/ was written
by the hand-written collector, so a diff means the registry changed behaviour.
"""

import copy
import json
import random
from datetime import timedelta

import pytest

from graph_fixtures import FIXTURES, INSTANCE, LAB_KINDS, LAUNCHED, LATER, FakeEc2, FakeProvider, dns_hostnames, ports, raw, user_data
from cloudy_labs.graph.collector import collect

VARIANT_DIR = FIXTURES / "variants"


def _instances(data):
    return [i for r in data["Reservations"] for i in r.get("Instances") or []]


def no_names(data):
    for items in data.values():
        for item in items:
            item["Tags"] = [t for t in item.get("Tags") or [] if t.get("Key") != "Name"]
            for i in item.get("Instances") or []:
                i["Tags"] = [t for t in i.get("Tags") or [] if t.get("Key") != "Name"]
    return data


def igw_gone(data):
    data["InternetGateways"] = []
    return data


def terminated(data):
    for i in _instances(data):
        i["State"] = {"Code": 48, "Name": "terminated"}
    return data


def real_public_ip(data):
    for i in _instances(data):
        i["PublicIpAddress"] = "54.1.2.3"
    return data


def nat_deleted(data):
    for n in data["NatGateways"]:
        n["State"] = "deleted"
    return data


def eip_on_instance(data):
    for a in data["Addresses"]:
        a.update(InstanceId=INSTANCE, AssociationId="eipassoc-1", NetworkInterfaceId="eni-3f2d7713457684f90")
    return data


# name -> (change to the responses, collect time, dns answers, user-data answers)
VARIANTS = {
    "base": (lambda d: d, LATER, dns_hostnames, user_data),
    "fresh-launch": (lambda d: d, LAUNCHED + timedelta(minutes=1), dns_hostnames, user_data),
    "no-names": (no_names, LATER, dns_hostnames, user_data),
    "igw-gone": (igw_gone, LATER, dns_hostnames, user_data),
    "terminated": (terminated, LAUNCHED + timedelta(minutes=1), dns_hostnames, user_data),
    "real-public-ip": (real_public_ip, LATER, dns_hostnames, user_data),
    "nat-deleted": (nat_deleted, LATER, dns_hostnames, user_data),
    "eip-on-instance": (eip_on_instance, LATER, dns_hostnames, user_data),
    "no-dns-answer": (lambda d: d, LATER, dict, user_data),
}


def variant_provider(name, shuffle=None):
    change, now, dns, ud = VARIANTS[name]
    data = change(copy.deepcopy(raw()))
    if shuffle is not None:
        rng = random.Random(shuffle)
        for items in data.values():
            rng.shuffle(items)
    return FakeProvider(FakeEc2(data, dns=dns(), user_data=ud())), now


def variant_graph(name, collector=collect, shuffle=None):
    provider, now = variant_provider(name, shuffle)
    return collector(provider, clock=lambda: now, ports=ports, kinds=LAB_KINDS)


# Props the registry added for reachability after the hand-written collector was retired: they
# are compared by the golden graph, not by these frozen outputs.
LATER_PROPS = {"route-table": {"routes", "associations"}, "security-group": {"egress"}, "instance": {"hasPublicIp"}}


def _without_later_props(graph: dict) -> dict:
    for node in graph["nodes"]:
        for prop in LATER_PROPS.get(node["kind"], ()):
            node["props"].pop(prop, None)
    return graph


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_variant_matches_the_hand_written_collector(name):
    expected = json.loads((VARIANT_DIR / f"{name}.graph.json").read_text())
    assert _without_later_props(variant_graph(name).to_dict()) == expected


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_response_order_does_not_matter(seed):
    assert variant_graph("base", shuffle=seed).to_json() == variant_graph("base").to_json()


def test_the_terminated_variant_skips_the_user_data_call():
    provider, now = variant_provider("terminated")
    collect(provider, clock=lambda: now, ports=ports, kinds=LAB_KINDS)
    assert INSTANCE not in provider.clients["ec2"].attribute_calls
