import json
import stat

import pytest

from cloudy_labs.labs import Lab, LabError
from cloudy_labs.providers import AwsProvider, provider_for
from cloudy_labs.providers.aws import MOTO_NO_AUTH_ACTIONS, moto_credentials_file


def lab(**over):
    data = {
        "id": "demo",
        "provider": "aws",
        "title": "T",
        "tasks": [{"id": "t", "text": "x"}],
        "checks": [{"id": "c", "task": "t", "fn": "checks:ok"}],
    }
    return Lab.model_validate(data | over)


@pytest.mark.parametrize("emulator, endpoint", [("floci", "http://127.0.0.1:4566"), ("moto", "http://127.0.0.1:5050")])
def test_env_points_at_the_lab_emulator(emulator, endpoint):
    env = provider_for(lab(emulator=emulator)).env()
    assert env == {
        "AWS_ENDPOINT_URL": endpoint,
        "AWS_ACCESS_KEY_ID": "test",
        "AWS_SECRET_ACCESS_KEY": "test",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_PAGER": "",
    }


def test_default_provider_is_floci_through_api_tap():
    p = provider_for(None)
    assert (p.endpoint, p.direct_endpoint) == ("http://127.0.0.1:4566", "http://127.0.0.1:4567")


def test_direct_client_bypasses_api_tap():
    assert AwsProvider("floci").client("ec2", direct=True).meta.endpoint_url == "http://127.0.0.1:4567"
    assert AwsProvider("floci").client("ec2").meta.endpoint_url == "http://127.0.0.1:4566"


def test_client_uses_endpoint_and_optional_credentials():
    c = AwsProvider("moto").client("iam", credentials=("AKIA1", "s3cr3t"))
    assert c.meta.endpoint_url == "http://127.0.0.1:5050"
    assert c._request_signer._credentials.access_key == "AKIA1"


def test_unsupported_provider():
    fake = lab().model_copy(update={"provider": "gcp"})
    with pytest.raises(LabError, match="unsupported provider .gcp. on emulator"):
        provider_for(fake)


class FakeIam:
    def __init__(self):
        self.calls = []

    def create_user(self, **kw):
        self.calls.append("CreateUser")

    def put_user_policy(self, **kw):
        self.calls.append("PutUserPolicy")
        assert json.loads(kw["PolicyDocument"])["Statement"][0]["Action"] == "*"

    def create_access_key(self, **kw):
        self.calls.append("CreateAccessKey")
        return {"AccessKey": {"AccessKeyId": "AKIAADMIN", "SecretAccessKey": "admin-secret"}}


def test_moto_reset_creates_admin_within_unauthenticated_calls(monkeypatch):
    sent, iam, used = [], FakeIam(), []
    p = AwsProvider("moto")
    monkeypatch.setattr(p, "_moto_post", lambda path, body, ctype: sent.append((path, body, ctype)))
    monkeypatch.setattr(p, "client", lambda service, credentials=None: used.append(credentials) or iam)
    p.reset()
    assert sent == [("/moto-api/reset", b"", "application/json"), ("/moto-api/reset-auth", b"3", "text/plain")]
    # Every bootstrap call must fit in the unauthenticated calls reset-auth grants.
    assert len(iam.calls) == MOTO_NO_AUTH_ACTIONS and used == [("test", "test")]
    file = moto_credentials_file()
    assert stat.S_IMODE(file.stat().st_mode) == 0o600
    assert p.credentials() == ("AKIAADMIN", "admin-secret")
    assert p.env()["AWS_ACCESS_KEY_ID"] == "AKIAADMIN"
    assert AwsProvider("floci").credentials() == ("test", "test")  # Floci never uses them


def test_compose_leaves_moto_auth_count_to_the_provider():
    from cloudy_labs.emulator.stack import COMPOSE_FILE

    assert "INITIAL_NO_AUTH_ACTION_COUNT:" not in COMPOSE_FILE.read_text()
