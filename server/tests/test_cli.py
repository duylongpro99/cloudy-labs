import pytest

from cloudy_labs import cli
from cloudy_labs.cli import COMMANDS, build_parser, main


def test_help_lists_every_command(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--help"])
    out = capsys.readouterr().out
    for name in COMMANDS:
        assert name in out


def test_lab_commands_require_lab_id():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["check"])


def test_env_prints_shell_exports(capsys):
    assert main(["env"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "export AWS_ENDPOINT_URL=http://127.0.0.1:4566" in out
    assert "export AWS_PAGER=''" in out


def test_unknown_lab_is_a_clean_error(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDY_LABS_LABS_DIR", str(tmp_path))
    assert main(["env", "ghost"]) == 1
    assert "no lab 'ghost'" in capsys.readouterr().err


def test_check_exit_codes(monkeypatch, capsys):
    from cloudy_labs.checks import CheckResult

    class FakeEngine:
        outcome = None

        @classmethod
        def default(cls):
            return cls()

        def check(self, lab_id):
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return 7, self.outcome

    monkeypatch.setattr(cli, "Engine", FakeEngine)
    FakeEngine.outcome = [CheckResult(True, "ok", [], "a")]
    assert main(["check", "demo"]) == 0
    FakeEngine.outcome = [CheckResult(True, "ok", [], "a"), CheckResult(False, "no", [], "b")]
    assert main(["check", "demo"]) == 1
    FakeEngine.outcome = cli.EngineError("no open attempt")
    assert main(["check", "demo"]) == 2
    FakeEngine.outcome = RuntimeError("boom")
    assert main(["check", "demo"]) == 2
    assert "unexpected error: RuntimeError: boom" in capsys.readouterr().err


def test_serve_refuses_without_the_emulator(monkeypatch, capsys):
    monkeypatch.setattr(cli.stack, "is_running", lambda: False)
    assert main(["serve"]) == 1
    assert "labctl up" in capsys.readouterr().err


def test_serve_refuses_a_busy_port_instead_of_moving(monkeypatch, capsys):
    import socket

    monkeypatch.setattr(cli.stack, "is_running", lambda: True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        monkeypatch.setattr(cli, "SERVER_PORT", s.getsockname()[1])
        assert main(["serve"]) == 1
    assert "already in use" in capsys.readouterr().err


def test_up_writes_the_lab_profile(monkeypatch, tmp_path, capsys):
    config = tmp_path / "aws-config"
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    monkeypatch.setattr(cli.stack, "up", lambda: None)
    assert main(["up"]) == 0
    assert "profile 'lab' created" in capsys.readouterr().out
    assert "[profile lab]" in config.read_text()
    assert main(["up"]) == 0
    assert capsys.readouterr().out == ""  # already right: nothing written, nothing said


def test_up_leaves_a_foreign_lab_profile_alone(monkeypatch, tmp_path, capsys):
    config = tmp_path / "aws-config"
    config.write_text("[profile lab]\nregion = eu-west-1\n")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    monkeypatch.setattr(cli.stack, "up", lambda: None)
    assert main(["up"]) == 1
    assert "labctl did not write" in capsys.readouterr().err
    assert config.read_text() == "[profile lab]\nregion = eu-west-1\n"


def test_serve_warns_without_aws_cli_or_profile(monkeypatch, tmp_path, capsys):
    import uvicorn

    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "absent"))
    monkeypatch.setattr(cli.stack, "is_running", lambda: True)
    monkeypatch.setattr(cli, "port_free", lambda port, host: True)
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    assert main(["serve"]) == 0  # still serves: the scene and command previews work without them
    err = capsys.readouterr().err
    assert "aws CLI is not on PATH" in err and "run `labctl up` to write it" in err
