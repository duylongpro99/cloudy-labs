"""`labctl`: drive the local emulator stack and the lab lifecycle from the terminal."""

import argparse
import json
import shlex
import sys
import time
from collections.abc import Callable

from .emulator import stack
from .emulator.docker import DockerError
from .engine import Engine, EngineError, result_dict
from .labs import LabError, load_lab
from .providers import provider_for

# name: (help, lab argument: "required" | "optional" | None, accepts --json)
COMMANDS: dict[str, tuple[str, str | None, bool]] = {
    "up": ("start the emulator stack", None, False),
    "down": ("stop the emulator stack and remove leftover containers", None, False),
    "env": ("print shell exports that point the AWS CLI at the emulator", "optional", False),
    "start": ("reset the emulator and open a new attempt at a lab", "required", False),
    "check": ("run the lab's checks against the emulator", "required", True),
    "reset": ("reset the emulator, rerun the lab's setup and open a new attempt", "required", False),
    "status": ("show emulator health, the current lab and its latest results", "optional", True),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="labctl", description="Cloudy Labs: hands-on AWS labs on local emulators.")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")
    for name, (help_text, lab_arg, has_json) in COMMANDS.items():
        p = sub.add_parser(name, help=help_text, description=help_text)
        if lab_arg == "required":
            p.add_argument("lab", help="lab id (directory name under labs/)")
        elif lab_arg == "optional":
            p.add_argument("lab", nargs="?", help="lab id (directory name under labs/)")
        if has_json:
            p.add_argument("--json", action="store_true", help="print machine-readable JSON")
    return parser


def cmd_up(args: argparse.Namespace) -> int:
    stack.up()
    return 0


def cmd_down(args: argparse.Namespace) -> int:
    stack.down()
    return 0


def cmd_env(args: argparse.Namespace) -> int:
    provider = provider_for(load_lab(args.lab).lab if args.lab else None)
    for key, value in provider.env().items():
        print(f"export {key}={shlex.quote(value)}")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    Engine.default().start(args.lab)
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    t0 = time.monotonic()
    Engine.default().reset(args.lab)
    print(f"done in {time.monotonic() - t0:.1f}s")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    attempt, results = Engine.default().check(args.lab)
    passed = all(r.passed for r in results)
    if args.json:
        print(json.dumps({"lab": args.lab, "attempt": attempt, "passed": passed, "results": [result_dict(r) for r in results]}))
    else:
        for r in results:
            ids = f" [{', '.join(r.resource_ids)}]" if r.resource_ids else ""
            print(f"{'PASS' if r.passed else 'FAIL'}  {r.check_id}: {r.message}{ids}")
        print(f"{sum(r.passed for r in results)}/{len(results)} checks passed")
    return 0 if passed else 1


def cmd_status(args: argparse.Namespace) -> int:
    s = Engine.default().status(args.lab)
    if args.json:
        print(json.dumps(s))
        return 0
    for name, ok in s["emulators"].items():
        print(f"{name}: {'up' if ok else 'down'}")
    current = s["current_attempt"]
    print(f"current lab: {current['lab_id']} (attempt {current['id']})" if current else "current lab: none")
    if s["lab"]:
        print(f"latest results for {s['lab']}:" if s["results"] else f"no checks run yet for {s['lab']}")
        for r in s["results"]:
            print(f"  {'PASS' if r['passed'] else 'FAIL'}  {r['check_id']}: {r['message']}")
    print("labs:" if s["labs"] else "labs: none found")
    for lab in s["labs"]:
        print(f"  {'[x]' if lab['completed'] else '[ ]'} {lab['id']}: {lab['title']}")
    return 0


HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "up": cmd_up,
    "down": cmd_down,
    "env": cmd_env,
    "start": cmd_start,
    "check": cmd_check,
    "reset": cmd_reset,
    "status": cmd_status,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return HANDLERS[args.command](args)
    except (DockerError, LabError, EngineError) as e:
        print(f"labctl {args.command}: {e}", file=sys.stderr)
    except Exception as e:  # keep `check`'s exit code meaningful: 1 means "checks failed", never "crashed"
        print(f"labctl {args.command}: unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
    return 2 if args.command == "check" else 1
