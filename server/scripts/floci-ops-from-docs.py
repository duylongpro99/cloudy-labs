"""Write registry/floci-ops-<version>.json: the API actions Floci documents at a tag, per botocore service.

Floci's docs/services/*.md list each service's actions in tables whose first column is the action
name (backticked or not). A row that says the action is refused, and actions named under a
"Not implemented"/"Unsupported" heading, are listed apart as `refused`. Each doc is matched to the
botocore service(s) whose operations it names most, so the JSON speaks botocore names.

    uv run python scripts/floci-ops-from-docs.py 2.3.0            # fetches the docs from GitHub
    uv run python scripts/floci-ops-from-docs.py 2.3.0 --docs-dir /path/to/docs/services

Fetching lists the folder through the GitHub API (`gh` must be logged in) and reads each file
from raw.githubusercontent.com. Docs are read as text; nothing in them is run.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import botocore.session

REPO = "floci-io/floci"
OUT_DIR = Path(__file__).resolve().parents[1] / "src" / "cloudy_labs" / "registry"
ROW = re.compile(r"^\|\s*`?([A-Z][A-Za-z0-9]+)`?\s*\|(.*)$")
NAME_LIST = re.compile(r"^\s*`?[A-Z][A-Za-z0-9]+`?(\s*,\s*`?[A-Z][A-Za-z0-9]+`?)*\s*$")
NAME = re.compile(r"[A-Z][A-Za-z0-9]+")
TICKED = re.compile(r"`([A-Z][A-Za-z0-9]+)`")
BULLET = re.compile(r"^\s*[-*]\s+")
# A row whose description starts like this documents the action as refused.
REFUSED_ROW = re.compile(r"^\s*(refused|not implemented|not supported|unsupported|no-op|returns? (an? )?error)\b", re.I)
REFUSED_SECTION = re.compile(r"not implemented|unsupported|not supported", re.I)
LIMITS = re.compile(r"limitation|differences?", re.I)
COMPLETE = re.compile(r"complete [\w\s.-]{0,60}API surface", re.I)
# A doc documents a second service only when that service has this share of the doc's actions
# (CloudWatch documents Logs; a doc that names a few S3 calls in passing does not document S3).
MIN_SHARE = 0.2


def fetch(version: str) -> dict[str, str]:
    names = subprocess.run(["gh", "api", f"repos/{REPO}/contents/docs/services?ref={version}", "--jq", ".[].name"],
                           check=True, capture_output=True, text=True).stdout.split()
    out = {}
    for name in names:
        if name.endswith(".md"):
            url = f"https://raw.githubusercontent.com/{REPO}/{version}/docs/services/{name}"
            with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310 - a fixed https host
                out[name] = r.read().decode("utf-8")
    return out


def read_dir(path: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(path.glob("*.md"))}


def actions(text: str) -> tuple[set[str], set[str]]:
    """(documented, refused) action names of one doc: table rows naming an action first, table
    cells listing actions, and bullets naming actions in backticks. Bullets under a limitations
    heading count for neither; names under a not-implemented heading are refused."""
    documented: set[str] = set()
    refused: set[str] = set()
    section = "normal"
    for line in text.splitlines():
        if line.startswith("#"):
            section = "refused" if REFUSED_SECTION.search(line) else "limits" if LIMITS.search(line) else "normal"
            continue
        if not line.startswith("|") and line.rstrip().endswith(":") and LIMITS.search(line):
            section = "limits"
        target = refused if section == "refused" else documented
        if m := ROW.match(line.strip()):
            name, rest = m.groups()
            if name not in ("Action", "Operation", "API", "Category", "Area", "Key"):
                (refused if REFUSED_ROW.search(rest.lstrip("| ")) else target).add(name)
            for cell in rest.split("|"):
                if "," in cell and NAME_LIST.match(cell):
                    target.update(NAME.findall(cell.replace("`", "")))
        elif line.startswith("|"):
            for cell in line.strip("|").split("|")[1:]:
                if "," in cell and NAME_LIST.match(cell):
                    target.update(NAME.findall(cell.replace("`", "")))
        elif BULLET.match(line) and section != "limits":
            target.update(TICKED.findall(line))
    return documented, refused - documented


def botocore_ops() -> dict[str, set[str]]:
    session = botocore.session.get_session()
    return {s: set(session.get_service_model(s).operation_names) for s in session.get_available_services()}


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def assign(names: set[str], services: dict[str, set[str]], doc: str = "") -> dict[str, set[str]]:
    """Each name to the service that documents most of the doc's names and has it. On a tie (DocumentDB
    and Neptune share RDS's operation names) the service named like the doc wins."""
    stem = _key(doc.removesuffix(".md"))
    score = sorted(((len(names & ops), _key(s) == stem, s) for s, ops in services.items()), reverse=True)
    out: dict[str, set[str]] = defaultdict(set)
    left = set(names)
    for count, _, service in score:
        if out and count < MIN_SHARE * len(names):
            break
        if count == 0:
            break
        hit = left & services[service]
        if hit:
            out[service] |= hit
            left -= hit
    return out


def build(version: str, docs: dict[str, str]) -> dict:
    services = botocore_ops()
    by_key = {_key(s): s for s in services}
    supported: dict[str, set[str]] = defaultdict(set)
    refused: dict[str, set[str]] = defaultdict(set)
    complete: set[str] = set()
    unlisted: set[str] = set()
    doc_services: dict[str, list[str]] = {}
    for name, text in sorted(docs.items()):
        documented, refused_names = actions(text)
        placed = assign(documented, services, name)
        own = by_key.get(_key(name.removesuffix(".md")))
        if own and COMPLETE.search(text):  # "the complete <service> API surface is routed"
            placed.setdefault(own, set()).update(services[own])
            complete.add(own)
        elif own and not placed:  # the doc describes the service in prose, without naming actions
            unlisted.add(own)
            placed[own] = set()
        for service, ops in placed.items():
            supported[service] |= ops
        doc_services[name] = sorted(placed)
        for service, ops in assign(refused_names, {s: services[s] for s in placed} or services, name).items():
            refused[service] |= ops
    for service in refused:
        refused[service] -= supported[service]
    out: dict[str, dict] = {}
    for s in sorted(supported):
        out[s] = {"supported": sorted(supported[s]), "refused": sorted(refused.get(s, ()))}
        if s in complete:
            out[s]["complete"] = True
        if s in unlisted:
            out[s]["unlisted"] = True  # Floci has the service; its docs do not list the actions
    return {
        "floci_version": version,
        "source": f"https://github.com/{REPO}/tree/{version}/docs/services",
        "services": out,
        "docs": doc_services,
        "undocumented": sorted(n for n, placed in doc_services.items() if not placed),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version")
    parser.add_argument("--docs-dir", type=Path)
    args = parser.parse_args(argv)
    docs = read_dir(args.docs_dir) if args.docs_dir else fetch(args.version)
    out = OUT_DIR / f"floci-ops-{args.version}.json"
    data = build(args.version, docs)
    out.write_text(json.dumps(data, indent=1, sort_keys=False) + "\n")
    total = sum(len(v["supported"]) for v in data["services"].values())
    print(f"{out.name}: {len(data['services'])} services, {total} actions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
