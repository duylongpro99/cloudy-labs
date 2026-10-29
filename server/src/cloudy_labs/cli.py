"""`labctl`: drive the local emulator stack and the lab lifecycle from the terminal."""

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable

from .config import HOST, SERVER_PORT, WEB_DEV_PORT
from .emulator import stack
from .emulator.aws_profile import (
    ProfileError, cli_ignores_endpoint_url, config_path, credentials_overrides, ensure_lab_profile, lab_profile_ok,
)
from .emulator.docker import DockerError
from .emulator.preflight import port_free
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
    "serve": ("run the lab-server that feeds the live 3D scene (foreground, Ctrl-C to stop)", None, False),
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
    # The builder shows and runs `aws ... --profile lab`; the profile points the CLI at the emulator.
    try:
        outcome = ensure_lab_profile()
    except ProfileError as e:
        print(f"labctl up: the emulator is up, but the builder cannot run commands: {e}", file=sys.stderr)
        return 1
    if outcome != "unchanged":
        print(f"aws profile 'lab' {outcome} in {config_path()} (use it with `aws ... --profile lab`)")
    _warn_profile_overrides("labctl up")
    return 0


def _warn_profile_overrides(cmd: str) -> None:
    if creds := credentials_overrides():
        print(f"{cmd}: {creds} has a [lab] section; its keys override the emulator's fake keys for "
              "`--profile lab`, so rename that section", file=sys.stderr)


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
    # Floci itself can be up while the proxy the learner's CLI goes through is not.
    s["api_tap"] = stack.reachable("api-tap")
    if args.json:
        print(json.dumps(s))
        return 0
    for name, ok in s["emulators"].items():
        print(f"{name}: {'up' if ok else 'down'}")
    print(f"api-tap: {'up' if s['api_tap'] else 'down'}")
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


def cmd_serve(args: argparse.Namespace) -> int:
    if not stack.is_running():
        print("labctl serve: the emulator stack is not running; start it with `labctl up`", file=sys.stderr)
        return 1
    if not port_free(SERVER_PORT, HOST):
        try:
            pids = subprocess.run(["lsof", "-t", "-i", f"tcp:{SERVER_PORT}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()
        except FileNotFoundError:  # no lsof (minimal Linux): report the port without its owner
            pids = []
        owner = f" by PID {', '.join(pids)}" if pids else ""
        print(f"labctl serve: port {SERVER_PORT} is already in use{owner}; stop that process and retry", file=sys.stderr)
        return 1
    if not shutil.which("aws"):
        print("labctl serve: the aws CLI is not on PATH, so the builder can show commands but not run them; "
              "install AWS CLI v2 (https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)",
              file=sys.stderr)
    elif old := cli_ignores_endpoint_url():
        print(f"labctl serve: {old} ignores endpoint_url in profiles, so `--profile lab` commands would go to "
              "real AWS; upgrade to AWS CLI v2.13 or later", file=sys.stderr)
    if not lab_profile_ok():
        print(f"labctl serve: {config_path()} has no up-to-date [profile lab], so builder commands would not "
              "reach the emulator; run `labctl up` to write it", file=sys.stderr)
    _warn_profile_overrides("labctl serve")
    import uvicorn

    from .server.app import create_app

    print(f"lab-server on http://{HOST}:{SERVER_PORT} (Ctrl-C to stop)", flush=True)
    print(f"open the scene at http://{HOST}:{WEB_DEV_PORT} after `pnpm dev` in web/", flush=True)
    # Loopback only, by design: there is deliberately no option to bind another address.
    uvicorn.run(create_app(), host=HOST, port=SERVER_PORT, log_level="warning")
    return 0


HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "up": cmd_up,
    "down": cmd_down,
    "env": cmd_env,
    "start": cmd_start,
    "check": cmd_check,
    "reset": cmd_reset,
    "status": cmd_status,
    "serve": cmd_serve,
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
