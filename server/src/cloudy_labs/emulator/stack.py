"""Start and stop the emulator stack defined in compose.yaml."""

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from ..config import COMPOSE_PROJECT, FLOCI_PORT, HOST, MOTO_PORT
from .docker import DockerError, docker, lines, require_docker
from .orphans import Orphans, remove_orphans
from .preflight import port_busy_message, port_free

COMPOSE_FILE = Path(__file__).with_name("compose.yaml")
SERVICES = {"floci": FLOCI_PORT, "moto": MOTO_PORT}
HEALTH_PATHS = {"floci": "/_floci/health", "moto": "/moto-api/"}
# Floci pulls alpine/socat without a tag the first time an app port is published, which
# makes Docker fetch every tag (about two minutes). Having :latest locally avoids that.
SOCAT_IMAGE = "alpine/socat:latest"
# Amazon Linux 2023 AMIs map to these images in ec2-image-catalog.yaml, one per AMI architecture
# because Floci pulls for the entry's platform. Built locally from al2023/Dockerfile; bump
# AL2023_VERSION whenever that Dockerfile changes (`python -m cloudy_labs.emulator.images
# bump-base` does it together with the base image digest and the catalog).
AL2023_VERSION = 1
AL2023_PLATFORMS = {"x86_64": "linux/amd64", "arm64": "linux/arm64"}
AL2023_DIR = Path(__file__).with_name("al2023")


def al2023_image(architecture: str, version: int = AL2023_VERSION) -> str:
    return f"cloudy-labs/al2023:{version}-{architecture}"


AL2023_IMAGES = {al2023_image(arch): platform for arch, platform in AL2023_PLATFORMS.items()}

Log = Callable[[str], None]


def compose(*args: str) -> str:
    return docker("compose", "-p", COMPOSE_PROJECT, "-f", str(COMPOSE_FILE), *args)


def parse_ps(output: str) -> dict[str, dict]:
    """`docker compose ps --format json` prints one object per line (older versions: one array)."""
    output = output.strip()
    if not output:
        return {}
    rows = json.loads(output) if output.startswith("[") else [json.loads(line) for line in lines(output)]
    return {row["Service"]: row for row in rows}


def service_states() -> dict[str, dict]:
    return parse_ps(compose("ps", "--all", "--format", "json"))


def is_running() -> bool:
    states = service_states()
    return all(
        states.get(name, {}).get("State") == "running" and states[name].get("Health", "healthy") == "healthy"
        for name in SERVICES
    )


def endpoints() -> dict[str, str]:
    return {name: f"http://{HOST}:{port}" for name, port in SERVICES.items()}


def reachable(name: str) -> bool:
    """Whether the service answers on its host port, which is what the CLI and checkers use."""
    try:
        with urllib.request.urlopen(endpoints()[name] + HEALTH_PATHS[name], timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def recreate_floci() -> Orphans:
    """Give Floci a fresh container with empty state and no instances left behind.

    Floci attaches its own container to every VPC network. Restarting it reconnects those
    networks and Floci then deletes them on startup, which can leave Docker Desktop
    forwarding the host port to an endpoint that no longer exists (the container stays
    healthy but 127.0.0.1:4566 hangs). Removing the container detaches it from every
    network first, and the new container joins only the compose network.
    """
    compose("rm", "-s", "-f", "floci")
    found = remove_orphans()
    compose("up", "-d", "--wait", "floci")
    return found


def up(log: Log = print) -> None:
    require_docker()
    states = service_states()
    if states and is_running():
        if reachable("floci"):
            log("emulator stack is already running")
        else:
            # Healthy inside Docker but not on the host port: the stale forward described in
            # recreate_floci, left by a restart outside labctl.
            log(f"floci is not reachable on {endpoints()['floci']}; recreating its container...")
            _report(recreate_floci(), log, "while recreating floci")
    else:
        if not states:  # our containers do not hold the ports, so something else must not either
            for port in SERVICES.values():
                if not port_free(port, HOST):
                    raise DockerError(port_busy_message(port))
        if states.get("floci", {}).get("State") != "running":
            # Only while Floci is down: a running Floci still owns its instance containers.
            # A stopped Floci container may still be attached to VPC networks; see recreate_floci.
            compose("rm", "-s", "-f", "floci")
            _report(remove_orphans(), log, "from an earlier run")
        log("starting emulator stack (floci, moto)...")
        compose("up", "-d", "--wait")
    if not _have_image(SOCAT_IMAGE):
        log(f"pulling {SOCAT_IMAGE} (Floci needs it to publish instance ports)...")
        docker("pull", SOCAT_IMAGE)
    for image, platform in AL2023_IMAGES.items():
        if not _have_image(image):
            log(f"building {image} for Amazon Linux 2023 instances (once, up to a minute)...")
            docker("build", "-q", "--platform", platform, "-t", image, str(AL2023_DIR))
    for name, url in endpoints().items():
        log(f"{name}: {url}")


def down(log: Log = print) -> None:
    require_docker()
    # Instance containers join the compose network, so they must go before `compose down` removes it.
    compose("stop")
    before = remove_orphans()
    compose("down", "-v", "--remove-orphans")
    after = remove_orphans()
    log(f"emulator stack stopped; cleaned up {len(before) + len(after)} leftover Floci resources")
    # Errors from the first pass may clear once compose has removed its network; only the last pass counts.
    if after.errors:
        raise DockerError("could not remove some Floci resources: " + "; ".join(after.errors))


def _have_image(ref: str) -> bool:
    return bool(lines(docker("image", "ls", "-q", ref)))


def _report(found, log: Log, when: str) -> None:
    if found:
        log(f"removed {len(found)} leftover Floci resources {when}")
    for error in found.errors:
        log(f"warning: {error}")
