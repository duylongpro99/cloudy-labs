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
