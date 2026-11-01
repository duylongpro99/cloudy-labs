"""What a lab page asks of the platform: the `aws` commands it runs and the AWS resources it names.

The page is the learner's local copy of a labaws.site lab (`content/lab.md`, never committed). What
comes out of here holds only service and API names, the heading a line sits under and its line
number; never the page's own text, so it may be printed, stored and committed.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from functools import cache

import botocore.session
from botocore import xform_name
from botocore.exceptions import DataNotFoundError

from ..registry import Registry

FENCE = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
INLINE_CODE = re.compile(r"`([^`\n]+)`")
# Options of `aws` itself that take a value, read before the service name.
GLOBAL_OPTS = {"--region", "--profile", "--output", "--endpoint-url", "--query", "--color", "--cli-read-timeout",
               "--cli-connect-timeout", "--ca-bundle", "--cli-binary-format"}
# The aws CLI's command names that are not the botocore service name.
CLI_SERVICE = {"s3api": "s3", "deploy": "codedeploy", "configservice": "config", "s3control": "s3control"}
# `aws s3 <cmd>`: high-level commands and the API calls they make.
S3_HIGH_LEVEL = {"mb": ("CreateBucket",), "rb": ("DeleteBucket",), "ls": ("ListObjectsV2",),
                 "cp": ("PutObject", "GetObject"), "mv": ("PutObject", "GetObject", "DeleteObject"),
                 "rm": ("DeleteObject",), "sync": ("ListObjectsV2", "PutObject"), "presign": ("GetObject",),
                 "website": ("PutBucketWebsite",)}
# CLI commands that are not API calls.
LOCAL = {"configure", "help", "history", "cli"}
# Subcommands the CLI handles itself (`aws sso login` caches a token, `aws rds generate-db-auth-token`
# signs one locally) though the service has APIs.
LOCAL_OPS = {("sso", "login"), ("sso", "logout"), ("rds", "generate-db-auth-token"), ("eks", "get-token")}
# CLI commands botocore has no operation for, built on other APIs: (CLI word, command) -> the
# botocore service and the APIs they call.
CLI_CUSTOM = {
    ("cloudformation", "deploy"): ("cloudformation", ("CreateChangeSet", "ExecuteChangeSet")),
    ("cloudformation", "package"): ("s3", ("PutObject",)),
    ("codeartifact", "login"): ("codeartifact", ("GetAuthorizationToken", "GetRepositoryEndpoint")),
    ("configservice", "get-status"): ("config", ("DescribeConfigurationRecorderStatus", "DescribeDeliveryChannelStatus")),
    ("configservice", "subscribe"): ("config", ("PutConfigurationRecorder", "PutDeliveryChannel", "StartConfigurationRecorder")),
    ("deploy", "push"): ("codedeploy", ("RegisterApplicationRevision",)),
    ("ecr", "get-login-password"): ("ecr", ("GetAuthorizationToken",)),
    ("eks", "update-kubeconfig"): ("eks", ("DescribeCluster",)),
    ("logs", "tail"): ("logs", ("FilterLogEvents",)),
}
# The noun of a creating API: CreateDBSubnetGroup -> "DB Subnet Group".
CREATE = re.compile(r"^(Create|Run|Allocate|Register|Put|Import|Start)([A-Z].*)$")
WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+")


@dataclass(frozen=True)
class Command:
    service: str  # botocore service name (or the CLI's word when botocore has no such service)
    apis: tuple[str, ...]  # botocore operation names; empty when the command is not one botocore knows
    cli: str  # "ec2 create-vpc", the command as typed (service and operation words only)
    flags: tuple[tuple[str, str], ...]  # (option, value) pairs; values may be shell variables
    line: int
    heading: str


@dataclass(frozen=True)
class Mention:
    term: str  # the dictionary term found, e.g. "Target Group"
    kinds: tuple[str, ...]  # registry kinds the term names; empty when only botocore knows it
    services: tuple[str, ...]  # botocore services with a resource of that name
    line: int
    heading: str
    weak: bool = False  # a common word: names one of `kinds` only where the page names its service

    @property
    def certain(self) -> bool:
        return bool(self.kinds)


@cache
def _session() -> botocore.session.Session:
    return botocore.session.get_session()


@cache
def services() -> frozenset[str]:
    return frozenset(_session().get_available_services())


@cache
def cli_operations(service: str) -> dict[str, str]:
    """`create-db-instance` -> `CreateDBInstance` for one botocore service."""
    model = _session().get_service_model(service)
    return {xform_name(op, "-"): op for op in model.operation_names}


@cache
def cli_waiters(service: str) -> dict[str, str]:
    """`db-instance-deleted` -> `DescribeDBInstances`: the API a CLI `wait` subcommand polls."""
    try:
        model = _session().get_waiter_model(service)
    except DataNotFoundError:  # a service without waiters
        return {}
    return {xform_name(name, "-"): model.get_waiter(name).operation for name in model.waiter_names}


def words(name: str) -> str:
    return " ".join(WORD.findall(name))


def _lines(text: str) -> list[tuple[int, str, bool, str]]:
    """(line number, text, inside a code fence, heading) for every line of the page."""
    out = []
    heading = ""
    fenced = False
    for n, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced and (m := HEADING.match(line)):
            heading = m.group(2)
            continue
        out.append((n, line, fenced, heading))
    return out


def _logical(text: str) -> list[tuple[int, str, str]]:
    """Shell text with `\\` continuations joined: (first line number, joined text, heading). Code
    fences give every line; prose gives its inline code spans that start with `aws`."""
    out: list[tuple[int, str, str]] = []
    pending: tuple[int, str, str] | None = None
    for n, line, fenced, heading in _lines(text):
        if fenced:
            if pending:
                start, acc, h = pending
                acc += " " + line.strip()
            else:
                start, acc, h = n, line.strip(), heading
            if acc.endswith("\\"):
                pending = (start, acc[:-1].rstrip(), h)
                continue
            pending = None
            out.append((start, acc, h))
        else:
            if pending:
                out.append(pending)
                pending = None
            out.extend((n, span, heading) for span in INLINE_CODE.findall(line) if "aws " in span)
    if pending:
        out.append(pending)
    return out


def _tokens(shell: str) -> list[str]:
    try:
        lexer = shlex.shlex(shell, posix=True, punctuation_chars="|&;()")
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:  # an unclosed quote: split on spaces
        return shell.split()


def _command(tokens: list[str], i: int, line: int, heading: str) -> Command | None:
    """The `aws` command starting at tokens[i] (the `aws` word)."""
    j = i + 1
    while j < len(tokens) and tokens[j].startswith("--"):
        j += 2 if tokens[j] in GLOBAL_OPTS else 1
    if j >= len(tokens) or not re.fullmatch(r"[a-z0-9-]+", tokens[j]):
        return None
    word = tokens[j]
    if word in LOCAL:
        return None
    op = tokens[j + 1] if j + 1 < len(tokens) and re.fullmatch(r"[a-z0-9-]+", tokens[j + 1]) else ""
    if (word, op) in LOCAL_OPS:
        return None
    flags: list[tuple[str, str]] = []
    k = j + 2
    while k < len(tokens) and tokens[k] not in ("|", "||", "&&", ";", ")", "&"):
        tok = tokens[k]
        if tok.startswith("--"):
            name, eq, value = tok.partition("=")
            if not eq and k + 1 < len(tokens) and not tokens[k + 1].startswith("--"):
                value = tokens[k + 1]
                k += 1
            flags.append((name, value))
        k += 1
    if word == "s3":
        return Command("s3", S3_HIGH_LEVEL.get(op, ()), f"s3 {op}".strip(), tuple(flags), line, heading)
    if (word, op) in CLI_CUSTOM:
        service, apis = CLI_CUSTOM[word, op]
        return Command(service, apis, f"{word} {op}", tuple(flags), line, heading)
    service = CLI_SERVICE.get(word, word)
    apis: tuple[str, ...] = ()
    if service in services() and op == "wait":
        # `aws rds wait db-instance-deleted` polls a describe API until a state is reached.
        waiter = tokens[j + 2] if j + 2 < len(tokens) else ""
        api = cli_waiters(service).get(waiter)
        return Command(service, (api,) if api else (), f"{word} wait {waiter}".strip(), tuple(flags), line, heading)
    if service in services() and op:
        api = cli_operations(service).get(op)
        apis = (api,) if api else ()
    return Command(service, apis, f"{word} {op}".strip(), tuple(flags), line, heading)


def commands(text: str) -> list[Command]:
    """Every `aws` command of the page: in code blocks (continued lines joined, after a pipe, `&&`,
    `$(` or a variable assignment) and in inline code."""
    out: list[Command] = []
    for line, shell, heading in _logical(text):
        if "aws" not in shell:
            continue
        tokens = _tokens(shell)
        for i, tok in enumerate(tokens):
            if tok == "aws" or tok.endswith("/aws") or tok.endswith("=aws") or tok == "$(aws":
                if (cmd := _command(tokens, i, line, heading)) is not None:
                    out.append(cmd)
    return out


@dataclass(frozen=True)
class Term:
    text: str
    pattern: re.Pattern[str]
    kinds: tuple[str, ...]
    services: tuple[str, ...]
    weak: bool = False  # one common word ("key", "api"): counts only where the page names its service


def _term(text: str, kinds: set[str], svcs: set[str], weak: bool = False) -> Term:
    # A kind's name may have one English word inside it ("Config Managed Rule" is a Config Rule).
    sep = r"[\s-]+(?:[A-Za-z0-9]+[\s-]+)?" if kinds else r"[\s-]+"
    pattern = re.compile(r"(?<![\w-])" + sep.join(map(re.escape, text.split())) + r"(?![\w-])", re.I)
    return Term(text, pattern, tuple(sorted(kinds)), tuple(sorted(svcs)), weak)


@cache
def _botocore_nouns() -> dict[str, set[str]]:
    """Resource names of botocore's creating APIs with at least two words, lowercased -> services."""
    out: dict[str, set[str]] = {}
    for service in services():
        for op in _session().get_service_model(service).operation_names:
            if (m := CREATE.match(op)) and m.group(1) == "Create":
                noun = words(m.group(2))
                if len(noun.split()) >= 2:
                    out.setdefault(noun.lower(), set()).add(service)
    return out


