"""Paths, ports and the fake credentials shared by labctl and the checkers."""

import os
from pathlib import Path

FLOCI_PORT = 4566
MOTO_PORT = 5050
HOST = "127.0.0.1"  # NFR7: emulators listen on loopback only
REGION = "us-east-1"
# Emulator credentials are fake on purpose (NFR6).
ACCESS_KEY_ID = "test"
SECRET_ACCESS_KEY = "test"

COMPOSE_PROJECT = "cloudy-labs"
REPO_ROOT = Path(__file__).resolve().parents[3]


def home() -> Path:
    """Directory for local state such as progress.db; kept outside the repo."""
    return Path(os.environ.get("CLOUDY_LABS_HOME", Path.home() / ".cloudy-labs"))


def labs_dir() -> Path:
    return Path(os.environ.get("CLOUDY_LABS_LABS_DIR", REPO_ROOT / "labs"))
