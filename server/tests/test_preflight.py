import socket
from ipaddress import IPv4Network as Net

from cloudy_labs.emulator.preflight import cidr_overlaps, parse_networks, port_free

INSPECT = (
    "bridge\t172.17.0.0/16 \n"
    "host\t\n"
    "cloudy-labs_default\t172.19.0.0/16 fd00::/64 \n"
    "floci-aws-vpc-4566-us-east-1-vpc-1\t10.0.0.0/16 \n"
    "corp\t10.0.0.0/8 \n"
)


def test_parse_networks_skips_ipv6_empty_and_floci_vpcs():
    assert parse_networks(INSPECT) == [
        ("bridge", Net("172.17.0.0/16")),
        ("cloudy-labs_default", Net("172.19.0.0/16")),
        ("corp", Net("10.0.0.0/8")),
    ]


def test_cidr_overlaps():
    nets = [("bridge", Net("172.17.0.0/16")), ("corp", Net("10.0.0.0/8")), ("lan", Net("192.168.1.0/24"))]
    labs = [Net("10.0.0.0/16"), Net("192.168.0.0/16"), Net("172.31.0.0/16")]
    assert cidr_overlaps(labs, nets) == [
        (Net("10.0.0.0/16"), "corp", Net("10.0.0.0/8")),  # lab inside network
        (Net("192.168.0.0/16"), "lan", Net("192.168.1.0/24")),  # network inside lab
    ]
    assert cidr_overlaps([], nets) == []


def test_port_free_detects_listener():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        port = s.getsockname()[1]
        assert not port_free(port)
    assert port_free(port)


def test_port_free_detects_wildcard_listener():
    # On macOS a bind to 127.0.0.1 succeeds next to a 0.0.0.0 listener; the check must still see it.
    with socket.socket() as s:
        s.bind(("0.0.0.0", 0))
        s.listen()
        assert not port_free(s.getsockname()[1])
