"""The first check on every op's params, before any shape or graph check.

The aws CLI reads a value starting with `file://` or `fileb://` from that file, whatever the
parameter, so a learner (or the chat model) could read any file on the host into a request. A
list element starting with `-` would be taken as the next flag. Name and description values go
into tags and the CLI's own parsing, so they keep to AWS's safe characters.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

# A value with one of these prefixes is replaced by the CLI with a file's contents.
FILE_PREFIX = re.compile(r"^\s*fileb?://", re.IGNORECASE)
NAME = re.compile(r"[A-Za-z0-9._-]{1,64}")  # used with fullmatch: `$` would let a trailing newline in
DESCRIPTION_MAX = 255
# The characters AWS accepts in a security group description (VPC groups).
DESCRIPTION = re.compile(rf"[A-Za-z0-9 ._\-:/()#,@\[\]+=&;{{}}!$*]{{1,{DESCRIPTION_MAX}}}")
# Name fields whose AWS names are paths, by service: a log group is commonly /aws/lambda/<function>,
# a parameter /app/db-host, an alias alias/<name>, a secret app/db-password.
PATH_NAMES = {
    ("logs", "logGroupName"): re.compile(r"[A-Za-z0-9._/#-]{1,512}"),
    ("ssm", "Name"): re.compile(r"[A-Za-z0-9._/-]{1,1011}"),
    ("kms", "AliasName"): re.compile(r"alias/[A-Za-z0-9._/-]{1,250}"),
    ("secretsmanager", "Name"): re.compile(r"[A-Za-z0-9._/+=@-]{1,512}"),
}
# Name fields whose AWS values are not names, by service, with the hint for a bad value: a Beanstalk
# solution stack is a platform title with spaces, an ACM certificate may be a wildcard (*.example.com).
# The first character is never '-', so the CLI cannot read the value as an option.
OTHER_NAMES = {
    ("elasticbeanstalk", "SolutionStackName"): (
        re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._()-]{0,199}"),
        "use the platform title as AWS lists it (for example 64bit Amazon Linux 2023 v4.3.0 running Docker)"),
    ("acm", "DomainName"): (
        re.compile(r"(?:\*\.)?[A-Za-z0-9][A-Za-z0-9.-]{0,252}"),
        "use a domain name, optionally starting with *. (for example *.example.com)"),
}
# Name-like fields that hold a comma-separated list of ids, not a name.
ID_LISTS = {"VPCZoneIdentifier": re.compile(r"subnet-[0-9a-f]{8,17}(?:,subnet-[0-9a-f]{8,17})*")}
NAME_FIELDS = re.compile(r"(?:^|[a-z])(?:Name|Identifier)$|^name$")
DESCRIPTION_FIELDS = re.compile(r"(?:^|[a-z])Description$|^description$|^Description$")


@dataclass(frozen=True)
class Problem:
    field: str  # the param it is about, as the form names it; "" for the op as a whole
    message: str


def is_name_field(field: str) -> bool:
    return bool(NAME_FIELDS.search(field))


def is_description_field(field: str) -> bool:
    return bool(DESCRIPTION_FIELDS.search(field))


def _json_text(value: str) -> Any:
    """The value parsed when it is JSON text for a list or structure, else None."""
    if value.lstrip()[:1] not in ("[", "{"):
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None


def _walk_files(field: str, value: Any, problems: list[Problem]) -> None:
    if isinstance(value, str):
        _walk(field, value, problems, False)
    elif isinstance(value, dict):
        for k, v in value.items():
            _walk_files(field, k, problems)
            _walk_files(field, v, problems)
    elif isinstance(value, list):
        for v in value:
            _walk_files(field, v, problems)


def _walk(field: str, value: Any, problems: list[Problem], in_list: bool) -> None:
    if isinstance(value, str):
        if FILE_PREFIX.match(value):
            problems.append(Problem(field, "a value may not start with file:// or fileb://: the aws CLI would read "
                                           "that file from this machine instead of using the text"))
        elif in_list and value.startswith("-"):
            problems.append(Problem(field, "a list value may not start with '-': the aws CLI would read it as another option"))
        elif (parsed := _json_text(value)) is not None:
            # The form sends structures as JSON text, parsed after this check: the CLI reads a file
            # for a string at any depth. The text stays one CLI argument, so '-' is harmless inside.
            _walk_files(field, parsed, problems)
    elif isinstance(value, dict):
        for k, v in value.items():
            _walk(field, k, problems, False)
            _walk(field, v, problems, False)
    elif isinstance(value, list):
        for v in value:
            _walk(field, v, problems, True)


def sanitize(params: dict[str, Any], *, list_fields: frozenset[str] = frozenset(), service: str = "") -> list[Problem]:
    """Problems with the raw params, one per field at most. `list_fields` are the fields whose
    text becomes separate CLI tokens, so their elements are checked for a leading '-'. `service`
    (the op's aws CLI service) picks the name rules of fields whose names are paths."""
    problems: list[Problem] = []
    for field, value in params.items():
        found: list[Problem] = []
        if isinstance(value, str) and field in list_fields:
            # Text the form turns into separate CLI tokens: a JSON array's elements, else the words.
            parsed = _json_text(value)
            tokens = parsed if isinstance(parsed, list) else [t for t in re.split(r"[\s,]+", value.strip()) if t]
            _walk(field, tokens, found, True)
        _walk(field, value, found, False)
        if not found and isinstance(value, str) and value:
            if other := OTHER_NAMES.get((service, field)):
                if not other[0].fullmatch(value):
                    found.append(Problem(field, other[1]))
            elif path := PATH_NAMES.get((service, field)):
                if not path.fullmatch(value):
                    found.append(Problem(field, "use letters, digits and . _ - / (for example /aws/lambda/my-fn, "
                                                "/app/db-host or alias/my-key)"))
            elif field in ID_LISTS:
                if not ID_LISTS[field].fullmatch(value.replace(" ", "")):
                    found.append(Problem(field, "give subnet ids separated by commas (for example subnet-0a1b2c3d,subnet-4e5f6a7b)"))
            elif is_name_field(field) and not NAME.fullmatch(value):
                found.append(Problem(field, "give it a Name tag of 1–64 letters, digits, dots, dashes or underscores "
                                                 "(for example lab06-vpc), so you can tell resources apart"))
            elif is_description_field(field) and not DESCRIPTION.fullmatch(value):
                found.append(Problem(field, f"use up to {DESCRIPTION_MAX} letters, digits, spaces and ._-:/()#,@[]+=&;{{}}!$* "
                                                        "(no accents or emoji)"))
        if found:
            problems.append(found[0])
    return problems
