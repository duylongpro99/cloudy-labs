"""Turn the model's answer into builder steps the learner can trust (PRD F5.1–F5.3, F5.6).

The model returns JSON naming ops and params. Each step is checked here exactly as a builder
request would be: the op must be in the lab's palette, the params must fit the op, and the
command is built and checked by the builder's `prepare`. A step that fails keeps its problems
and is still shown, never dropped, so the learner sees what the model got wrong. Nothing runs.
"""

import re
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from ..builder.catalog import BuilderOp, OpError, op_named, practice_expectation, prepare, server_field_problem
from ..builder.ec2_choices import Choices
from ..builder.sanitize import Problem
from ..graph.schema import Node, ResourceGraph
from ..labs.schema import Lab
from . import provider
from .prompt import system_prompt
from .provider import Message
from .settings import LlmSettings

FORMAT_FAILED = "Model không trả về đúng định dạng; thử hỏi lại hoặc đổi model"
RAW_ECHO_MAX = 2000  # how much of a malformed answer is sent back with the request to fix it
FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

Complete = Callable[[LlmSettings, str, list[Message]], Awaitable[str]]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Ref(_Strict):
    ref: int  # the 1-based number of an earlier create step whose new resource id goes here


class RawStep(_Strict):
    op: str
    params: dict[str, str | Ref] = {}
    explanation: str = ""

    @field_validator("params", mode="before")
    @classmethod
    def _numbers_as_text(cls, v: Any) -> Any:
        """Models often write a port as 80, true for a flag, or null for "none"; every op param is
        text, "" meaning none."""
        if isinstance(v, dict):
            return {k: _as_text(x) for k, x in v.items()}
        return v


def _as_text(x: Any) -> Any:
    if x is None:
        return ""
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int | float):
        return str(x)
    return x


def _ref_fields(op: BuilderOp) -> set[str]:
    """Params that take a resource id, which an earlier step's new resource may fill."""
    if op.legacy:
        return {f.alias or n for n, f in op.legacy.params.model_fields.items() if (f.alias or n).endswith("Id")}
    return {f.name for f in op.fields() if f.ref and f.ref_by == "id"}


class Reply(BaseModel):
    reply: str = ""
    refusal: str | None = None
    steps: list[RawStep] = []


@dataclass
class Step:
    op: str
    params: dict[str, Any]  # as the model gave them, refs kept as {"ref": n} for the browser to fill in
    explanation: str
    command: str = ""  # empty when no command can be built
    problems: list[Problem] = field(default_factory=list)
    deferred: bool = False  # uses an id an earlier step makes: checked against the graph when it runs
    refs: list[int] = field(default_factory=list)
    practice_expect: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"op": self.op, "params": self.params, "explanation": self.explanation, "command": self.command,
                "problems": [asdict(p) for p in self.problems], "deferred": self.deferred, "refs": self.refs,
                "practiceExpect": self.practice_expect}


@dataclass
class Suggestion:
    reply: str
    refusal: str | None = None
    steps: list[Step] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"reply": self.reply, "refusal": self.refusal, "steps": [s.to_dict() for s in self.steps]}


def placeholder(n: int) -> str:
    return f"<id từ bước {n}>"


def parse_reply(text: str) -> Reply:
    """The JSON object in the model's text, tolerating a ```json fence or words around it."""
    body = text.strip()
    if fenced := FENCE.search(body):
        body = fenced.group(1).strip()
    if not body.startswith("{") and "{" in body:
        body = body[body.index("{"): body.rindex("}") + 1]
    return Reply.model_validate_json(body)


def _short_error(e: ValidationError | ValueError) -> str:
    if isinstance(e, ValidationError):
        return "; ".join(f"{'.'.join(map(str, err['loc'])) or 'reply'}: {err['msg']}" for err in e.errors()[:5])
    return str(e)[:300]


