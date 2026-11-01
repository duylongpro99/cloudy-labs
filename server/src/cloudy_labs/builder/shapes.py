"""Form fields, typed values and the aws argv of an op, generated from its botocore input shape.

The browser and the chat send every value as text; `coerce` turns it into what the shape wants
and says why when it cannot. `argv` prints the request the way the aws CLI takes it: each member
as `--kebab-name`, booleans as `--flag`/`--no-flag`, lists of scalars as separate tokens and
anything structured as JSON (never the CLI's shorthand, whose commas and brackets have meaning).
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, replace
from functools import cache
from typing import Any

import botocore.session
from botocore import xform_name
from botocore.model import OperationModel, Shape
from botocore.validate import ParamValidator

from ..registry import OpField, OpSpec

PROFILE = "lab"  # written by `labctl start` into the learner's AWS config (aws_profile.py)
# The aws CLI's command for a botocore service where the two differ.
CLI_SERVICE = {"s3": "s3api", "codedeploy": "deploy", "config": "configservice"}
# Members a form never offers: the server adds tags itself, and the rest change how a request is
# sent rather than what it does.
HIDDEN = {"DryRun", "ClientToken", "TagSpecifications", "Tags", "tags", "IdempotencyToken"}  # tags: the lab's, added by the server
DOC_MAX = 300


@dataclass(frozen=True)
class Field:
    name: str  # the param name the browser and the chat send; dotted for a nested member
    type: str  # string | enum | boolean | integer | number | list | json | blob
    required: bool = False
    label: str = ""
    doc: str = ""
    choices: tuple[str, ...] | None = None
    source: str | None = None
    ref: str | None = None
    ref_by: str = "id"
    placeholder: str | None = None
    multiline: bool = False
    free: bool = False
    advanced: bool = False
    flag: str | None = None
    sample: str | None = None

    def describe(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "type": self.type, "required": self.required,
                               "label": self.label or self.name}
        for key in ("doc", "choices", "source", "ref", "placeholder"):
            if value := getattr(self, key):
                out[key] = list(value) if key == "choices" else value
        if self.ref:
            out["refBy"] = self.ref_by
        for key in ("multiline", "free", "advanced"):
            if getattr(self, key):
                out[key] = True
        return out


@cache
def _session() -> botocore.session.Session:
    return botocore.session.get_session()


@cache
def operation(service: str, api: str) -> OperationModel:
    """The botocore model of `service`'s `api`. KeyError/OperationNotFound when there is none."""
    return _session().get_service_model(service).operation_model(api)


def cli_command(service: str, api: str) -> list[str]:
    return [CLI_SERVICE.get(service, service), xform_name(api, "-")]


