import asyncio
import json
from pathlib import Path

from cloudy_labs.builder.ec2_choices import choices
from cloudy_labs.chat.settings import LlmSettings
from cloudy_labs.chat.suggest import FORMAT_FAILED, parse_reply, suggest
from cloudy_labs.graph.schema import ResourceGraph
from cloudy_labs.labs import load_lab

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = ResourceGraph.model_validate_json((FIXTURES / "graph" / "lab-06-07.graph.json").read_text())
LAB06 = load_lab("fixture-lab-06", FIXTURES / "labs").lab
LAB07 = load_lab("fixture-lab-07", FIXTURES / "labs").lab
SETTINGS = LlmSettings("https://llm.example/v1", "sk-test", "m", "openai")
VPC, IGW, SG_WEB, SG_DEFAULT, INSTANCE = "vpc-149d0439", "igw-34ddd4cd", "sg-dbd2e6007fa2e7eef", "sg-b58b05ddff613fe13", "i-fdb553d289095d128"
QUESTION = [{"role": "user", "content": "help"}]


def ask(*answers, lab=LAB06):
    """suggest() with a fake provider that gives these answers in turn."""
    calls = []

    async def complete(settings, system, messages):
        calls.append(messages)
        answer = answers[len(calls) - 1]
        return answer if isinstance(answer, str) else json.dumps(answer)

    result = asyncio.run(suggest(QUESTION, lab=lab, graph=GOLDEN, azs=["us-east-1a", "us-east-1b"],
                                 choices=choices("arm64"), settings=SETTINGS, complete=complete))
    return result, calls


def answer(*steps, reply="ok", refusal=None):
    return {"reply": reply, "refusal": refusal, "steps": [{"op": o, "params": p, "explanation": "why"} for o, p in steps]}


def fields(step):
    return [p.field for p in step.problems]


def test_two_steps_with_a_ref():
    result, calls = ask(answer(("create-subnet", {"name": "lab06-public-c", "vpcId": VPC, "cidr": "10.0.3.0/24", "az": "us-east-1a"}),
                               ("create-route-table", {"name": "lab06-rt-c", "vpcId": VPC}),
                               ("associate-route-table", {"routeTableId": {"ref": 2}, "subnetId": {"ref": 1}})))
    first, second, third = result.steps
    assert len(calls) == 1 and result.reply == "ok"
    assert first.problems == [] and not first.deferred and first.command.startswith("aws ec2 create-subnet")
    assert first.practice_expect == {"kind": "subnet", "label": "lab06-public-c"}
    assert third.deferred and third.refs == [1, 2] and third.problems == []
    assert third.params == {"routeTableId": {"ref": 2}, "subnetId": {"ref": 1}}  # kept for the browser to fill in
    assert "'<id từ bước 2>'" in third.command and "'<id từ bước 1>'" in third.command
    body = result.to_dict()["steps"][2]
    assert set(body) == {"op", "params", "explanation", "command", "problems", "deferred", "refs", "practiceExpect"}


def test_json_in_a_code_fence():
    text = "Here you go:\n```json\n" + json.dumps(answer(("create-internet-gateway", {"name": "igw2"}))) + "\n```"
    result, _ = ask(text)
    assert [s.op for s in result.steps] == ["create-internet-gateway"] and result.steps[0].problems == []


def test_port_as_a_number_is_text():
    reply = parse_reply(json.dumps(answer(("authorize-security-group-ingress", {"groupId": SG_WEB, "port": 443}))))
    assert reply.steps[0].params["port"] == "443"


def test_broken_json_is_fixed_on_the_second_try():
    result, calls = ask('{"reply": "ok", "steps": [', answer(("create-internet-gateway", {"name": "igw2"})))
    assert len(calls) == 2 and [s.op for s in result.steps] == ["create-internet-gateway"]
    retry = calls[1]
    assert retry[:1] == QUESTION and retry[1]["role"] == "assistant" and retry[2]["role"] == "user"
    assert "JSON" in retry[2]["content"]


