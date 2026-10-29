"""The `lab` profile in the learner's AWS config, so `aws ... --profile lab` reaches the emulator.

The builder shows commands with `--profile lab` (PRD F4.4) so they run when pasted into any
terminal. The config file is the learner's own and may hold work profiles, so this edits text
(configparser would drop comments), touches only the block it marked, keeps a backup of the
file before the first change, and refuses to take over a `[profile lab]` someone else wrote.
"""

import functools
import os
import re
import shutil
import subprocess
from pathlib import Path

from ..config import ACCESS_KEY_ID, API_PORT, HOST, REGION, SECRET_ACCESS_KEY

PROFILE = "lab"
HEADER = f"[profile {PROFILE}]"
MARK = "# managed by labctl: rewritten by `labctl up`, edits here are lost"
BACKUP_SUFFIX = ".cloudy-labs.bak"
ENDPOINT_URL_SINCE = (2, 13)  # first AWS CLI v2 release that reads endpoint_url from a profile


class ProfileError(Exception):
    pass


def config_path() -> Path:
    return Path(os.environ.get("AWS_CONFIG_FILE") or Path.home() / ".aws" / "config").expanduser()


def profile_block() -> str:
    # Fake emulator keys (NFR6); endpoint_url is api-tap, so the learner's calls show in the scene.
    return "\n".join([
        HEADER,
        MARK,
        f"endpoint_url = http://{HOST}:{API_PORT}",
        f"region = {REGION}",
        f"aws_access_key_id = {ACCESS_KEY_ID}",
        f"aws_secret_access_key = {SECRET_ACCESS_KEY}",
        "output = json",
        "cli_pager =",
    ]) + "\n"


def _own(line: str) -> bool:
    """A line of the lab block: the marker or a setting. A blank line or another comment ends it, so a
    comment the learner wrote above the next section stays theirs."""
    s = line.strip()
    return s == MARK or (bool(s) and not s.startswith(("[", "#", ";")))


def _find(lines: list[str]) -> tuple[int, int] | None:
    """Line range [start, end) of the `[profile lab]` header and the lines that belong to it."""
    for i, line in enumerate(lines):
        if line.strip() == HEADER:
            end = i + 1
            while end < len(lines) and _own(lines[end]):
                end += 1
            return i, end
    return None


def render(text: str) -> str:
    """`text` with the lab profile written in. Raises ProfileError for a lab profile labctl did not write."""
    lines = text.splitlines(keepends=True)
    found = _find(lines)
    block = profile_block()
    if found is None:
        sep = "" if not text else "\n" if text.endswith("\n") else "\n\n"
        return text + sep + block if text.strip() else block
    start, end = found
    if start + 1 >= len(lines) or lines[start + 1].strip() != MARK:
        raise ProfileError(
            f"{config_path()} already has a {HEADER} that labctl did not write; rename or remove it, "
            f"then run `labctl up` again (labctl will not overwrite it)"
        )
    return "".join(lines[:start]) + block + "".join(lines[end:])


def ensure_lab_profile() -> str:
    """Write the lab profile if needed. Returns "created", "updated" or "unchanged"."""
    # Write through a symlink (dotfiles managers link ~/.aws/config), never replace the link itself.
    path = config_path().resolve()
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    new = render(old)
    if new == old:
        return "unchanged"
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".labctl-tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(new)
    if path.exists():
        shutil.copymode(path, tmp)
    os.replace(tmp, path)
    return "updated" if old and _find(old.splitlines()) else "created"


def lab_profile_ok() -> bool:
    """Whether the config holds the lab profile exactly as labctl writes it."""
    path = config_path()
    try:
        text = path.read_text(encoding="utf-8")
        return render(text) == text
    except (OSError, ProfileError):
        return False


def credentials_overrides() -> Path | None:
    """The credentials file when it has a `[lab]` section. Its keys win over the fake ones in the config,
    so builder commands would be signed with them."""
    paths = {Path(os.environ.get("AWS_SHARED_CREDENTIALS_FILE") or Path.home() / ".aws" / "credentials").expanduser(),
             Path.home() / ".aws" / "credentials"}  # the builder's runner drops AWS_*, so it reads the default
    for path in sorted(paths):
        try:
            if any(line.strip() == f"[{PROFILE}]" for line in path.read_text(encoding="utf-8").splitlines()):
                return path
        except OSError:
            continue
    return None


@functools.cache  # the installed CLI does not change while labctl runs
def cli_ignores_endpoint_url() -> str | None:
    """The `aws --version` line when that CLI predates endpoint_url in profiles: with it, a pasted
    `--profile lab` command goes to real AWS instead of the emulator. None when fine or unknown."""
    try:
        line = subprocess.run(["aws", "--version"], capture_output=True, text=True, timeout=15).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.match(r"aws-cli/(\d+)\.(\d+)", line)
    if m and (int(m[1]), int(m[2])) < ENDPOINT_URL_SINCE:
        return line
    return None
