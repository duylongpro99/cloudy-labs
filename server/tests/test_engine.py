from ipaddress import IPv4Network as Net

import pytest

from cloudy_labs.engine import Engine, EngineError
from cloudy_labs.labs import LabError
from cloudy_labs.progress import Progress

LAB_YAML = """
id: {id}
provider: aws
title: Demo {id}
cidrs: [10.0.0.0/16]
setup: ["checks:seed"]
tasks: [{{id: t1, text: make the flag}}]
checks: [{{id: flag, task: t1, fn: "checks:flag_set"}}]
"""

CHECKS_PY = """
from cloudy_labs.checks import CheckResult

def seed(ctx):
    ctx.client("s3").seeded = True

def flag_set(ctx):
    c = ctx.client("s3")
    return CheckResult(c.flag, "flag set" if c.flag else "flag missing", ["r-1"] if c.flag else [])
"""


class FakeClient:
    seeded = False
    flag = False


class FakeProvider:
    def __init__(self, healthy=True):
        self.healthy = healthy
        self.resets = 0
        self.c = FakeClient()

    def client(self, service, credentials=None):
        return self.c

    def env(self):
        return {}

    def reset(self):
        self.resets += 1
        self.c = FakeClient()

    def health(self):
        return self.healthy


@pytest.fixture
def setup(make_lab, tmp_path):
    root = make_lab("demo", LAB_YAML.format(id="demo"), CHECKS_PY)
    make_lab("other", LAB_YAML.format(id="other"), CHECKS_PY)
    provider = FakeProvider()
    logs = []
    engine = Engine(
        Progress(tmp_path / "state" / "p.db"),
        labs_root=root,
        providers=lambda name, emulator: provider,
        networks=lambda: [("corp", Net("10.0.0.0/8"))],
        log=logs.append,
    )
    return engine, provider, logs


def test_start_warns_on_overlap_resets_and_runs_setup(setup):
    engine, provider, logs = setup
    attempt = engine.start("demo")
    assert provider.resets == 1 and provider.c.seeded
    assert any("overlaps Docker network corp" in line and "10.240.0.0/16" in line for line in logs)
    assert engine.progress.current_attempt().id == attempt


def test_check_requires_an_attempt_at_that_lab(setup):
    engine, _, _ = setup
    with pytest.raises(EngineError, match="labctl start demo"):
        engine.check("demo")
    engine.start("other")
    with pytest.raises(EngineError, match="labctl start demo"):
        engine.check("demo")


def test_check_records_fail_then_pass(setup):
    engine, provider, _ = setup
    attempt = engine.start("demo")
    assert engine.check("demo") == (attempt, [r := engine.progress.latest_results("demo")[0]])
    assert not r.passed
    provider.c.flag = True
    _, [r] = engine.check("demo")
    assert r.passed and r.resource_ids == ["r-1"]
    assert engine.progress.lab_summary() == {"demo": True}


def test_reset_opens_a_new_attempt(setup):
    engine, provider, _ = setup
    first = engine.start("demo")
    provider.c.flag = True
    second = engine.reset("demo")
    assert second > first and provider.resets == 2 and not provider.c.flag and provider.c.seeded


def test_unhealthy_emulator_asks_for_labctl_up(setup):
    engine, provider, _ = setup
    provider.healthy = False
    with pytest.raises(EngineError, match="labctl up"):
        engine.start("demo")


def test_failing_setup_step_is_reported(setup, tmp_path):
    engine, provider, _ = setup
    provider.client = lambda service, credentials=None: None  # seed() hits AttributeError
    with pytest.raises(EngineError, match=r"setup step checks:seed failed: AttributeError.*labctl reset demo"):
        engine.start("demo")
    # The emulator was wiped, so a new attempt is open and the old one can no longer be graded.
    assert engine.progress.current_attempt().lab_id == "demo"


def test_status(setup):
    engine, provider, _ = setup
    engine.start("demo")
    provider.c.flag = True
    engine.check("demo")
    s = engine.status()
    assert s["emulators"] == {"floci": True, "moto": True}
    assert s["lab"] == "demo" and s["results"][0]["passed"]
    assert s["labs"] == [
        {"id": "demo", "title": "Demo demo", "completed": True},
        {"id": "other", "title": "Demo other", "completed": False},
    ]
    assert engine.status("other")["results"] == []
    with pytest.raises(LabError, match="no lab 'ghost'"):
        engine.status("ghost")
