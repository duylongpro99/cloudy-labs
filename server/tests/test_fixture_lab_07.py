"""fixture-lab-07's setup and checks against canned describe responses, without Docker."""

from unittest.mock import MagicMock

import pytest

from cloudy_labs.checks import CheckContext, run_checks
from cloudy_labs.labs import load_lab

VPC = {"VpcId": "vpc-1", "CidrBlock": "10.67.0.0/16"}
PUBLIC_TABLE = {
    "RouteTableId": "rtb-1",
    "Routes": [{"DestinationCidrBlock": "10.67.0.0/16", "GatewayId": "local"},
               {"DestinationCidrBlock": "0.0.0.0/0", "GatewayId": "igw-1"}],
    "Associations": [{"SubnetId": "subnet-pub"}],
}
DEFAULT_SG = {"GroupId": "sg-default", "GroupName": "default", "IpPermissions": []}


def rule(protocol: str, port: int | None, cidr: str) -> dict:
    r = {"IpProtocol": protocol, "IpRanges": [{"CidrIp": cidr}]}
    return r | ({"FromPort": port, "ToPort": port} if port is not None else {})


WEB_SG = {"GroupId": "sg-web", "GroupName": "web",
          "IpPermissions": [rule("tcp", 80, "0.0.0.0/0"), rule("tcp", 22, "203.0.113.10/32")]}
ADMIN_SG = {"GroupId": "sg-admin", "GroupName": "admin", "IpPermissions": []}


def instance(groups=("sg-web",), state="running", subnet="subnet-pub", key="lab07-key", public_ip="127.0.0.1") -> dict:
    return {"InstanceId": "i-1", "State": {"Name": state}, "SubnetId": subnet, "KeyName": key,
            "PublicIpAddress": public_ip, "SecurityGroups": [{"GroupId": g} for g in groups]}


@pytest.fixture
def lab(fixture_labs, monkeypatch):
    loaded = load_lab("fixture-lab-07", fixture_labs)
    module = loaded.resolve("checks:web_server_answers").__globals__
    asked: list[str] = []
    monkeypatch.setitem(module, "host_ports", lambda: {"i-1": {"22/tcp": 2200, "80/tcp": 30000}})
    monkeypatch.setitem(module, "_http_ok", lambda url: asked.append(url) or True)
    return loaded, asked


def ec2_with(groups=(DEFAULT_SG, WEB_SG), instances=(), keys=({"KeyName": "lab07-key", "KeyPairId": "key-1"},), vpcs=(VPC,),
             igws=({"InternetGatewayId": "igw-1"},)):
    ec2 = MagicMock()
    ec2.describe_internet_gateways.return_value = {"InternetGateways": list(igws)}
    ec2.describe_vpcs.return_value = {"Vpcs": list(vpcs)}
    ec2.describe_security_groups.return_value = {"SecurityGroups": list(groups)}
    ec2.describe_key_pairs.return_value = {"KeyPairs": list(keys)}
    ec2.describe_instances.return_value = {"Reservations": [{"Instances": list(instances)}]}
    ec2.describe_route_tables.return_value = {"RouteTables": [PUBLIC_TABLE]}
    return ec2


def results(loaded, ec2) -> dict:
    return {r.check_id: r for r in run_checks(loaded, CheckContext(client=lambda service: ec2))}


def test_everything_done_passes(lab):
    loaded, asked = lab
    got = results(loaded, ec2_with(groups=(DEFAULT_SG, WEB_SG, ADMIN_SG), instances=[instance(groups=("sg-web", "sg-admin"))]))
    assert {k: r.passed for k, r in got.items()} == dict.fromkeys(
        ["network-ready", "sg-web-80", "ssh-not-open-to-world", "key-pair-exists", "instance-running", "web-server-answers", "instance-has-two-sgs"], True)
    assert asked == ["http://127.0.0.1:30000/"]
    assert got["instance-running"].resource_ids == ["i-1"]
    assert got["network-ready"].resource_ids == ["vpc-1", "subnet-pub", "igw-1"]


def test_network_without_an_attached_igw_is_not_ready(lab):
    got = results(lab[0], ec2_with(igws=()))
    assert not got["network-ready"].passed and "labctl reset fixture-lab-07" in got["network-ready"].message
    assert got["network-ready"].resource_ids == ["vpc-1"]


