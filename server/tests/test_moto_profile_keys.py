"""The lab profile on moto: keys come from `labctl credentials moto` and are never written into the AWS config."""

import json
import os
import shutil
import subprocess

import pytest

from cloudy_labs import cli
from cloudy_labs.emulator.aws_profile import credential_command, ensure_lab_profile, profile_block
from cloudy_labs.providers.aws import AwsProvider, moto_credentials_file


def write_keys(key: str, secret: str) -> None:
    file = moto_credentials_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps({"AccessKeyId": key, "SecretAccessKey": secret}))


def test_credentials_prints_the_credential_process_format(capsys):
    write_keys("AKIAMOTO1", "moto-secret-1")
    assert cli.main(["credentials", "moto"]) == 0
    out, err = capsys.readouterr()
    assert json.loads(out) == {"Version": 1, "AccessKeyId": "AKIAMOTO1", "SecretAccessKey": "moto-secret-1"}
    assert err == ""


def test_credentials_before_any_moto_lab_gives_the_fake_keys(capsys):
    assert cli.main(["credentials", "moto"]) == 0
    assert json.loads(capsys.readouterr().out)["AccessKeyId"] == "test"


def test_only_moto_has_a_credentials_command():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["credentials", "floci"])


def test_the_moto_profile_runs_labctl_and_holds_no_keys(tmp_path, monkeypatch):
    config = tmp_path / "config"
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    write_keys("AKIAMOTO1", "moto-secret-1")
    ensure_lab_profile("moto", "eu-west-1")
    text = config.read_text()
    assert f"credential_process = {credential_command()}" in text
    assert "endpoint_url = http://127.0.0.1:4569" in text and "region = eu-west-1" in text
    assert "AKIAMOTO1" not in text and "moto-secret-1" not in text and "aws_access_key_id" not in text


def test_switching_back_to_floci_drops_the_credential_process(tmp_path, monkeypatch):
    config = tmp_path / "config"
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    ensure_lab_profile("moto")
    assert ensure_lab_profile("floci") == "updated"
    assert config.read_text() == profile_block("floci")


def test_the_credential_command_runs_outside_the_repo(tmp_path):
    """The AWS CLI runs credential_process from wherever the learner is, with its own environment."""
    write_keys("AKIAMOTO2", "moto-secret-2")
    out = subprocess.run(credential_command(), shell=True, cwd=tmp_path, capture_output=True, text=True,
                         env={**os.environ}, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["AccessKeyId"] == "AKIAMOTO2"


@pytest.mark.docker
def test_after_a_reset_the_new_moto_keys_work_through_the_profile(tmp_path, monkeypatch):
    if shutil.which("aws") is None:
        pytest.skip("the AWS CLI is not installed")
    from cloudy_labs.emulator import stack

    stack.up(log=lambda line: None)
    config = tmp_path / "config"
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    ensure_lab_profile("moto")
    env = {k: v for k, v in os.environ.items() if not k.startswith("AWS_") or k == "AWS_CONFIG_FILE"}
    env["AWS_SHARED_CREDENTIALS_FILE"] = str(tmp_path / "no-credentials")

    def list_users() -> subprocess.CompletedProcess:
        return subprocess.run(["aws", "iam", "list-users", "--profile", "lab"], capture_output=True, text=True,
                              env=env, timeout=60)

    keys = []
    for _ in range(2):
        AwsProvider("moto").reset()
        keys.append(AwsProvider("moto").credentials())
        out = list_users()
        assert out.returncode == 0, out.stderr
        assert "cloudy-labs-admin" in out.stdout
    assert keys[0] != keys[1]
    text = config.read_text()
    assert not any(part in text for key in keys for part in key)
