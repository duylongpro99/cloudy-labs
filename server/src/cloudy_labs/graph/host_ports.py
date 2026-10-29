"""Host ports Docker publishes for each Floci instance.

On Docker Desktop Floci reports PublicIpAddress 127.0.0.1, so the scene shows the host
ports instead. SSH is published on the instance container itself
(floci-aws-ec2-i-<id>); each port a security group opens goes through a socat container
named floci-aws-ec2-fwd-i-<id>-<port>.
"""

import re

from ..emulator.docker import DockerError, docker, lines

CONTAINER = re.compile(r"^floci-aws-ec2-(?:fwd-)?(i-[0-9a-f]+)(?:-\d+)?$")
MAPPING = re.compile(r"(?:\d+\.\d+\.\d+\.\d+|\[::\]):(\d+)->(\d+/\w+)")


def parse_ps(output: str) -> dict[str, dict[str, int]]:
    """Parse `docker ps --format '{{.Names}}\\t{{.Ports}}'` into {instance id: {"22/tcp": 2200}}."""
    found: dict[str, dict[str, int]] = {}
    for line in lines(output):
        name, _, ports = line.partition("\t")
        m = CONTAINER.match(name.strip())
        if not m:
            continue
        for host, container in MAPPING.findall(ports):
            found.setdefault(m.group(1), {})[container] = int(host)
    return {iid: dict(sorted(p.items())) for iid, p in found.items()}


def host_ports() -> dict[str, dict[str, int]]:
    """Empty when Docker is not reachable: host ports are a nicety, never a reason to fail."""
    try:
        # Bounded: a hung Docker must not stall every later graph update behind this call.
        return parse_ps(docker("ps", "--filter", "name=floci-aws-ec2-", "--format", "{{.Names}}\t{{.Ports}}", timeout=5))
    except DockerError:
        return {}
