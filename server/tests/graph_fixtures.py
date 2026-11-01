"""Floci describe responses recorded for lab 06/07, served by fake boto3 clients."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from botocore.exceptions import ClientError

from cloudy_labs.graph.collector import collect
from cloudy_labs.graph.host_ports import parse_ps

FIXTURES = Path(__file__).parent / "fixtures" / "graph"
DESCRIBED = FIXTURES / "floci-describe"
GOLDEN = FIXTURES / "lab-06-07.graph.json"
INSTANCE = "i-fdb553d289095d128"
LAUNCHED = datetime(2026, 10, 29, 7, 33, 59, 99000, tzinfo=timezone.utc)
LATER = LAUNCHED + timedelta(hours=1)

# EC2 describe call -> response key, as recorded in floci-describe/.
DESCRIBE = {
    "describe_vpcs": "Vpcs",
    "describe_subnets": "Subnets",
    "describe_internet_gateways": "InternetGateways",
    "describe_nat_gateways": "NatGateways",
    "describe_route_tables": "RouteTables",
    "describe_security_groups": "SecurityGroups",
    "describe_key_pairs": "KeyPairs",
    "describe_instances": "Reservations",
    "describe_addresses": "Addresses",
}


def raw() -> dict:
    return {
        key: json.loads((DESCRIBED / f"{method.replace('_', '-')}.json").read_text())[key]
        for method, key in DESCRIBE.items()
    }


def ports() -> dict:
    return parse_ps((DESCRIBED / "docker-ps.txt").read_text())


def user_data() -> dict:
    return json.loads((DESCRIBED / "user-data.json").read_text())


def dns_hostnames() -> dict:
    return json.loads((DESCRIBED / "vpc-dns-hostnames.json").read_text())


def _not_found(op: str) -> ClientError:
    return ClientError({"Error": {"Code": "NotFound", "Message": "gone"}}, op)


class FakeEc2:
    """Answers the describe calls from `data`; attributes from `dns` and `user_data` (absent: NotFound)."""

    def __init__(self, data, fail=None, dns=None, user_data=None):
        self.data, self.fail = data, fail
        self.dns = dns if dns is not None else {}
        self.user_data = user_data if user_data is not None else {}
        self.attribute_calls: list[str] = []
        self.list_calls: list[str] = []

    def can_paginate(self, method):
        return False

    def __getattr__(self, method):
        if method not in DESCRIBE:
            if method.startswith(("describe_", "get_")):
                # A kind the Lab 6/7 recording predates (NACLs, peerings...): the account has none.
                def empty(**params):
                    self.list_calls.append(method)
                    if self.fail:
                        raise self.fail
                    return {}
                return empty
            raise AttributeError(method)

        def call(**params):
            self.list_calls.append(method)
            if self.fail:
                raise self.fail
            return {DESCRIBE[method]: self.data[DESCRIBE[method]]}
        return call

    def describe_vpc_attribute(self, VpcId, Attribute):
        assert Attribute == "enableDnsHostnames"
        if VpcId not in self.dns:
            raise _not_found("DescribeVpcAttribute")
        return {"VpcId": VpcId, "EnableDnsHostnames": {"Value": self.dns[VpcId]}}

    def describe_instance_attribute(self, InstanceId, Attribute):
        self.attribute_calls.append(InstanceId)
        has = self.user_data.get(InstanceId)
        return {"UserData": {"Value": "IyEvYmluL2Jhc2g="} if has else {}}


class FakeProvider:
    def __init__(self, clients):
        self.clients = clients if isinstance(clients, dict) else {"ec2": clients}
        self.calls = []

    def client(self, service, credentials=None, *, direct=False, config=None):
        self.calls.append((service, direct))
        if service not in self.clients:
            raise AssertionError(f"no fake client for {service}")
        return self.clients[service]


LAB_KINDS = ("vpc", "az", "subnet-public", "subnet-private", "igw", "nat", "route-table", "security-group", "key-pair",
             "instance", "elastic-ip")  # what Lab 6/7 uses; the recording holds nothing else


def lab_graph(now=LATER, data=None, *, host_ports=None, user_data_=None, dns=None, registry=None, kinds=LAB_KINDS):
    """The graph the collector makes from the fixtures (or `data`), with the given enrich answers."""
    ec2 = FakeEc2(data or raw(), dns=dns_hostnames() if dns is None else dns,
                  user_data=user_data() if user_data_ is None else user_data_)
    hp = ports() if host_ports is None else host_ports
    return collect(FakeProvider(ec2), clock=lambda: now, ports=lambda: hp, kinds=kinds, registry=registry)


WAVE_1_GOLDEN = FIXTURES / "wave-1.graph.json"
WAVE_1_CLOCK = datetime(2026, 11, 1, tzinfo=timezone.utc)  # long after the recording: no UserData probes


def _same(a, b):
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


class Replay:
    """A boto3 client that answers from `<root>/<service>/<method>.json` (default root:
    floci-describe), written by scripts/record-floci-fixtures.py. A call matches the first unused
    recorded call with the same params; a recorded error is raised as a ClientError; anything
    unrecorded fails the test."""

    def __init__(self, service, root=DESCRIBED):
        self.service = service
        folder = root / service if (root / service).is_dir() else root / "other" / service
        self.calls = {p.stem: json.loads(p.read_text())["calls"] for p in folder.glob("*.json")}
        self.used = {method: [False] * len(calls) for method, calls in self.calls.items()}

    def can_paginate(self, method):
        return False

    def __getattr__(self, method):
        if method.startswith("_") or method not in self.calls:
            raise AttributeError(f"{self.service}.{method} was not recorded")

        def call(**params):
            for i, recorded in enumerate(self.calls[method]):
                if not self.used[method][i] and _same(recorded["params"], params):
                    self.used[method][i] = True
                    if "error" in recorded:
                        raise ClientError({"Error": {"Code": recorded["error"], "Message": ""}}, method)
                    return json.loads(json.dumps(recorded["response"]))
            raise AssertionError(f"{self.service}.{method}({params}) was not recorded")

        return call


class FixtureClients(FakeProvider):
    """Every service the recording under `root` holds, replayed."""

    def __init__(self, root=DESCRIBED):
        services = [p.name for p in root.iterdir() if p.is_dir() and p.name != "other"]
        services += [p.name for p in (root / "other").iterdir() if p.is_dir()] if (root / "other").is_dir() else []
        super().__init__({s: Replay(s, root) for s in services})


def recorded_kinds(root=DESCRIBED):
    """The kinds the recording under `root` listed (`kinds.json`, written by the recorder). Kinds
    added to the registry later are left out: the recording holds no answers for them."""
    return json.loads((root / "kinds.json").read_text())


def _replay_graph(root):
    from cloudy_labs.registry import default_registry

    return collect(FixtureClients(root), clock=lambda: WAVE_1_CLOCK, ports=lambda: {},
                   kinds=recorded_kinds(root), registry=default_registry())


def wave_1_graph(kinds=None):
    """The graph the collector makes from the wave-1 recording on Floci."""
    from cloudy_labs.registry import default_registry

    return collect(FixtureClients(), clock=lambda: WAVE_1_CLOCK, ports=lambda: {},
                   kinds=recorded_kinds() if kinds is None else kinds, registry=default_registry())


WAVE_2_DESCRIBED = FIXTURES / "floci-describe-wave-2"
WAVE_2_GOLDEN = FIXTURES / "wave-2.graph.json"
WAVE_3_DESCRIBED = FIXTURES / "floci-describe-wave-3"
WAVE_3_GOLDEN = FIXTURES / "wave-3.graph.json"


def wave_2_graph():
    """The graph the collector makes from the wave-2 recording on Floci."""
    return _replay_graph(WAVE_2_DESCRIBED)


def wave_3_graph():
    """The graph the collector makes from the wave-3 recording on Floci."""
    return _replay_graph(WAVE_3_DESCRIBED)
