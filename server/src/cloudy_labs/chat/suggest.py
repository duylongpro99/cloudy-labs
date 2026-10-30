"""Turn the model's answer into builder steps the learner can trust (PRD F5.1–F5.3, F5.6).

The model returns JSON naming ops and params. Each step is checked here exactly as a builder
request would be: the op must be in the lab's palette, the params must fit the op, and the
command is built by `Op.argv` and checked by `validate()`. A step that fails keeps its problems
and is still shown, never dropped, so the learner sees what the model got wrong. Nothing runs.
"""

import re
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from ..builder.ec2_choices import Choices
from ..builder.ops import OPS, ModifyInstanceAttribute, display, practice_expectation
from ..builder.validate import Problem, attached_groups, validate
from ..graph.schema import ResourceGraph
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
        """Models often write a port as 80, or null for "none"; every op param is text, "" meaning none."""
        if isinstance(v, dict):
            return {k: "" if x is None else str(x) if isinstance(x, int | float) and not isinstance(x, bool) else x
                    for k, x in v.items()}
        return v


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


def check_step(n: int, raw: RawStep, earlier: list[RawStep], lab: Lab, graph: ResourceGraph,
               azs: list[str], choices: Choices) -> Step:
    """Step `n` (1-based), given the steps before it."""
    params_out = {k: v.model_dump() if isinstance(v, Ref) else v for k, v in raw.params.items()}
    step = Step(raw.op, params_out, raw.explanation)
    op = OPS.get(raw.op)
    if op is None:
        step.problems.append(Problem("", f"{raw.op} is not a builder op; this answer cannot be run"))
        return step
    if op.palette_kind() not in lab.builder.palette:
        step.problems.append(Problem("", f"{lab.id} does not offer {op.name} in its builder"))
    server_fields = {*op.server_fields, *(name for name, f in op.params.model_fields.items() if f.alias in op.server_fields)}
    for name in sorted(server_fields & set(raw.params)):
        step.problems.append(Problem(name, "the server fills this in from the scene"))

    values: dict[str, str] = {}
    for name, value in raw.params.items():
        if name in server_fields:
            continue
        if isinstance(value, str):
            values[name] = value
            continue
        target = earlier[value.ref - 1] if 1 <= value.ref < n else None
        if not name.endswith("Id"):
            step.problems.append(Problem(name, "takes a name, not an id; write the name instead of a ref"))
        elif target is None:
            step.problems.append(Problem(name, f"refers to step {value.ref}, but a step can only use an earlier step"))
        elif (made := OPS.get(target.op)) is None or made.gesture != "create":
            step.problems.append(Problem(name, f"refers to step {value.ref}, which creates nothing to take an id from"))
        else:
            step.refs.append(value.ref)
        values[name] = placeholder(value.ref)
    step.refs = sorted(set(step.refs))

    try:
        params = op.params.model_validate(values)
    except ValidationError as e:
        explain = {"missing": "this parameter is missing", "extra_forbidden": f"not a parameter of {op.name}"}
        for err in e.errors():
            step.problems.append(Problem(".".join(map(str, err["loc"])), explain.get(err["type"], err["msg"])))
        return step
    step.deferred = any(isinstance(v, Ref) for v in raw.params.values())
    if isinstance(params, ModifyInstanceAttribute) and not step.deferred:
        params = params.model_copy(update={"current_groups": attached_groups(graph, params.instance_id)})
    step.command = display(op.argv(params, lab.builder.tags))
    step.practice_expect = practice_expectation(op, params)
    if not step.deferred:
        step.problems += validate(op.name, params, graph, azs, choices)
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
