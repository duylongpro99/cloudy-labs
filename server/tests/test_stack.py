import pytest
import yaml

from cloudy_labs.emulator import stack
from cloudy_labs.emulator.docker import DockerError
from cloudy_labs.emulator.orphans import Orphans
from cloudy_labs.emulator.stack import COMPOSE_FILE, parse_ps


def test_parse_ps_line_and_array_formats():
    line = '{"Service":"floci","State":"running","Health":"healthy"}\n{"Service":"moto","State":"exited","Health":""}\n'
    array = '[{"Service":"floci","State":"running","Health":"healthy"}]'
    assert parse_ps(line)["moto"]["State"] == "exited"
    assert parse_ps(array)["floci"]["Health"] == "healthy"
    assert parse_ps("") == {}


def test_compose_binds_loopback_only():
    text = COMPOSE_FILE.read_text()
    assert '"127.0.0.1:4566:4566"' in text and '"127.0.0.1:5050:5000"' in text
    assert "@sha256:" in text


def fake_stack(monkeypatch, states, orphan_errors=()):
    calls = []
    monkeypatch.setattr(stack, "require_docker", lambda: None)
    monkeypatch.setattr(stack, "service_states", lambda: states)
    monkeypatch.setattr(stack, "port_free", lambda port, host: True)
    monkeypatch.setattr(stack, "compose", lambda *args: calls.append(("compose", *args)) or "")
    monkeypatch.setattr(stack, "docker", lambda *args: "sha" if args[:2] == ("image", "ls") else "")

    def remove_orphans():
        calls.append(("remove_orphans",))
        return Orphans([], [], [], list(orphan_errors))

    monkeypatch.setattr(stack, "remove_orphans", remove_orphans)
    return calls


def test_up_leaves_instances_alone_while_floci_runs(monkeypatch):
    states = {"floci": {"State": "running", "Health": "healthy"}, "moto": {"State": "exited", "Health": ""}}
    calls = fake_stack(monkeypatch, states)
    stack.up(log=lambda line: None)
    assert ("remove_orphans",) not in calls and ("compose", "up", "-d", "--wait") in calls


def test_up_cleans_orphans_when_floci_is_down(monkeypatch):
    calls = fake_stack(monkeypatch, {}, orphan_errors=["stuck network"])
    logs = []
    stack.up(log=logs.append)
    # The stopped Floci container goes first so it holds no VPC network when it comes back.
    assert calls[:2] == [("compose", "rm", "-s", "-f", "floci"), ("remove_orphans",)]
    assert "warning: stuck network" in logs


def test_recreate_floci_removes_the_container_instead_of_restarting_it(monkeypatch):
    calls = fake_stack(monkeypatch, {})
    stack.recreate_floci()
    assert calls == [
        ("compose", "rm", "-s", "-f", "floci"),
        ("remove_orphans",),
        ("compose", "up", "-d", "--wait", "floci"),
    ]


def test_down_finishes_compose_down_then_reports_stuck_resources(monkeypatch):
    calls = fake_stack(monkeypatch, {}, orphan_errors=["stuck network"])
    with pytest.raises(DockerError, match="stuck network"):
        stack.down(log=lambda line: None)
    assert ("compose", "down", "-v", "--remove-orphans") in calls


def test_up_recreates_floci_that_is_healthy_but_unreachable_from_the_host(monkeypatch):
    healthy = {"State": "running", "Health": "healthy"}
    calls = fake_stack(monkeypatch, {"floci": healthy, "moto": healthy})
    monkeypatch.setattr(stack, "reachable", lambda name: False)
    stack.up(log=lambda line: None)
    assert calls == [
        ("compose", "rm", "-s", "-f", "floci"),
        ("remove_orphans",),
        ("compose", "up", "-d", "--wait", "floci"),
    ]


def test_amazon_linux_2023_amis_run_the_prebuilt_image_for_their_architecture():
    catalog = yaml.safe_load((COMPOSE_FILE.parent / "ec2-image-catalog.yaml").read_text())
    # No architecture to pick a local tag by, so unknown AMIs keep the pullable upstream image.
    assert catalog["defaultDockerImage"] == "public.ecr.aws/amazonlinux/amazonlinux:2023"
    al2023 = [i for i in catalog["images"] if i["dockerImage"].startswith("cloudy-labs/al2023:")]
    assert {i["imageId"] for i in al2023} >= {"ami-amazonlinux2023-arm64", "ami-0abcdef1234567891"}
    platforms = {"x86_64": "linux/amd64", "arm64": "linux/arm64"}
    for image in al2023:
        assert stack.AL2023_IMAGES[image["dockerImage"]] == platforms[image["architecture"]]
    assert not any("amazonlinux:2023" in i["dockerImage"] for i in catalog["images"])
    assert (stack.AL2023_DIR / "Dockerfile").is_file()


def test_compose_mounts_the_catalog_floci_is_told_to_read():
    floci = yaml.safe_load(COMPOSE_FILE.read_text())["services"]["floci"]
    path = floci["environment"]["FLOCI_SERVICES_EC2_IMAGE_CATALOG_PATH"]
    assert f"./ec2-image-catalog.yaml:{path}:ro" in floci["volumes"]


def test_up_builds_the_al2023_image_only_when_missing(monkeypatch):
    calls = fake_stack(monkeypatch, {})
    built = []
    monkeypatch.setattr(stack, "_have_image", lambda ref: ref != "cloudy-labs/al2023:1-x86_64")
    monkeypatch.setattr(stack, "docker", lambda *args: built.append(args) or "")
    stack.up(log=lambda line: None)
    assert built == [
        ("build", "-q", "--platform", "linux/amd64", "-t", "cloudy-labs/al2023:1-x86_64", str(stack.AL2023_DIR))
    ]
    assert ("compose", "up", "-d", "--wait") in calls
