"""Thin wrapper over the `docker` CLI; no Docker SDK dependency."""

import subprocess


class DockerError(Exception):
    pass


def docker(*args: str) -> str:
    try:
        proc = subprocess.run(["docker", *args], capture_output=True, text=True)
    except FileNotFoundError as e:
        raise DockerError("docker CLI not found; install Docker Desktop or Docker Engine") from e
    if proc.returncode != 0:
        raise DockerError(f"docker {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def require_docker() -> None:
    try:
        docker("info", "--format", "{{.ServerVersion}}")
    except DockerError as e:
        raise DockerError(f"Docker is not running ({e})") from e


def lines(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]
