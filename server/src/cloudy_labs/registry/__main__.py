"""`python -m cloudy_labs.registry export [--out FILE]`: the registry's public view as JSON.

The web app bundles this as its default registry (web/src/registry/registry.json) and the icon
import script reads it, so neither needs the lab-server running.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import default_registry


def export_json() -> str:
    return json.dumps(default_registry().public(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cloudy_labs.registry")
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="print the registry's public view as JSON")
    export.add_argument("--out", type=Path, help="write to this file instead of stdout")
    args = parser.parse_args(argv)
    text = export_json()
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
