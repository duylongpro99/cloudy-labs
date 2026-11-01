"""Fail when text of a local lab page (labs/*/content/**/*.md, gitignored) shows up in a file git tracks.

Every run of 8 words in the local content is looked up in every tracked text file. A hit prints the
tracked file, how many runs it shares and a short hash of each, never the shared text, and exits 1.
Run it before committing a lab:

    cd server && uv run python scripts/check-content-leak.py

Two kinds of run are not lab content. Titles and tables of contents are on the public labaws.site
listing, so a run the public catalog holds is skipped. A run that is an AWS idiom (a CLI filter, a
list of AZ names) is skipped once a person has reviewed it: its hash goes in
labs/<lab>/leak-review.json with the reason, as {"reviewed": date, "runs": {hash: reason}}.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

N = 8
REPO = Path(__file__).resolve().parents[2]
WORD = re.compile(r"\w+", re.UNICODE)
PUBLIC_CATALOG = "plans/reports/researcher-261031-1358-labaws-catalog-and-floci-coverage.csv"
REVIEW_FILE = "leak-review.json"


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


def run_hash(run: tuple[str, ...]) -> str:
    return hashlib.sha256(" ".join(run).encode()).hexdigest()[:16]


def _reviewed(lab: Path) -> set[str]:
    try:
        return set(json.loads((lab / REVIEW_FILE).read_text())["runs"])
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def shared_runs(repo: Path) -> dict[str, set[tuple[str, ...]]]:
    """Runs of local lab content that tracked files hold, by file."""
    local: set[tuple[str, ...]] = set()
    for lab in (repo / "labs").iterdir() if (repo / "labs").is_dir() else []:
        reviewed = _reviewed(lab)
        for page in lab.glob("content/**/*.md"):
            local |= {r for r in ngrams(page.read_text(encoding="utf-8", errors="ignore")) if run_hash(r) not in reviewed}
    if (public := read_text(repo / PUBLIC_CATALOG)) is not None:
        local -= ngrams(public)
    if not local:
        return {}
    found: dict[str, set[tuple[str, ...]]] = {}
    for path in tracked_files(repo):
        text = read_text(path)
        if text and (shared := ngrams(text) & local):
            found[str(path.relative_to(repo))] = shared
    return found


def leaks(repo: Path) -> dict[str, int]:
    return {name: len(runs) for name, runs in shared_runs(repo).items()}


def main() -> int:
    found = shared_runs(REPO)
    for name, runs in sorted(found.items()):
        print(f"{name}: {len(runs)} run(s) of {N} words from local lab content: {' '.join(sorted(map(run_hash, runs)))}")
    if found:
        print("lab content must stay in labs/*/content/ (gitignored); rewrite these passages in your own words, "
              f"or list a reviewed AWS idiom in labs/<lab>/{REVIEW_FILE}", file=sys.stderr)
        return 1
    print("no local lab content in tracked files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
