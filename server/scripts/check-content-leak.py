"""Fail when text of a local lab page (labs/*/content/**/*.md, gitignored) shows up in a file git tracks.

Every run of 8 words in the local content is looked up in every tracked text file. A hit prints the
tracked file and how many runs it shares, never the shared text, and exits 1. Run it before committing
a lab:

    cd server && uv run python scripts/check-content-leak.py
"""

import re
import subprocess
import sys
from pathlib import Path

N = 8
REPO = Path(__file__).resolve().parents[2]
WORD = re.compile(r"\w+", re.UNICODE)


def ngrams(text: str) -> set[tuple[str, ...]]:
    words = WORD.findall(text.lower())
    return {tuple(words[i:i + N]) for i in range(len(words) - N + 1)}


def tracked_files(repo: Path) -> list[Path]:
    out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"], check=True, capture_output=True).stdout
    return [repo / name for name in out.decode().split("\0") if name]


def read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:  # deleted in the working tree, or not a regular file
        return None
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="ignore")


def leaks(repo: Path) -> dict[str, int]:
    local: set[tuple[str, ...]] = set()
    for page in (repo / "labs").glob("*/content/**/*.md"):
        local |= ngrams(page.read_text(encoding="utf-8", errors="ignore"))
    if not local:
        return {}
    found: dict[str, int] = {}
    for path in tracked_files(repo):
        text = read_text(path)
        if text and (shared := len(ngrams(text) & local)):
            found[str(path.relative_to(repo))] = shared
    return found


def main() -> int:
    found = leaks(REPO)
    for name, count in sorted(found.items()):
        print(f"{name}: {count} run(s) of {N} words from local lab content")
    if found:
        print("lab content must stay in labs/*/content/ (gitignored); rewrite these passages in your own words",
              file=sys.stderr)
        return 1
    print("no local lab content in tracked files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
