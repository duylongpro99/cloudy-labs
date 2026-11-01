"""Kinds that hold secrets, parameter values or stack inputs/outputs must never pass one to the chat."""
import pytest

from cloudy_labs.registry import CHAT_PROPS_DENY, default_registry

SENSITIVE_KINDS = ["cloudformation-stack", "ssm-parameter", "secretsmanager-secret"]
# Props that would carry a value read back from the service, beyond the shared deny-list.
VALUE_WORDS = ("value", "outputs", "parameters")


@pytest.mark.parametrize("kind", SENSITIVE_KINDS)
def test_chat_props_of_value_holding_kinds_hold_no_value(kind: str) -> None:
    rt = default_registry().by_kind[kind]
    assert rt.chat_props, f"{kind} lists no chat_props"
    for prop in rt.chat_props:
        name = prop.lower()
        assert not any(word in name for word in CHAT_PROPS_DENY), f"{kind}.{prop} is deny-listed"
        assert not any(word in name for word in VALUE_WORDS), f"{kind}.{prop} would carry a value"


@pytest.mark.parametrize("kind", SENSITIVE_KINDS)
def test_value_holding_kinds_read_no_value_into_props(kind: str) -> None:
    rt = default_registry().by_kind[kind]
    for name, spec in rt.props.items():
        assert not any(word in name.lower() for word in VALUE_WORDS), f"{kind}.{name} would carry a value"
        if isinstance(spec, str):
            assert not any(field in spec for field in ("Value", "SecretString", "SecretBinary", "Outputs", "Parameters")), \
                f"{kind}.{name} reads {spec!r}"
    calls = [rt.listing.method if rt.listing else "", *(e.method for e in rt.enrich)]
    assert not any(m in ("get_parameter", "get_parameters", "get_parameters_by_path", "get_parameter_history",
                         "get_secret_value", "batch_get_secret_value", "get_template") for m in calls), calls
