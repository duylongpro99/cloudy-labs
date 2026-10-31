import pytest

from cloudy_labs.labs import LabError, list_labs, load_lab

LAB_YAML = """
id: {id}
provider: aws
title: T
tasks: [{{id: t1, text: x}}]
checks: [{{id: c1, task: t1, fn: "{fn}"}}]
"""


def test_loads_fixture_and_resolves_checker(fixture_labs):
    loaded = load_lab("fixture-vpc", fixture_labs)
    assert loaded.lab.cidrs and str(loaded.lab.cidrs[0]) == "10.77.0.0/16"
    assert callable(loaded.resolve("checks:vpc_exists"))
    assert list_labs(fixture_labs) == ["fixture-lab-06", "fixture-lab-07", "fixture-vpc"]


def test_loads_builder_fixture(fixture_labs):
    loaded = load_lab("fixture-lab-06", fixture_labs)
    lab = loaded.lab
    assert lab.builder.palette == ["vpc", "subnet", "igw", "elastic-ip", "nat", "route-table"]
    assert lab.builder.tags == {"lab": "fixture-lab-06"}
    assert [str(c) for c in lab.cidrs] == ["10.66.0.0/16"]
    assert len(lab.checks) == 8  # every fn resolved at load time


def test_loads_lab_07_fixture(fixture_labs):
    loaded = load_lab("fixture-lab-07", fixture_labs)
    lab = loaded.lab
    assert lab.builder.palette == ["security-group", "key-pair", "instance"]
    assert lab.setup == ["checks:setup_network"] and callable(loaded.resolve("checks:setup_network"))
    assert '--bind "$IP"' in lab.builder.user_data and lab.builder.user_data.startswith("#!/bin/sh\n")
    assert len(lab.checks) == 7 and lab.checks[0].id == "network-ready"
    assert [n.id for n in lab.target.nodes][:3] == ["vpc", "igw", "az"]


def test_list_labs_missing_root(tmp_path):
    assert list_labs(tmp_path / "absent") == []


def test_missing_lab(tmp_path):
    with pytest.raises(LabError, match="no lab 'ghost'"):
        load_lab("ghost", tmp_path)


def test_missing_function_fails_at_load(make_lab):
    root = make_lab("demo", LAB_YAML.format(id="demo", fn="checks:absent"), "def other(ctx): pass\n")
    with pytest.raises(LabError, match="no function 'absent'"):
        load_lab("demo", root)


def test_missing_module_file(make_lab):
    root = make_lab("demo", LAB_YAML.format(id="demo", fn="checks:ok"))
    with pytest.raises(LabError, match="no file"):
        load_lab("demo", root)


def test_import_error_is_lab_error(make_lab):
    root = make_lab("demo", LAB_YAML.format(id="demo", fn="checks:ok"), "raise RuntimeError('boom')\n")
    with pytest.raises(LabError, match="cannot import checks.py: boom"):
        load_lab("demo", root)


def test_schema_error_names_file_and_field(make_lab):
    root = make_lab("demo", LAB_YAML.format(id="demo", fn="bad"))
    with pytest.raises(LabError, match=r"lab\.yaml: checks\.0\.fn"):
        load_lab("demo", root)


def test_invalid_yaml(make_lab):
    root = make_lab("demo", "id: [unclosed\n")
    with pytest.raises(LabError, match="invalid YAML"):
        load_lab("demo", root)


def test_id_must_match_directory(make_lab):
    root = make_lab("demo", LAB_YAML.format(id="other", fn="checks:ok"), "def ok(ctx): pass\n")
    with pytest.raises(LabError, match="does not match directory"):
        load_lab("demo", root)


def test_same_module_name_in_two_labs_does_not_collide(tmp_path):
    for lab_id, value in (("a", 1), ("b", 2)):
        d = tmp_path / lab_id
        d.mkdir()
        (d / "lab.yaml").write_text(LAB_YAML.format(id=lab_id, fn="checks:ok"))
        (d / "checks.py").write_text(f"def ok(ctx): return {value}\n")
    assert load_lab("a", tmp_path).resolve("checks:ok")(None) == 1
    assert load_lab("b", tmp_path).resolve("checks:ok")(None) == 2


def test_checker_module_supports_dataclasses(make_lab):
    # dataclasses look the defining module up in sys.modules while the module executes.
    checks = "from __future__ import annotations\nfrom dataclasses import dataclass\n\n@dataclass\nclass Row:\n    name: str\n\ndef ok(ctx):\n    return Row('x')\n"
    root = make_lab("demo", LAB_YAML.format(id="demo", fn="checks:ok"), checks)
    assert load_lab("demo", root).resolve("checks:ok")(None).name == "x"