def _ahead(graph: ResourceGraph, earlier: list[RawStep]) -> ResourceGraph:
    """The scene as a step will find it: what earlier create steps make by name (an Aurora cluster
    its member instance names) is there too. Only registry ops: the hand-written ones check props."""
    made = []
    for n, raw in enumerate(earlier, start=1):
        op = op_named(raw.op)
        if op is None or op.legacy or op.gesture != "create" or not op.spec.expect:
            continue
        if isinstance(name := raw.params.get(op.spec.expect.label), str):
            made.append(Node(id=f"step-{n}", kind=op.spec.expect.kind or op.creates or op.kind, label=name))
    return graph.model_copy(update={"nodes": [*graph.nodes, *made]}) if made else graph


def check_step(n: int, raw: RawStep, earlier: list[RawStep], lab: Lab, graph: ResourceGraph,
               azs: list[str], choices: Choices) -> Step:
    """Step `n` (1-based), given the steps before it."""
    params_out = {k: v.model_dump() if isinstance(v, Ref) else v for k, v in raw.params.items()}
    step = Step(raw.op, params_out, raw.explanation)
    op = op_named(raw.op)
    if op is None:
        step.problems.append(Problem("", f"{raw.op} is not a builder op; this answer cannot be run"))
        return step
    if op.palette_kind() not in lab.builder.palette:
        step.problems.append(Problem("", f"{lab.id} does not offer {op.name} in its builder"))
    server_fields = set(server_field_problem(op, raw.params))
    for name in sorted(server_fields):
        step.problems.append(Problem(name, "the server fills this in from the scene"))

    ref_fields = _ref_fields(op)
    values: dict[str, str] = {}
    for name, value in raw.params.items():
        if name in server_fields:
            continue
        if isinstance(value, str):
            values[name] = value
            continue
        target = earlier[value.ref - 1] if 1 <= value.ref < n else None
        if name not in ref_fields:
            step.problems.append(Problem(name, "takes a name, not an id; write the name instead of a ref"))
        elif target is None:
            step.problems.append(Problem(name, f"refers to step {value.ref}, but a step can only use an earlier step"))
        elif (made := op_named(target.op)) is None or made.gesture != "create":
            step.problems.append(Problem(name, f"refers to step {value.ref}, which creates nothing to take an id from"))
        else:
            step.refs.append(value.ref)
        values[name] = placeholder(value.ref)
    step.refs = sorted(set(step.refs))

    if op.legacy:
        try:
            op.legacy.params.model_validate(values)
        except ValidationError as e:
            explain = {"missing": "this parameter is missing", "extra_forbidden": f"not a parameter of {op.name}"}
            for err in e.errors():
                step.problems.append(Problem(".".join(map(str, err["loc"])), explain.get(err["type"], err["msg"])))
            return step
    step.deferred = any(isinstance(v, Ref) for v in raw.params.values())
    try:
        prepared = prepare(op, values, graph=graph if op.legacy else _ahead(graph, earlier), azs=azs, choices=choices, tags=lab.builder.tags,
                           check=not step.deferred)
    except OpError as e:
        step.problems.append(Problem("", str(e)))
        return step
    step.command = prepared.command
    step.practice_expect = practice_expectation(prepared)
    step.problems += prepared.problems
    return step


async def suggest(messages: list[Message], *, lab: Lab, graph: ResourceGraph, azs: list[str], choices: Choices,
                  settings: LlmSettings, complete: Complete = provider.complete) -> Suggestion:
    """Ask the model, parse its answer (asking once more if it is malformed), and check every step.
    Raises ProviderError when the provider cannot be reached."""
    system = system_prompt(lab, graph, azs, choices)
    text = await complete(settings, system, messages)
    try:
        reply = parse_reply(text)
    except (ValidationError, ValueError) as e:
        retry: list[Message] = [
            *messages,
            {"role": "assistant", "content": text[:RAW_ECHO_MAX]},
            {"role": "user", "content": f"That answer was not the JSON object asked for ({_short_error(e)}). "
                                        "Answer the same request again with only that JSON object."},
        ]
        try:
            reply = parse_reply(await complete(settings, system, retry))
        except (ValidationError, ValueError):
            return Suggestion(reply=FORMAT_FAILED)
    steps: list[Step] = []
    for n, raw in enumerate([] if reply.refusal else reply.steps, start=1):
        steps.append(check_step(n, raw, reply.steps[: n - 1], lab, graph, azs, choices))
    return Suggestion(reply=reply.reply, refusal=reply.refusal or None, steps=steps)
