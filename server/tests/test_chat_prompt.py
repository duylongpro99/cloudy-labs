import json
from pathlib import Path

from cloudy_labs.builder.ec2_choices import choices
from cloudy_labs.builder.ops import OPS
from cloudy_labs.chat.prompt import OP_NOTES, compact_graph, ops_section, system_prompt
from cloudy_labs.graph.schema import ResourceGraph
from cloudy_labs.labs import load_lab

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = ResourceGraph.model_validate_json((FIXTURES / "graph" / "lab-06-07.graph.json").read_text())
LAB06 = load_lab("fixture-lab-06", FIXTURES / "labs").lab
LAB07 = load_lab("fixture-lab-07", FIXTURES / "labs").lab
AZS = ["us-east-1a", "us-east-1b"]
ARM = choices("arm64")


def test_every_op_has_a_note():
    assert set(OP_NOTES) == set(OPS)


def test_ops_are_those_of_the_palette():
    names = {o["op"] for o in ops_section(list(LAB06.builder.palette))}
    assert "create-subnet" in names and "create-route" in names
    assert not names & {"run-instances", "create-security-group", "modify-instance-attribute"}


def test_server_fields_are_not_offered():
    [attach] = [o for o in ops_section(list(LAB07.builder.palette)) if o["op"] == "modify-instance-attribute"]
    assert attach["params"] == {"instanceId": "string", "groupId": "string"}


def test_compact_graph_folds_azs_into_parents():
    g = compact_graph(GOLDEN)
    by_id = {n["id"]: n for n in g["nodes"]}
    assert not any(n["kind"] in ("region", "az") for n in g["nodes"])
    subnet = by_id["subnet-83a1f79a"]
    assert subnet["in"] == "vpc-149d0439" and subnet["az"] == "us-east-1a" and subnet["cidr"] == "10.0.1.0/24"
    assert by_id["sg-dbd2e6007fa2e7eef"]["ingress"][0]["sources"] == ["203.0.113.10/32"]
    assert "hostPorts" not in by_id["i-fdb553d289095d128"] and "tags" not in by_id["vpc-149d0439"]
    assert {"kind": "route", "from": "rtb-509e5b33", "to": "igw-34ddd4cd", "label": "0.0.0.0/0"} in g["edges"]


def test_lab06_prompt():
    text = system_prompt(LAB06, GOLDEN, AZS, ARM)
    assert "Fixture Lab 6" in text and "Create a VPC 10.66.0.0/16" in text
    assert '"create-nat-gateway"' in text and '"run-instances"' not in text
    assert "vpc-149d0439" in text and "subnet-83a1f79a" in text and json.dumps(AZS, separators=(",", ":")) in text
    assert "currentGroups" not in text and "ami-" not in text
    assert '{"ref": n}' in text and "refusal" in text
    print(f"\nprompt length, fixture-lab-06 on the golden graph: {len(text)} characters")


def test_lab07_prompt_has_images_and_user_data():
    text = system_prompt(LAB07, GOLDEN, AZS, ARM)
    assert '"run-instances"' in text and '"create-vpc"' not in text
    assert "ami-amazonlinux2023-arm64" in text and "t4g.micro" in text and "http.server 80" in text
    assert "currentGroups" not in text
    print(f"\nprompt length, fixture-lab-07 on the golden graph: {len(text)} characters")
