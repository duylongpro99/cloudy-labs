"""Find and remove what Floci leaves behind after its container stops.

Floci runs EC2 instances as sibling containers and VPCs as Docker networks, and
`docker compose down` does not remove them. Floci labels all of them with
`io.floci.owner=<host port>`; its own compose container has no such label.
"""

from dataclasses import dataclass, field

from ..config import FLOCI_PORT
from .docker import DockerError, docker, lines


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
    return Orphans(
        containers=lines(docker("ps", "-a", *f, "--format", "{{.Names}}")),
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