def test_broken_twice():
    result, calls = ask("not json", "still not json")
    assert len(calls) == 2 and result.reply == FORMAT_FAILED and result.steps == []


def test_unknown_op_is_kept_with_a_problem():
    result, _ = ask(answer(("create-bucket", {"name": "b"})))
    [step] = result.steps
    assert step.op == "create-bucket" and step.command == "" and "not a builder op" in step.problems[0].message


def test_op_outside_the_palette():
    result, _ = ask(answer(("create-key-pair", {"name": "k"})))
    assert "does not offer" in result.steps[0].problems[0].message


def test_missing_and_extra_params():
    result, _ = ask(answer(("create-vpc", {"name": "v", "region": "us-east-1"})))
    step = result.steps[0]
    assert sorted(fields(step)) == ["cidr", "region"] and step.command == ""


def test_ref_to_a_later_step_or_itself():
    result, _ = ask(answer(("attach-internet-gateway", {"igwId": {"ref": 2}, "vpcId": {"ref": 1}}),
                           ("create-internet-gateway", {"name": "igw2"})))
    assert fields(result.steps[0]) == ["igwId", "vpcId"] and result.steps[0].refs == []


def test_ref_to_a_step_that_creates_nothing():
    result, _ = ask(answer(("modify-vpc-attribute", {"vpcId": VPC}),
                           ("create-subnet", {"name": "s", "vpcId": {"ref": 1}, "cidr": "10.0.9.0/24", "az": "us-east-1a"})))
    assert fields(result.steps[1]) == ["vpcId"] and "creates nothing" in result.steps[1].problems[0].message


def test_overlapping_cidr_is_caught_by_validate():
    result, _ = ask(answer(("create-subnet", {"name": "s", "vpcId": VPC, "cidr": "10.0.1.0/25", "az": "us-east-1a"})))
    assert fields(result.steps[0]) == ["cidr"] and "overlaps" in result.steps[0].problems[0].message


def test_made_up_id_is_caught_by_validate():
    result, _ = ask(answer(("attach-internet-gateway", {"igwId": "igw-made-up", "vpcId": VPC})))
    assert "not in the scene" in result.steps[0].problems[0].message


def test_refusal_without_steps():
    result, _ = ask(answer(reply="", refusal="S3 is outside this lab"))
    assert result.refusal == "S3 is outside this lab" and result.steps == []


def test_refusal_drops_any_steps_the_model_added():
    result, _ = ask(answer(("create-internet-gateway", {"name": "igw2"}), refusal="S3 is outside this lab"))
    assert result.refusal and result.steps == []


def test_null_param_means_none_and_keeps_the_answer():
    result, calls = ask(answer(("create-internet-gateway", {"name": "igw2", "extra": None})))
    assert len(calls) == 1 and result.steps[0].params == {"name": "igw2", "extra": ""}
    assert fields(result.steps[0]) == ["extra"]  # shown with its problem, not thrown away


def test_ref_only_stands_for_an_id():
    result, _ = ask(answer(("create-key-pair", {"name": "k"}),
                           ("run-instances", {"name": "web", "subnetId": "subnet-x", "keyName": {"ref": 1}})), lab=LAB07)
    assert "keyName" in fields(result.steps[1]) and result.steps[1].refs == []


def test_current_groups_come_from_the_graph():
    result, _ = ask(answer(("modify-instance-attribute", {"instanceId": INSTANCE, "groupId": SG_DEFAULT})), lab=LAB07)
    step = result.steps[0]
    assert step.problems == [] and f"--groups {SG_WEB} {SG_DEFAULT}" in step.command


def test_model_cannot_send_current_groups():
    result, _ = ask(answer(("modify-instance-attribute", {"instanceId": INSTANCE, "groupId": SG_DEFAULT,
                                                          "currentGroups": ""})), lab=LAB07)
    assert "currentGroups" in fields(result.steps[0])
