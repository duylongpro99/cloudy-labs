import os
import stat

import pytest

from cloudy_labs.emulator import aws_profile
from cloudy_labs.emulator.aws_profile import BACKUP_SUFFIX, HEADER, MARK, ProfileError, ensure_lab_profile, lab_profile_ok

WORK = "# my work setup\n[default]\nregion = eu-west-1\n\n[profile work]\nsso_start_url = https://example.awsapps.com/start\n"


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / "aws" / "config"
    monkeypatch.setenv("AWS_CONFIG_FILE", str(path))
    return path


def test_creates_file_and_directory(config):
    assert not lab_profile_ok()
    assert ensure_lab_profile() == "created"
    text = config.read_text()
    assert text.startswith(HEADER + "\n" + MARK)
    assert "endpoint_url = http://127.0.0.1:4566" in text and "aws_access_key_id = test" in text
    assert stat.S_IMODE(os.stat(config).st_mode) == 0o600
    assert lab_profile_ok()
    assert not (config.parent / ("config" + BACKUP_SUFFIX)).exists()  # nothing to back up


def test_rerun_leaves_file_untouched(config):
    config.parent.mkdir()
    config.write_text(WORK)
    assert ensure_lab_profile() == "created"
    before = config.read_bytes()
    mtime = config.stat().st_mtime_ns
    assert ensure_lab_profile() == "unchanged"
    assert config.read_bytes() == before and config.stat().st_mtime_ns == mtime


def test_keeps_comments_and_other_profiles_and_backs_up(config):
    config.parent.mkdir()
    config.write_text(WORK)
    ensure_lab_profile()
    text = config.read_text()
    assert text.startswith(WORK) and HEADER in text
    assert (config.parent / ("config" + BACKUP_SUFFIX)).read_text() == WORK


def test_updates_own_block_in_place(config):
    config.parent.mkdir()
    stale = f"[default]\nregion = eu-west-1\n\n{HEADER}\n{MARK}\nendpoint_url = http://127.0.0.1:9999\n\n[profile work]\nregion = x\n"
    config.write_text(stale)
    assert ensure_lab_profile() == "updated"
    text = config.read_text()
    assert "9999" not in text and "endpoint_url = http://127.0.0.1:4566" in text
    assert text.startswith("[default]\nregion = eu-west-1\n\n" + HEADER)
    assert text.endswith("cli_pager =\n\n[profile work]\nregion = x\n")


def test_refuses_lab_profile_it_did_not_write(config):
    config.parent.mkdir()
    foreign = "[profile lab]\nregion = ap-southeast-1\n"
    config.write_text(foreign)
    with pytest.raises(ProfileError, match="labctl did not write"):
        ensure_lab_profile()
    assert config.read_text() == foreign
    assert not lab_profile_ok()


def test_render_appends_after_text_without_newline():
    assert aws_profile.render("[default]\nregion = x").startswith("[default]\nregion = x\n\n" + HEADER)


def test_updates_through_a_symlinked_config(config, tmp_path):
    real = tmp_path / "dotfiles" / "aws-config"
    real.parent.mkdir()
    real.write_text(WORK)
    config.parent.mkdir()
    config.symlink_to(real)
    assert ensure_lab_profile() == "created"
    assert config.is_symlink() and HEADER in real.read_text()
    assert (real.parent / ("aws-config" + BACKUP_SUFFIX)).read_text() == WORK


def test_update_keeps_a_comment_above_the_next_section(config):
    config.parent.mkdir()
    after = "# work account (prod) - do not delete\n[profile work]\nregion = x\n"
    config.write_text(f"{HEADER}\n{MARK}\nendpoint_url = http://127.0.0.1:9999\n{after}")
    assert ensure_lab_profile() == "updated"
    text = config.read_text()
    assert "9999" not in text and text.endswith("cli_pager =\n" + after)


def test_credentials_with_a_lab_section_are_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    creds = tmp_path / "creds"
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(creds))
    assert aws_profile.credentials_overrides() is None
    creds.write_text("[default]\naws_access_key_id = x\n[lab]\naws_access_key_id = y\n")
    assert aws_profile.credentials_overrides() == creds


@pytest.mark.parametrize("version, too_old", [
    ("aws-cli/2.12.7 Python/3.11.4 Darwin/23.0.0 exe/x86_64", True),
    ("aws-cli/1.29.0 Python/3.11.4 Darwin/23.0.0 botocore/1.31.0", True),
    ("aws-cli/2.13.0 Python/3.11.4 Darwin/23.0.0 exe/x86_64", False),
    ("aws-cli/2.36.31 Python/3.13.11 Darwin/25.6.0 exe/arm64", False),
])
def test_cli_too_old_for_endpoint_url(monkeypatch, version, too_old):
    aws_profile.cli_ignores_endpoint_url.cache_clear()
    monkeypatch.setattr(aws_profile.subprocess, "run", lambda *a, **k: aws_profile.subprocess.CompletedProcess(a, 0, version + "\n", ""))
    try:
        assert (aws_profile.cli_ignores_endpoint_url() == version) is too_old
    finally:
        aws_profile.cli_ignores_endpoint_url.cache_clear()
