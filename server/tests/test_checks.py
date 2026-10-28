from unittest.mock import MagicMock

from cloudy_labs.checks import CheckContext, CheckResult, run_checks
from cloudy_labs.labs import load_lab

LAB_YAML = """
id: demo
provider: aws
title: T
tasks: [{id: t1, text: x}]
checks:
  - {id: passes, task: t1, fn: "checks:passes", args: {name: web}}
  - {id: fails, task: t1, fn: "checks:fails"}
  - {id: raises, task: t1, fn: "checks:raises"}
  - {id: wrong-type, task: t1, fn: "checks:wrong_type"}
  - {id: truthy, task: t1, fn: "checks:truthy"}
  - {id: bad-ids, task: t1, fn: "checks:bad_ids"}
"""

CHECKS_PY = """
from cloudy_labs.checks import CheckResult

def passes(ctx, name):
    return CheckResult(True, f"found {name}", ["i-1"])

def fails(ctx):
    return CheckResult(False, "missing")

def raises(ctx):
    raise KeyError("Vpcs")

def wrong_type(ctx):
    return True

def truthy(ctx):
    return CheckResult(1, "ok")

def bad_ids(ctx):
    return CheckResult(True, "ok", "i-1")
"""


def test_run_checks_covers_every_outcome(make_lab):
    loaded = load_lab("demo", make_lab("demo", LAB_YAML, CHECKS_PY))
    results = {r.check_id: r for r in run_checks(loaded, CheckContext(client=MagicMock()))}
    assert list(results) == ["passes", "fails", "raises", "wrong-type", "truthy", "bad-ids"]
    assert results["passes"] == CheckResult(True, "found web", ["i-1"], "passes")
    assert not results["fails"].passed and results["fails"].message == "missing"
    assert not results["raises"].passed and "KeyError" in results["raises"].message
    assert not results["wrong-type"].passed and "returned bool" in results["wrong-type"].message
    assert not results["truthy"].passed and "passed=1" in results["truthy"].message
    assert not results["bad-ids"].passed and "resource_ids" in results["bad-ids"].message


def test_fixture_checker_reads_through_ctx_client(fixture_labs):
    ec2 = MagicMock()
    ec2.describe_vpcs.return_value = {"Vpcs": [{"VpcId": "vpc-1", "CidrBlock": "10.77.0.0/16"}]}
    loaded = load_lab("fixture-vpc", fixture_labs)
    [result] = run_checks(loaded, CheckContext(client=lambda service: ec2))
    assert result.passed and result.resource_ids == ["vpc-1"]
    ec2.describe_vpcs.assert_called_once_with(Filters=[{"Name": "tag:lab", "Values": ["fixture-vpc"]}])