def dictionary(registry: Registry) -> list[Term]:
    """Resource names to look for: each registry kind's label and the nouns of its API actions
    (certain: they name a kind), then botocore's resource names (a service, but no kind yet).
    Longer terms first, so "DB Subnet Group" wins over "Subnet". A one-word action noun that is no
    kind's label ("Key", "Application") is weak: see `Mention.weak`."""
    by_text: dict[str, tuple[set[str], set[str]]] = {}
    labels = {t.label.lower() for t in registry.types if not t.structural}
    for t in registry.types:
        if t.structural:
            continue
        names = {t.label, *(words(a) for a in t.view.actions)}
        for name in names:
            kinds, svcs = by_text.setdefault(name.lower(), (set(), set()))
            kinds.add(t.kind)
            svcs.add(t.service)
    for noun, svcs in _botocore_nouns().items():
        by_text.setdefault(noun, (set(), set()))[1].update(svcs)
    terms = [_term(text, kinds, svcs, weak=bool(kinds) and " " not in text and text not in labels)
             for text, (kinds, svcs) in by_text.items()]
    return sorted(terms, key=lambda t: (-len(t.text), t.text))


def mentions(text: str, terms: list[Term]) -> list[Mention]:
    """Resource names in the page's prose (not its code blocks), one per term and line; a longer
    term hides the shorter ones it contains on that line."""
    out: list[Mention] = []
    for n, line, fenced, heading in _lines(text):
        if fenced:
            continue
        taken: list[tuple[int, int]] = []
        for term in terms:
            for m in term.pattern.finditer(line):
                if any(a <= m.start() < b or a < m.end() <= b for a, b in taken):
                    continue
                taken.append(m.span())
                out.append(Mention(term.text, term.kinds, term.services, n, heading, term.weak))
                break
    return out