def test_fresh_network_fails_every_check_with_guidance(lab):
    got = results(lab[0], ec2_with(groups=(DEFAULT_SG,), keys=()))
    assert [k for k, r in got.items() if r.passed] == ["network-ready"]
    assert "create the web group first" in got["ssh-not-open-to-world"].message
    assert "no key pair" in got["key-pair-exists"].message
    assert "no running instance" in got["web-server-answers"].message


def test_missing_vpc_points_at_reset(lab):
    got = results(lab[0], ec2_with(vpcs=()))
    assert "labctl reset fixture-lab-07" in got["sg-web-80"].message


@pytest.mark.parametrize("bad", [rule("tcp", 22, "0.0.0.0/0"), rule("-1", None, "0.0.0.0/0"),
                                 {"IpProtocol": "tcp", "FromPort": 0, "ToPort": 1024, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}])
def test_ssh_open_to_the_world_fails(lab, bad):
    admin = ADMIN_SG | {"IpPermissions": [bad]}
    got = results(lab[0], ec2_with(groups=(DEFAULT_SG, WEB_SG, admin)))
    assert not got["ssh-not-open-to-world"].passed
    assert got["ssh-not-open-to-world"].resource_ids == ["sg-admin"] and "/32" in got["ssh-not-open-to-world"].message


def test_ssh_from_a_private_range_is_fine(lab):
    admin = ADMIN_SG | {"IpPermissions": [rule("-1", None, "10.0.0.0/8")]}
    assert results(lab[0], ec2_with(groups=(DEFAULT_SG, WEB_SG, admin)))["ssh-not-open-to-world"].passed


@pytest.mark.parametrize("inst", [instance(subnet="subnet-private"), instance(key=None), instance(groups=("sg-admin",)),
                                  instance(state="pending")])
def test_instance_running_needs_public_subnet_key_and_port_80(lab, inst):
    got = results(lab[0], ec2_with(groups=(DEFAULT_SG, WEB_SG, ADMIN_SG), instances=[inst]))
    assert not got["instance-running"].passed and got["instance-running"].resource_ids == ["i-1"]


def test_web_server_not_answering_says_to_wait(lab, monkeypatch):
    loaded, _ = lab
    monkeypatch.setitem(loaded.resolve("checks:web_server_answers").__globals__, "_http_ok", lambda url: False)
    got = results(loaded, ec2_with(instances=[instance()]))
    assert not got["web-server-answers"].passed and "wait a minute" in got["web-server-answers"].message


def test_web_server_without_a_host_port_uses_the_public_ip(lab):
    loaded, asked = lab
    assert results(loaded, ec2_with(instances=[instance(public_ip="54.1.2.3")]))["web-server-answers"].passed
    assert asked == ["http://54.1.2.3/"]


def test_one_security_group_is_not_enough(lab):
    got = results(lab[0], ec2_with(instances=[instance()]))
    assert not got["instance-has-two-sgs"].passed and "second security group" in got["instance-has-two-sgs"].message


def test_setup_builds_a_public_subnet(fixture_labs):
    ec2 = MagicMock()
    ec2.create_vpc.return_value = {"Vpc": {"VpcId": "vpc-1"}}
    ec2.describe_availability_zones.return_value = {"AvailabilityZones": [{"ZoneName": "us-east-1b"}, {"ZoneName": "us-east-1a"}]}
    ec2.create_subnet.return_value = {"Subnet": {"SubnetId": "subnet-1"}}
    ec2.create_internet_gateway.return_value = {"InternetGateway": {"InternetGatewayId": "igw-1"}}
    ec2.create_route_table.return_value = {"RouteTable": {"RouteTableId": "rtb-1"}}
    load_lab("fixture-lab-07", fixture_labs).resolve("checks:setup_network")(CheckContext(client=lambda service: ec2))
    assert ec2.create_vpc.call_args.kwargs["CidrBlock"] == "10.67.0.0/16"
    assert {"Key": "lab", "Value": "fixture-lab-07"} in ec2.create_vpc.call_args.kwargs["TagSpecifications"][0]["Tags"]
    assert ec2.create_subnet.call_args.kwargs["AvailabilityZone"] == "us-east-1a"
    ec2.modify_subnet_attribute.assert_called_once_with(SubnetId="subnet-1", MapPublicIpOnLaunch={"Value": True})
    ec2.attach_internet_gateway.assert_called_once_with(InternetGatewayId="igw-1", VpcId="vpc-1")
    ec2.create_route.assert_called_once_with(RouteTableId="rtb-1", DestinationCidrBlock="0.0.0.0/0", GatewayId="igw-1")
    ec2.associate_route_table.assert_called_once_with(RouteTableId="rtb-1", SubnetId="subnet-1")
