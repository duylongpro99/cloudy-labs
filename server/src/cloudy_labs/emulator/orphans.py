"""Find and remove what Floci leaves behind after its container stops.

Floci runs EC2 instances as sibling containers and VPCs as Docker networks, and
`docker compose down` does not remove them. Floci labels all of them with
`io.floci.owner=<port>`, the port Floci listens on inside its container. Compose runs
labctl's Floci on FLOCI_PORT inside and out, so the label tells its resources apart from
those of any other Floci on the machine (which listen on the default 4566). Floci's own
compose container has no such label.
"""

import re
from dataclasses import dataclass, field

from ..config import FLOCI_PORT
from .docker import DockerError, docker, lines

# Floci publishes an instance's application ports through socat containers named
# floci-aws-ec2-fwd-<instance-id>-<port>. They carry no io.floci label, so they are tied
# to labctl's Floci through the instance containers it owns (floci-aws-ec2-<instance-id>).
FORWARDER_FILTERS = ["--filter", "label=floci_emulator=floci-aws", "--filter", "name=floci-aws-ec2-fwd-"]
INSTANCE = re.compile(r"^floci-aws-ec2-(i-[0-9a-f]+)$")


def owner_filters(port: int = FLOCI_PORT) -> list[str]:
    return ["--filter", f"label=io.floci.owner={port}", "--filter", "label=io.floci=aws"]


@dataclass(frozen=True)
class Orphans:
    containers: list[str]
    networks: list[str]
    volumes: list[str]
    errors: list[str] = field(default_factory=list)  # removals that failed

    def __len__(self) -> int:
        return len(self.containers) + len(self.networks) + len(self.volumes)


def find_orphans(port: int = FLOCI_PORT) -> Orphans:
    f = owner_filters(port)
    owned = lines(docker("ps", "-a", *f, "--format", "{{.Names}}"))
    prefixes = tuple(f"floci-aws-ec2-fwd-{m[1]}-" for m in map(INSTANCE.match, owned) if m)
    forwarders = lines(docker("ps", "-a", *FORWARDER_FILTERS, "--format", "{{.Names}}")) if prefixes else []
    return Orphans(
        containers=owned + [name for name in forwarders if name.startswith(prefixes)],
        networks=lines(docker("network", "ls", *f, "--format", "{{.Name}}")),
        volumes=lines(docker("volume", "ls", *f, "--format", "{{.Name}}")),
    )


def remove_orphans(port: int = FLOCI_PORT) -> Orphans:
    """Remove containers first: a network or volume still in use cannot be removed.

    A failed removal is recorded in `errors` and the rest still go, so one stuck
    resource (say, a user container attached to a VPC network) cannot block teardown.
    """
    found = find_orphans(port)
    for names, cmd in (
        (found.containers, ("rm", "-f", "-v")),
        (found.networks, ("network", "rm")),
        (found.volumes, ("volume", "rm", "-f")),
    ):
        if names:
            try:
                docker(*cmd, *names)
            except DockerError as e:
                found.errors.append(str(e))
    return found