@cache
def _service_names(service: str) -> tuple[re.Pattern[str], ...]:
    """How a page names a service: "Amazon SQS", "SQS", "AWS Config", "Elastic Beanstalk". A bare
    name counts only when it cannot be a plain word: several words, or a capital or digit inside
    ("CloudWatch", "EC2"); "Config" or "Lambda" alone need their "AWS"/"Amazon"."""
    meta = _session().get_service_model(service).metadata
    out = []
    for full in filter(None, {meta.get("serviceFullName"), meta.get("serviceAbbreviation")}):
        name = re.sub(r"^(Amazon|AWS)\s*", "", full).strip()
        if not name:
            continue
        body = r"[\s-]+".join(map(re.escape, name.split()))
        out.append(re.compile(r"(?<![\w-])(?:Amazon|AWS)[\s-]+" + body + r"(?![\w-])", re.I))
        if " " in name or re.search(r"[A-Z0-9]", name[1:]):
            out.append(re.compile(r"(?<![\w-])" + body + r"(?![\w-])"))
    return tuple(out)


def named_services(text: str, candidates: set[str]) -> set[str]:
    """The services of `candidates` the page's prose names."""
    prose = "\n".join(line for _, line, fenced, _ in _lines(text) if not fenced)
    return {s for s in candidates if s in services() and any(p.search(prose) for p in _service_names(s))}


