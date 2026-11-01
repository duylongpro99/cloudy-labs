"""`labctl`: drive the local emulator stack and the lab lifecycle from the terminal."""

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

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
    "credentials": ("print an emulator's keys for the AWS CLI's credential_process (used by the lab profile)", None, False),
    "content": ("manage a lab's local content (theory and hints; gitignored, never committed)", None, False),
    "coverage": ("say whether the platform can run a lab, or the public catalog, and what it lacks", "optional", True),
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
        if name == "credentials":
            p.add_argument("emulator", choices=["moto"], help="the emulator whose keys to print")
        if name == "content":
            actions = p.add_subparsers(dest="action", required=True, metavar="action")
            imp = actions.add_parser("import", help="copy a pasted lab page into labs/<lab>/content/lab.md")
            imp.add_argument("lab", help="lab id (directory name under labs/)")
            imp.add_argument("file", type=Path, help="the markdown file to import")
            imp.add_argument("--fetch-images", action="store_true",
                             help="download the page's http(s) images into the content directory")
        if name == "coverage":
            p.add_argument("--catalog", type=Path, metavar="CSV", help="judge every lab of a catalog CSV from its metadata")
            p.add_argument("--matrix", action="store_true", help="rewrite docs/coverage.md from the registry")
            p.add_argument("--accept", action="store_true",
                           help="record the lab's unrecognised lines as reviewed (ignored unless --require names them)")
            p.add_argument("--require", type=int, action="append", default=[], metavar="LINE",
                           help="with --accept: a line whose resource the lab does need (repeatable)")
            p.add_argument("--optional", type=int, action="append", default=[], metavar="LINE",
                           help="with --accept: a command line the page calls optional; what it lacks is a caveat "
                                "(repeatable)")
            p.add_argument("--quote", action="store_true",
                           help="print the text of the lines to review (to this terminal only; never in --json)")
            p.add_argument("--strict", action="store_true", help="fail when the contract results are missing or stale")
    return parser


def profile_target() -> tuple[str, str]:
    """(emulator, region) the lab profile should point at: those of the open lab, else Floci in the
    default region. Reset and down keep whatever the last `labctl start` chose."""
    from .config import DEFAULT_REGION, home
    from .progress import Progress

    progress = Progress(home() / "progress.db")
    try:
        attempt = progress.current_attempt()
    finally:
        progress.close()
    if attempt is not None:
        try:
            lab = load_lab(attempt.lab_id).lab
            return lab.emulator, lab.region
        except LabError:
            pass  # the open lab no longer loads: fall back to the defaults
    return "floci", DEFAULT_REGION


def _write_profile(cmd: str, emulator: str, region: str) -> int:
    try:
        outcome = ensure_lab_profile(emulator, region)
    except ProfileError as e:
        print(f"{cmd}: the builder cannot run commands: {e}", file=sys.stderr)
        return 1
    if outcome != "unchanged":
        print(f"aws profile 'lab' {outcome} in {config_path()} for {emulator} in {region} "
              "(use it with `aws ... --profile lab`)")
    _warn_profile_overrides(cmd)
    return 0


def cmd_up(args: argparse.Namespace) -> int:
    stack.up()
    # The builder shows and runs `aws ... --profile lab`; the profile points the CLI at the emulator.
    return _write_profile("labctl up", *profile_target())


def _warn_profile_overrides(cmd: str) -> None:
    if creds := credentials_overrides():
        print(f"{cmd}: {creds} has a [lab] section; its keys override the emulator's fake keys for "
              "`--profile lab`, so rename that section", file=sys.stderr)


def cmd_down(args: argparse.Namespace) -> int:
    stack.down()
    return 0


def cmd_env(args: argparse.Namespace) -> int:
    provider = provider_for(load_lab(args.lab).lab if args.lab else None)
    env = provider.env()
    if "AWS_ACCESS_KEY_ID" not in env:
        # Keys left in the shell would win over the profile's credential_process.
        print("unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN")
    for key, value in env.items():
        print(f"export {key}={shlex.quote(value)}")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    lab = load_lab(args.lab).lab
    Engine.default().start(args.lab)
    # The lab decides the emulator and region `--profile lab` reaches.
    return _write_profile("labctl start", lab.emulator, lab.region)


def cmd_content(args: argparse.Namespace) -> int:
    from .labs import lab_path
    from .labs.content import import_content

    if not args.file.is_file():
        raise LabError(f"no file {args.file}")
    tabs, problems = import_content(lab_path(args.lab), args.file, fetch=args.fetch_images)
    for problem in problems:
        print(f"labctl content: {problem}", file=sys.stderr)
    print(f"{len(tabs)} tab(s):")
    for tab in tabs:
        print(f"  - {tab.title}")
    return 0


