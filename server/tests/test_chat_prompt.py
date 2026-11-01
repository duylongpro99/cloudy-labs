import json
from datetime import datetime, timezone
from pathlib import Path

from cloudy_labs.builder.ec2_choices import choices
from cloudy_labs.builder.catalog import all_ops
from cloudy_labs.chat.prompt import compact_graph, emulator_limits, ops_section, system_prompt
from cloudy_labs.graph.schema import ResourceGraph
from cloudy_labs.labs import load_lab

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = ResourceGraph.model_validate_json((FIXTURES / "graph" / "lab-06-07.graph.json").read_text())
LAB06 = load_lab("fixture-lab-06", FIXTURES / "labs").lab
LAB07 = load_lab("fixture-lab-07", FIXTURES / "labs").lab
AZS = ["ap-southeast-2a", "ap-southeast-2b"]
ARM = choices("arm64")


def test_every_op_has_a_note():
    assert all(op.spec.note for op in all_ops().values())


def test_ops_are_those_of_the_palette():
    names = {o["op"] for o in ops_section(list(LAB06.builder.palette))}
    assert "create-subnet" in names and "create-route" in names
    assert not names & {"run-instances", "create-security-group", "modify-instance-attribute"}


def test_server_fields_are_not_offered():
    [attach] = [o for o in ops_section(list(LAB07.builder.palette)) if o["op"] == "modify-instance-attribute"]
    assert set(attach["params"]) == {"instanceId", "groupId"}
    assert attach["params"]["groupId"].startswith("string (the id of a security-group), required")


def test_compact_graph_folds_azs_into_parents():
    g = compact_graph(GOLDEN)
    by_id = {n["id"]: n for n in g["nodes"]}
    assert not any(n["kind"] in ("region", "az") for n in g["nodes"])
    subnet = by_id["subnet-83a1f79a"]
    assert subnet["in"] == "vpc-149d0439" and subnet["az"] == "ap-southeast-2a" and subnet["cidr"] == "10.0.1.0/24"
    assert by_id["sg-dbd2e6007fa2e7eef"]["ingress"][0]["sources"] == ["203.0.113.10/32"]
    assert "tags" not in by_id["vpc-149d0439"] and "tags" not in by_id["i-fdb553d289095d128"]
    assert {"kind": "route", "from": "rtb-509e5b33", "to": "igw-34ddd4cd", "label": "0.0.0.0/0"} in g["edges"]


def test_a_datetime_prop_is_written_as_iso():
    g = GOLDEN.model_copy(deep=True)
    g.nodes.append(g.nodes[0].model_copy(update={
        "id": "arn:secret", "kind": "secretsmanager-secret", "label": "db-credentials",
        "props": {"lastChanged": datetime(2026, 11, 1, 4, 43, tzinfo=timezone.utc)}}))
    assert '"lastChanged":"2026-11-01T04:43:00+00:00"' in system_prompt(LAB06, g, AZS, ARM)


def test_lab06_prompt():
    text = system_prompt(LAB06, GOLDEN, AZS, ARM)
    assert "Fixture Lab 6" in text and "Create a VPC 10.66.0.0/16" in text
    assert '"create-nat-gateway"' in text and '"run-instances"' not in text
    assert "vpc-149d0439" in text and "subnet-83a1f79a" in text and json.dumps(AZS, separators=(",", ":")) in text
    assert "currentGroups" not in text and "Images (imageId)" not in text and "Instance types" not in text
    assert '{"ref": n}' in text and "refusal" in text
    print(f"\nprompt length, fixture-lab-06 on the golden graph: {len(text)} characters")


def test_lab07_prompt_has_images_and_user_data():
    text = system_prompt(LAB07, GOLDEN, AZS, ARM)
    assert '"run-instances"' in text and '"create-vpc"' not in text
    assert "ami-amazonlinux2023-arm64" in text and "t4g.micro" in text and "http.server 80" in text
    assert "currentGroups" not in text and "Images (imageId)" in text
    print(f"\nprompt length, fixture-lab-07 on the golden graph: {len(text)} characters")


def test_limits_name_the_lab_services_and_actions():
    [_, ops] = emulator_limits(LAB06)
    assert "services: ec2" in ops and "delete" not in ops and "S3" not in ops
    assert any("UserData" in line for line in emulator_limits(LAB07))
