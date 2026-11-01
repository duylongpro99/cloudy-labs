import asyncio
import json
from pathlib import Path

import pytest

from cloudy_labs.builder.catalog import all_ops, catalog, expectation, op_named, practice_expectation, prepare
from cloudy_labs.builder.ec2_choices import choices
from cloudy_labs.builder.ops import OPS
from cloudy_labs.graph.schema import ResourceGraph
from cloudy_labs.labs import load_lab
from cloudy_labs.registry import ResourceType, default_registry

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN_JSON = json.loads((FIXTURES / "graph" / "lab-06-07.graph.json").read_text())
LAB06 = load_lab("fixture-lab-06", FIXTURES / "labs").lab
AZS = ["ap-southeast-2a", "ap-southeast-2b"]
TAGS = {"lab": "06"}


def graph_with(*nodes):
    g = json.loads(json.dumps(GOLDEN_JSON))
    for kind, node_id, parent in nodes:
        g["nodes"].append({"id": node_id, "kind": kind, "label": node_id, "props": {}})
        g["contains"].append({"child": node_id, "parent": parent})
    return ResourceGraph.model_validate(g)


def lab_with(*kinds):
    builder = LAB06.builder.model_copy(update={"palette": [*LAB06.builder.palette, *kinds]})
    return LAB06.model_copy(update={"builder": builder})


@pytest.fixture
def test_kinds(extra_registry):
    return extra_registry("test-only", "test-protected")


def test_every_registry_op_builds_and_the_hand_written_ones_come_first():
    ops = all_ops()
    assert list(ops)[:len(OPS)] == list(OPS)
    assert all(ops[name].legacy for name in OPS)
    assert all(op.spec.title and op.spec.note for op in ops.values())
    assert {"create-bucket", "create-function", "create-role", "create-db-instance"} <= set(ops)


def test_a_registry_entry_alone_adds_an_op(test_kinds):
    op = op_named("create-test-queue")
    assert op is not None and op.legacy is None and op.palette_kind() == "test-only"
    assert "create-test-queue" not in {o["name"] for o in catalog(list(LAB06.builder.palette))}
    [described] = [o for o in catalog(["test-only"]) if o["name"] == "create-test-queue"]
    assert described["generated"] and described["creates"] == "test-only" and described["containers"] == ["region"]
    assert described["nameField"] == "QueueName"
    queue_name = described["fields"][0]
    assert queue_name["name"] == "QueueName" and queue_name["required"] and queue_name["doc"]
    assert not {"tags", "Tags"} & {f["name"] for f in described["fields"]}

    prepared = prepare(op, {"QueueName": "lab-queue"}, graph=graph_with(), azs=AZS, choices=choices("arm64"), tags=TAGS)
    assert prepared.problems == []
    assert prepared.argv == ["aws", "sqs", "create-queue", "--queue-name", "lab-queue", "--tags", '{"lab":"06"}',
                             "--profile", "lab", "--output", "json"]
    assert practice_expectation(prepared) == {"kind": "test-only", "label": "lab-queue"}
    assert expectation(prepared, '{"QueueUrl": "http://x/lab-queue"}', 7) == {"after": 7}


def test_the_chat_offers_and_checks_a_registry_op(test_kinds):
    from cloudy_labs.chat.prompt import ops_section
    from cloudy_labs.chat.settings import LlmSettings
    from cloudy_labs.chat.suggest import suggest

    lab = lab_with("test-only")
    [offered] = [o for o in ops_section(list(lab.builder.palette)) if o["op"] == "create-test-queue"]
    assert offered["params"] == {"QueueName": "string, required"} and "test-only" in offered["does"]

    async def complete(settings, system, messages):
        assert '"create-test-queue"' in system
        return json.dumps({"reply": "ok", "refusal": None, "steps": [
            {"op": "create-test-queue", "params": {"QueueName": "lab-queue"}, "explanation": "why"},
            {"op": "create-test-queue", "params": {"QueueName": "file:///etc/passwd"}, "explanation": "why"}]})

    result = asyncio.run(suggest([{"role": "user", "content": "q"}], lab=lab, graph=graph_with(), azs=AZS,
                                 choices=choices("arm64"), settings=LlmSettings("https://x/v1", "k", "m", "openai"),
                                 complete=complete))
    good, bad = result.steps
    assert good.problems == [] and good.command.startswith("aws sqs create-queue --queue-name lab-queue")
    assert [p.field for p in bad.problems] == ["QueueName"] and "file://" in bad.problems[0].message


