"""Checks that run before the stack or a lab starts."""

import socket
from ipaddress import IPv4Network, ip_network

from .docker import docker, lines

# VPC networks created by Floci itself; a lab's own VPC is expected to "overlap" them.
OWN_NETWORK_PREFIX = "floci-aws-vpc-"


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    """True when nothing accepts connections on host:port.

    Connecting, not binding: on macOS a bind to 127.0.0.1 succeeds next to a 0.0.0.0 listener,
    and a plain bind fails on TIME_WAIT sockets left by a stack that just stopped.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) != 0


def port_busy_message(port: int) -> str:
    return f"port {port} is in use by another process; free it (see `lsof -i :{port}`) and retry"


def parse_networks(output: str) -> list[tuple[str, IPv4Network]]:
    """Parse `docker network inspect --format '{{.Name}}\\t{{range .IPAM.Config}}{{.Subnet}} {{end}}'`."""
    found = []
    for line in lines(output):
        name, _, subnets = line.partition("\t")
        if name.startswith(OWN_NETWORK_PREFIX):
            continue
        for subnet in subnets.split():
            net = ip_network(subnet, strict=False)
            if isinstance(net, IPv4Network):
                found.append((name, net))
    return found


def docker_networks() -> list[tuple[str, IPv4Network]]:
    ids = lines(docker("network", "ls", "-q"))
    if not ids:
        return []
    fmt = "{{.Name}}\t{{range .IPAM.Config}}{{.Subnet}} {{end}}"
    return parse_networks(docker("network", "inspect", "--format", fmt, *ids))


def cidr_overlaps(
    lab_cidrs: list[IPv4Network], networks: list[tuple[str, IPv4Network]]
) -> list[tuple[IPv4Network, str, IPv4Network]]:
    return [(cidr, name, net) for cidr in lab_cidrs for name, net in networks if cidr.overlaps(net)]


def overlap_warning(cidr: IPv4Network, name: str, net: IPv4Network) -> str:
    # Floci does not fail on overlap; it quietly builds the VPC network on 10.240.0.0/16 instead.
    return (
        f"lab CIDR {cidr} overlaps Docker network {name} ({net}); Floci will place this VPC on "
        "10.240.0.0/16 instead, so private IPs will not match the lab text"
    )
