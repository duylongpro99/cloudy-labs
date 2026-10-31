import pytest
from pydantic import ValidationError

from cloudy_labs.labs import Lab


def base(**over):
    data = {
        "id": "demo",
        "provider": "aws",
        "title": "Demo",
        "tasks": [{"id": "t1", "text": "do it"}],
        "checks": [{"id": "c1", "task": "t1", "fn": "checks:ok"}],
    }
    data.update(over)
    return data


def target(*nodes):
    return {"target": {"nodes": list(nodes)}}


def test_minimal_lab_gets_defaults():
    lab = Lab.model_validate(base(cidrs=["10.0.0.0/16"]))
    assert lab.emulator == "floci"
    assert str(lab.cidrs[0]) == "10.0.0.0/16"
    assert lab.checks[0].args == {}


@pytest.mark.parametrize(
    "over, needle",
    [
        ({"tasks": [{"id": "t1", "text": "a"}, {"id": "t1", "text": "b"}]}, "duplicate task id"),
        (
            {"checks": [{"id": "c1", "task": "t1", "fn": "checks:a"}, {"id": "c1", "task": "t1", "fn": "checks:b"}]},
            "duplicate check id",
        ),
        ({"checks": [{"id": "c1", "task": "nope", "fn": "checks:ok"}]}, "unknown task 'nope'"),
        ({"hints": [{"task": "nope", "text": "x"}]}, "unknown task 'nope'"),
        ({"checks": [{"id": "c1", "task": "t1", "fn": "checks.ok"}]}, "module:function"),
        ({"setup": ["setup"]}, "module:function"),
        ({"surprise": 1}, "Extra inputs"),
        ({"emulator": "localstack"}, "floci"),
        ({"cidrs": ["10.0.0.1/16"]}, "valid IPv4 network"),
        ({"id": "Bad Id"}, "pattern"),
        ({"checks": []}, "at least 1"),
        ({"builder": {"palette": ["vpc", "vpc"]}}, "palette lists a kind twice"),
        ({"builder": {"palette": ["lambda"]}}, "'vpc'"),
        ({"builder": {"tags": {"Name": "x"}}}, "Name tag comes from the builder form"),
        ({"builder": {"tags": {"lab": "a,b"}}}, "letters, digits"),
        ({"builder": {"tags": {"lab": "a\n"}}}, "letters, digits"),
        ({"builder": {"surprise": 1}}, "Extra inputs"),
        ({"builder": {"userData": "x" * (16 * 1024 + 1)}}, "at most 16384"),
        ({"builder": {"palette": ["instance", "lambda"]}}, "'instance'"),
        (target({"id": "vpc", "kind": "vpc", "label": "v", "checks": ["c1"]}, {"id": "vpc", "kind": "igw", "label": "i", "checks": ["c1"]}),
         "duplicate target node id: vpc"),
        (target({"id": "s", "kind": "subnet-public", "parent": "nope", "label": "s", "checks": ["c1"]}), "unknown parent 'nope'"),
        (target({"id": "s", "kind": "subnet-public", "label": "s", "checks": ["c1"]}), "cannot sit in the region"),
        (target({"id": "vpc", "kind": "vpc", "label": "v", "checks": ["c1"]},
                {"id": "s", "kind": "subnet-public", "parent": "vpc", "label": "s", "checks": ["c1"]}), "it goes in az"),
        (target({"id": "vpc", "kind": "vpc", "label": "v", "checks": ["c1", "c9"]}), "'vpc' refers to unknown check 'c9'"),
        (target({"id": "vpc", "kind": "vpc", "label": "v"}), "'vpc' needs at least one check"),
        (target({"id": "vpc", "kind": "vpc", "label": "v", "checks": ["c1"]},
                {"id": "a", "kind": "az", "parent": "vpc", "label": "a", "checks": ["c1"]}), "an az has no checks"),
        (target({"id": "r", "kind": "region", "label": "r", "checks": ["c1"]}), "'vpc'"),
        (target({"id": "Bad", "kind": "vpc", "label": "v", "checks": ["c1"]}), "pattern"),
        ({"target": {"nodes": [], "edges": []}}, "Extra inputs"),
    ],
)
def test_invalid_lab(over, needle):
    with pytest.raises(ValidationError, match=needle):
        Lab.model_validate(base(**over))


def test_builder_defaults_to_empty():
    lab = Lab.model_validate(base())
    assert lab.builder.palette == [] and lab.builder.tags == {}


def test_builder_section():
    lab = Lab.model_validate(base(builder={"palette": ["vpc", "subnet"], "tags": {"lab": "06"}}))
    assert lab.builder.palette == ["vpc", "subnet"]
    assert lab.builder.tags == {"lab": "06"}


def test_builder_user_data():
    lab = Lab.model_validate(base(builder={"palette": ["security-group", "key-pair", "instance"],
                                           "userData": "#!/bin/sh\necho ok\n"}))
    assert lab.builder.palette == ["security-group", "key-pair", "instance"]
    assert lab.builder.user_data == "#!/bin/sh\necho ok\n"
    assert Lab.model_validate(base(builder={"userData": "é" * 8192})).builder.user_data  # 16 KB counted in bytes
    assert Lab.model_validate(base()).builder.user_data == ""


def test_target_nests_like_the_collector():
    lab = Lab.model_validate(base(**target(
        {"id": "vpc", "kind": "vpc", "label": "VPC", "checks": ["c1"]},
        {"id": "igw", "kind": "igw", "parent": "vpc", "label": "IGW", "checks": ["c1"]},
        {"id": "az-1", "kind": "az", "parent": "vpc", "label": "AZ"},
        {"id": "nat", "kind": "nat", "parent": "public", "label": "NAT", "checks": ["c1"]},  # parent declared later is fine
        {"id": "public", "kind": "subnet-public", "parent": "az-1", "label": "Public", "checks": ["c1"]},
        {"id": "key", "kind": "key-pair", "label": "Key", "checks": ["c1"]},
    )))
    assert [(n.id, n.parent) for n in lab.target.nodes][:2] == [("vpc", None), ("igw", "vpc")]
    assert Lab.model_validate(base()).target.nodes == []