def _print_report(report, quote_lines: list[str] | None) -> None:
    draft = " (draft: lines to review below)" if report.draft else ""
    print(f"{report.lab}: {report.verdict}{draft}")
    for f in report.findings:
        where = f" [line {f.line}, {f.heading}]" if f.line else ""
        print(f"  {f.level:7} {f.code}: {f.text}{where}")
    if report.unrecognised:
        print("lines naming resources the platform may not cover (review, then `--accept [--require LINE] [--optional LINE]`):")
        for u in report.unrecognised:
            text = f": {quote_lines[u['line'] - 1].strip()}" if quote_lines else ""
            print(f"  line {u['line']} [{u['heading']}] {u['term']} ({', '.join(u['services'])}){text}")


def cmd_coverage(args: argparse.Namespace) -> int:
    from .coverage import evaluate

    try:
        return _coverage(args)
    except evaluate.CoverageError as e:  # a lab or input that is not there: a plain error, not a crash
        raise LabError(str(e)) from e


def _coverage(args: argparse.Namespace) -> int:
    from .coverage import evaluate, matrix
    from .labs import lab_path
    from .labs.content import CONTENT_DIR, LAB_MD

    ev = evaluate.Evidence.load()
    warnings = ev.warnings()
    for w in warnings:
        print(f"labctl coverage: warning: {w}", file=sys.stderr)
    if args.strict and warnings:
        return 1
    if args.matrix:
        print(f"{matrix.DOC} {'updated' if matrix.write(ev) else 'unchanged'}")
        if not (args.lab or args.catalog):
            return 0
    if args.catalog:
        summary = evaluate.evaluate_catalog(evaluate.read_catalog(args.catalog), ev)
        if args.json:
            print(json.dumps(summary.as_dict()))
            return 0
        print(f"{summary.total} labs: " + ", ".join(f"{v} {n}" for v, n in summary.by_verdict.items()))
        print("most common reasons (blocked and gap):")
        for text, n in list(summary.reasons.items())[:20]:
            print(f"  {n:4}  {text}")
        print("verdicts come from the catalog's metadata only; a lab's own page can need more.")
        return 0
    if not args.lab:
        raise LabError("name a lab, or pass --catalog CSV or --matrix")
    lab_dir = lab_path(args.lab)
    if args.accept:
        if args.optional:
            from .coverage import extract

            page = lab_dir / CONTENT_DIR / LAB_MD
            commands = {cmd.line for cmd in extract.commands(page.read_text(encoding="utf-8"))} if page.is_file() else set()
            if stray := sorted(set(args.optional) - commands):
                raise LabError(f"--optional names line(s) with no aws command: {', '.join(map(str, stray))}")
        report = evaluate.evaluate_lab(lab_dir, ev, review={})
        path = evaluate.write_review(lab_dir, [u["line"] for u in report.unrecognised], set(args.require),
                                           frozenset(args.optional))
        print(f"reviewed {len(report.unrecognised)} line(s) into {path}")
    report = evaluate.evaluate_lab(lab_dir, ev)
    if args.json:
        print(json.dumps(report.as_dict()))
        return 0
    page = lab_dir / CONTENT_DIR / LAB_MD
    _print_report(report, page.read_text(encoding="utf-8").splitlines() if args.quote and page.is_file() else None)
    return 0


def cmd_credentials(args: argparse.Namespace) -> int:
    """credential_process output. The keys go to the AWS CLI on stdout and nowhere else."""
    from .providers.aws import AwsProvider

    key, secret = AwsProvider(args.emulator).credentials()
    print(json.dumps({"Version": 1, "AccessKeyId": key, "SecretAccessKey": secret}))
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    t0 = time.monotonic()
    Engine.default().reset(args.lab)
    print(f"done in {time.monotonic() - t0:.1f}s")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    attempt, results = Engine.default().check(args.lab)
    passed = all(r.passed or r.info for r in results)  # an info result is shown, not graded
    if args.json:
        print(json.dumps({"lab": args.lab, "attempt": attempt, "passed": passed, "results": [result_dict(r) for r in results]}))
    else:
        for r in results:
            ids = f" [{', '.join(r.resource_ids)}]" if r.resource_ids else ""
            print(f"{'INFO' if r.info else 'PASS' if r.passed else 'FAIL'}  {r.check_id}: {r.message}{ids}")
        graded = [r for r in results if not r.info]
        print(f"{sum(r.passed for r in graded)}/{len(graded)} checks passed")
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
    if not lab_profile_ok(*profile_target()):
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
    "credentials": cmd_credentials,
    "content": cmd_content,
    "coverage": cmd_coverage,
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


if __name__ == "__main__":
    sys.exit(main())