def strip_html(doc: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", doc or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= DOC_MAX else text[: DOC_MAX - 1].rstrip() + "…"


def _type(shape: Shape) -> str:
    match shape.type_name:
        case "string":
            return "enum" if getattr(shape, "enum", None) else "string"
        case "boolean":
            return "boolean"
        case "integer" | "long":
            return "integer"
        case "float" | "double":
            return "number"
        case "list" if shape.member.type_name == "string":
            return "list"
        case "blob":
            return "blob"
        case "timestamp":
            return "string"
    return "json"


def _member(root: Shape, path: str) -> Shape | None:
    shape: Shape | None = root
    for part in path.split("."):
        if shape is None or shape.type_name != "structure":
            return None
        shape = shape.members.get(part)
    return shape


def _field_of(root: Shape, name: str, *, required: bool, advanced: bool = False) -> Field:
    shape = _member(root, name)
    if shape is None:
        raise ValueError(f"{name} is not a member of {root.name}")
    return Field(name, _type(shape), required, label=name, doc=strip_html(shape.documentation),
                 choices=tuple(shape.enum) if getattr(shape, "enum", None) else None, advanced=advanced)


def _required(root: Shape, name: str) -> bool:
    """A dotted member is required when each step on its way is."""
    shape, need = root, True
    for part in name.split("."):
        need = need and part in (shape.required_members or []) and not _is_token(shape.members[part])
        shape = shape.members[part]
    return need


def _is_token(shape: Shape) -> bool:
    """An idempotency token (ClientToken): the aws CLI makes one up when the request has none."""
    return bool(shape.metadata.get("idempotencyToken"))


def fields(spec: OpSpec, service: str) -> list[Field]:
    """The op's form: the fields it lists, then (for a generated op) every other member the
    request may carry, marked advanced. An argv op's fields are its own, not the shape's."""
    out: list[Field] = []
    root = None if spec.argv else operation(service, spec.api).input_shape
    for entry in spec.fields:
        given = OpField(name=entry) if isinstance(entry, str) else entry
        if root is not None:
            base = _field_of(root, given.name, required=_required(root, given.name))
        else:
            base = Field(given.name, given.type or "string", True if given.required is None else given.required,
                         label=given.name)
        out.append(replace(
            base,
            type=given.type or base.type,
            required=base.required if given.required is None else given.required,
            label=given.label or base.label, doc=given.doc or base.doc,
            choices=tuple(spec.choices.get(given.name) or given.choices or base.choices or ()) or None,
            source=given.source, ref=given.ref, ref_by=given.ref_by, placeholder=given.placeholder,
            multiline=given.multiline, free=given.free, flag=given.flag, sample=given.sample,
        ))
    if root is not None:
        listed = {f.name.split(".")[0] for f in out} | set(spec.server_fields) | HIDDEN
        for name, shape in root.members.items():
            if name not in listed and shape.type_name != "blob":
                out.append(_field_of(root, name, required=_required(root, name), advanced=True))
    return out


def coerce(field: Field, text: Any) -> tuple[Any, str | None]:
    """The value `field` takes from the text the browser or the chat sent, or a problem."""
    if not isinstance(text, str):
        return None, "send the value as text"
    value = text.strip()
    match field.type:
        case "boolean":
            if value.lower() in ("true", "false"):
                return value.lower() == "true", None
            return None, "choose true or false"
        case "integer":
            if re.fullmatch(r"-?[0-9]{1,18}", value):
                return int(value), None
            return None, f"{value or '(none)'} is not a whole number"
        case "number":
            try:
                return float(value), None
            except ValueError:
                return None, f"{value or '(none)'} is not a number"
        case "enum":
            if field.choices and value not in field.choices:
                return None, f"{value or '(none)'} is not one of {', '.join(field.choices)}"
            return value, None
        case "list":
            if value.startswith("["):
                try:
                    items = json.loads(value)
                except ValueError:
                    return None, "write the list as a JSON array, or values separated by commas"
                if not (isinstance(items, list) and all(isinstance(i, str) for i in items)):
                    return None, "the list may hold only text values"
                return items, None
            return [t for t in re.split(r"[\s,]+", value) if t], None
        case "json":
            try:
                return json.loads(value), None
            except ValueError as e:
                return None, f"this is not valid JSON ({e.msg} at character {e.pos})"
        case "blob":
            return field.sample, None  # the server's sample, whatever was sent
    return text, None


def _set(target: dict[str, Any], path: str, value: Any) -> None:
    *parents, last = path.split(".")
    for part in parents:
        target = target.setdefault(part, {})
    target[last] = value


def request(spec: OpSpec, service: str, text: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """The API request built from the form's text, and a problem per field that could not be read.
    Empty optional values are left out; the op's defaults fill what the form left empty."""
    by_name = {f.name: f for f in fields(spec, service)}
    params: dict[str, Any] = {}
    problems: dict[str, str] = {}
    defaults = {k: v if isinstance(v, str) else json.dumps(v) if isinstance(v, (dict, list, bool)) else str(v)
                for k, v in spec.defaults.items()}
    sent = {k: v for k, v in text.items() if not (k in defaults and isinstance(v, str) and not v.strip())}
    for name, raw in {**defaults, **sent}.items():
        f = by_name.get(name)
        if f is None:
            problems[name] = f"{spec.id} has no field {name}"
            continue
        if f.type != "blob" and isinstance(raw, str) and not raw.strip():
            continue
        value, problem = coerce(f, raw)
        if problem:
            problems[name] = problem
        else:
            _set(params, name, value)
    for f in by_name.values():
        if f.type == "blob" and f.sample:  # always the server's sample, sent or not
            _set(params, f.name, f.sample)
    return params, problems


def shape_problems(service: str, api: str, params: dict[str, Any]) -> list[str]:
    """What botocore's own validation says about the request: missing members, wrong types, ranges."""
    shape = operation(service, api).input_shape
    # Blobs are sample ids here; botocore wants bytes, which the CLI reads from the sample file.
    probe = _blobs_as_bytes(shape, params)
    probe |= {k: "t" * max(m.metadata.get("min", 1), 32) for k, m in shape.members.items() if _is_token(m) and k not in probe}
    report = ParamValidator().validate(probe, shape)
    if not report.has_errors():
        return []
    return [line.strip() for line in report.generate_report().splitlines() if line.strip()]


def _blobs_as_bytes(shape: Shape, value: Any) -> Any:
    if shape.type_name == "blob":
        return b"sample"
    if shape.type_name == "structure" and isinstance(value, dict):
        return {k: _blobs_as_bytes(shape.members[k], v) if k in shape.members else v for k, v in value.items()}
    if shape.type_name == "list" and isinstance(value, list):
        return [_blobs_as_bytes(shape.member, v) for v in value]
    return value


def _has_values(value: Any) -> bool:
    return any(_has_values(v) for v in value.values()) if isinstance(value, dict) else True


# Booleans the aws CLI spells as two words of its own instead of --flag/--no-flag:
# (service, API, member) -> (flag when true, flag when false).
CLI_BOOLEAN_PAIRS = {
    ("ec2", "CreateNetworkAclEntry", "Egress"): ("--egress", "--ingress"),
    ("ec2", "ReplaceNetworkAclEntry", "Egress"): ("--egress", "--ingress"),
    ("ec2", "DeleteNetworkAclEntry", "Egress"): ("--egress", "--ingress"),
}
# Members the aws CLI offers under another flag (awscli customizations/argrename.py), because their
# own name is a global option: `--endpoint` would be read as `--endpoint-url`, and `--version` prints
# the CLI's version and exits 0 without sending the request.
CLI_RENAMES = {
    ("sns", "Subscribe", "Endpoint"): "--notification-endpoint",
    ("eks", "CreateCluster", "version"): "--kubernetes-version",
    ("eks", "CreateNodegroup", "version"): "--kubernetes-version",
    ("eks", "UpdateNodegroupVersion", "version"): "--kubernetes-version",
    ("apigateway", "CreateRestApi", "version"): "--api-version",
    ("apigatewayv2", "CreateApi", "Version"): "--api-version",
    ("apigatewayv2", "UpdateApi", "Version"): "--api-version",
}
# The aws CLI's global options: no generated member flag may be one of them.
CLI_GLOBAL_OPTIONS = frozenset({
    "--debug", "--endpoint-url", "--no-verify-ssl", "--no-paginate", "--output", "--query", "--profile", "--region",
    "--version", "--color", "--no-sign-request", "--ca-bundle", "--cli-read-timeout", "--cli-connect-timeout",
    "--cli-binary-format", "--no-cli-pager", "--cli-auto-prompt", "--no-cli-auto-prompt", "--cli-input-json",
    "--cli-input-yaml", "--generate-cli-skeleton",
})


def argv(spec: OpSpec, service: str, params: dict[str, Any], blob_paths: dict[str, str]) -> list[str]:
    """The aws argv of the request. `blob_paths`: the local file of each blob field's sample."""
    shape = operation(service, spec.api).input_shape
    blob_fields = [f for f in fields(spec, service) if f.type == "blob"]
    out = ["aws", *cli_command(service, spec.api)]
    params = json.loads(json.dumps(params))  # a copy whose blob members can be removed
    for f in blob_fields:
        top, *rest = f.name.split(".")
        if top not in params:
            continue
        if f.flag is None:
            raise ValueError(f"{spec.id}: blob field {f.name} needs a flag")
        out += [f.flag, f"fileb://{blob_paths[f.name]}"]
        if not rest:
            del params[top]
            continue
        holder = params[top]
        for part in rest[:-1]:
            holder = holder[part]
        holder.pop(rest[-1], None)
        if not _has_values(params[top]):
            del params[top]
    for name, member in shape.members.items():
        if name not in params:
            continue
        value, flag = params[name], CLI_RENAMES.get((service, spec.api, name)) or "--" + xform_name(name, "-")
        if flag in CLI_GLOBAL_OPTIONS:
            raise ValueError(f"{spec.id}: member {name} would be sent as the global option {flag}")
        if member.type_name == "boolean":
            out.append((CLI_BOOLEAN_PAIRS.get((service, spec.api, name)) or (flag, "--no-" + flag[2:]))[0 if value else 1])
        elif member.type_name == "list" and member.member.type_name in ("string", "integer", "long"):
            out += [flag, *(str(v) for v in value)]
        elif member.type_name in ("structure", "list", "map"):
            out += [flag, json.dumps(value, separators=(",", ":"))]
        else:
            out += [flag, str(value)]
    return out + ["--profile", PROFILE, "--output", "json"]
