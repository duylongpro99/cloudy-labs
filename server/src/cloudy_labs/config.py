"""Paths, ports and the fake credentials shared by labctl and the checkers."""

import os
from pathlib import Path

API_PORT = 4566  # api-tap in front of Floci: what the learner's CLI and the checkers use
FLOCI_PORT = 4567  # Floci itself, for labctl and the collector
TAP_EVENTS_PORT = 4568  # api-tap's stream of write calls
MOTO_TAP_PORT = 4569  # api-tap-moto in front of moto, for labs that run on moto
MOTO_TAP_EVENTS_PORT = 4570  # api-tap-moto's stream of write calls
SERVER_PORT = 8730  # `labctl serve`
WEB_DEV_PORT = 5174  # Vite dev server of web/, the only browser origin `labctl serve` accepts
MOTO_PORT = 5050
HOST = "127.0.0.1"  # NFR7: emulators listen on loopback only
# A lab names its region; this one applies while no lab is open.
DEFAULT_REGION = "ap-southeast-2"
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