# Verbs whose APIs make, read or change a resource a kind already stands for.
COMMON_VERBS = {"Create", "Delete", "Describe", "List", "Get", "Update", "Put", "Modify", "Tag", "Untag", "Batch"}
# The console's word for an API's verb: "Launch instance" calls RunInstances.
CONSOLE_VERBS = {"Launch": "Run"}


@dataclass(frozen=True)
class Action:
    service: str
    api: str  # an API Floci lacks
    line: int
    heading: str


def actions(text: str, service: str, apis: list[str], emulated: list[str]) -> list[Action]:
    """Console steps that may call one of `apis`: its verb, then its last noun within four words, on
    a prose line ("Flush entire cache" for FlushStageCache); an API of four words or more needs them
    all. When an API in `emulated` shares the verb and noun, a line with the words that set it apart
    means that one ("attach the internet gateway" is AttachInternetGateway, not AttachVpnGateway).
    A guess for review, never a finding."""
    siblings: dict[tuple[str, str], list[list[str]]] = {}
    for p in map(WORD.findall, emulated):
        if len(p) >= 2:
            siblings.setdefault((p[0], p[-1]), []).append(p[1:-1])
    gap = r"(?:\W+[A-Za-z0-9]+){0,3}?\W+"
    phrases = []
    for api in apis:
        parts = WORD.findall(api)
        if len(parts) < 2 or parts[0] in COMMON_VERBS or parts[-1] in ("Tag", "Tags"):
            continue
        needed = parts if len(parts) >= 4 else [parts[0], parts[-1]]
        body = rf"\w*{gap}".join(map(re.escape, needed))
        verb = CONSOLE_VERBS.get(parts[0], parts[0])
        others = [[w.lower() for w in mid if w not in parts] for mid in siblings.get((verb, parts[-1]), [])]
        phrases.append((api, re.compile(rf"(?<![\w-]){body}s?(?![\w-])", re.I), others))
    out = []
    for n, line, fenced, heading in _lines(text):
        if fenced:
            continue
        low = set(re.findall(r"[a-z0-9]+", line.lower()))
        out.extend(Action(service, api, n, heading) for api, p, others in phrases
                   if p.search(line) and not any(o and set(o) <= low for o in others) and not any(not o for o in others))
    return out


def checker_services(sources: list[str]) -> set[str]:
    """Services a lab's checks call: `client("rds")` and `.client('ec2', ...)`, read without running."""
    found: set[str] = set()
    for src in sources:
        found.update(re.findall(r"client\(\s*[\"']([a-z0-9-]+)[\"']", src))
    return found
