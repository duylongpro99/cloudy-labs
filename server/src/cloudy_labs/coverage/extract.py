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
    service = CLI_SERVICE.get(word, word)
    apis: tuple[str, ...] = ()
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


def _term(text: str, kinds: set[str], svcs: set[str]) -> Term:
    pattern = re.compile(r"(?<![\w-])" + r"[\s-]+".join(map(re.escape, text.split())) + r"(?![\w-])", re.I)
    return Term(text, pattern, tuple(sorted(kinds)), tuple(sorted(svcs)))


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
    Longer terms first, so "DB Subnet Group" wins over "Subnet"."""
    by_text: dict[str, tuple[set[str], set[str]]] = {}
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
    terms = [_term(text, kinds, svcs) for text, (kinds, svcs) in by_text.items()]
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
                out.append(Mention(term.text, term.kinds, term.services, n, heading))
                break
    return out


def checker_services(sources: list[str]) -> set[str]:
    """Services a lab's checks call: `client("rds")` and `.client('ec2', ...)`, read without running."""
    found: set[str] = set()
    for src in sources:
        found.update(re.findall(r"client\(\s*[\"']([a-z0-9-]+)[\"']", src))
    return found