def test_deleting_a_protected_resource_is_refused_by_the_builder(test_kinds):
    graph = graph_with(("test-user", "learner", "global"))
    op = op_named("delete-test-user")
    refused = prepare(op, {"UserName": "cloudy-labs-admin"}, graph=graph, azs=AZS, choices={}, tags=TAGS)
    assert any("belongs to the lab platform" in p.message for p in refused.problems)

    allowed = prepare(op, {"UserName": "learner"}, graph=graph, azs=AZS, choices={}, tags=TAGS)
    assert allowed.problems == [] and allowed.command == "aws iam delete-user --user-name learner --profile lab --output json"
    assert practice_expectation(allowed) == {"gone": "learner"} and expectation(allowed, "", 3) == {"gone": "learner"}


def test_the_platform_admin_user_is_hidden_and_refused_by_every_user_op():
    from graph_fixtures import wave_1_graph

    graph = wave_1_graph()
    assert not [n for n in graph.nodes if n.label == "cloudy-labs-admin"]
    # Even with the admin in the scene, an op acting on it is refused by the registry's protected rule.
    scene = graph_with(("iam-user", "cloudy-labs-admin", "global"), ("iam-group", "admins", "global"))
    for name, params in [("attach-user-policy", {"UserName": "cloudy-labs-admin", "PolicyArn": "arn:aws:iam::aws:policy/AdministratorAccess"}),
                         ("add-user-to-group", {"UserName": "cloudy-labs-admin", "GroupName": "admins"})]:
        refused = prepare(op_named(name), params, graph=scene, azs=AZS, choices={}, tags=TAGS)
        assert any("belongs to the lab platform" in p.message for p in refused.problems), name
    allowed = prepare(op_named("add-user-to-group"), {"UserName": "learner", "GroupName": "admins"},
                      graph=graph_with(("iam-user", "learner", "global"), ("iam-group", "admins", "global")),
                      azs=AZS, choices={}, tags=TAGS)
    assert allowed.problems == []


def test_deleting_a_protected_resource_is_refused_through_the_chat(test_kinds):
    from cloudy_labs.chat.suggest import RawStep, check_step

    graph = graph_with(("test-user", "learner", "global"))
    raw = RawStep(op="delete-test-user", params={"UserName": "cloudy-labs-admin"}, explanation="why")
    step = check_step(1, raw, [], lab_with("test-user"), graph, AZS, {})
    assert any("belongs to the lab platform" in p.message for p in step.problems)


@pytest.mark.parametrize("prop", ["Password", "dbSecret", "UserData", "Environment"])
def test_chat_props_that_may_hold_secrets_fail_the_load(prop):
    entry = {"kind": "x-thing", "service": "x", "label": "X", "list": {"method": "list_x", "items": "Xs"}, "id": ["Id"],
             "parent": [{"kind": "region"}], "props": {prop: prop}, "chat_props": [prop],
             "view": {"role": "block", "category": "general", "icon": "x.svg"}}
    with pytest.raises(ValueError, match="never go to the chat model"):
        ResourceType.model_validate(entry)


def test_every_op_belongs_to_a_kind_a_lab_palette_can_offer():
    # A version, alias or snapshot is made from its resource's palette entry: no palette lists it.
    offerable = set(default_registry().builder_kinds())
    assert {name: op.palette_kind() for name, op in all_ops().items() if op.palette_kind() not in offerable} == {}
    assert op_named("publish-version").palette_kind() == "lambda-function"
    assert op_named("create-db-snapshot").palette_kind() == "db-instance"
