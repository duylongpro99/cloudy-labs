"""End-to-end lifecycle against the real emulator stack. Run with `uv run pytest -m docker`."""

import json
import shutil
import sqlite3
import threading
import time
import urllib.request
from pathlib import Path

import boto3
import pytest
from botocore.exceptions import ClientError

from cloudy_labs.cli import main
from cloudy_labs.emulator.docker import docker, lines
from cloudy_labs.emulator.orphans import owner_filters
from cloudy_labs.providers import AwsProvider

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module")
def stack(tmp_path_factory, fixture_labs_root):
    home = tmp_path_factory.mktemp("home")
    labs = tmp_path_factory.mktemp("labs")
    shutil.copytree(fixture_labs_root / "fixture-vpc", labs / "fixture-vpc")
    moto_lab = labs / "fixture-moto"
    shutil.copytree(fixture_labs_root / "fixture-vpc", moto_lab)
    text = (moto_lab / "lab.yaml").read_text()
    (moto_lab / "lab.yaml").write_text(text.replace("id: fixture-vpc", "id: fixture-moto").replace("floci", "moto"))
    mp = pytest.MonkeyPatch()
    mp.setenv("CLOUDY_LABS_HOME", str(home))
    mp.setenv("CLOUDY_LABS_LABS_DIR", str(labs))
    mp.setenv("AWS_CONFIG_FILE", str(home / "aws-config"))  # `up` writes the lab profile here
    try:
        assert main(["up"]) == 0
        yield home
    finally:
        main(["down"])  # always, so a failing test leaves no containers behind
        mp.undo()


@pytest.fixture(autouse=True)
def isolated_home():
    """The module-scoped `stack` fixture owns CLOUDY_LABS_HOME here; do not swap it per test."""


@pytest.fixture(scope="module")
def fixture_labs_root():
    return Path(__file__).parent / "fixtures" / "labs"


def ec2(port: int = 4566):
    return boto3.client(
        "ec2", endpoint_url=f"http://127.0.0.1:{port}", region_name="us-east-1",
        aws_access_key_id="test", aws_secret_access_key="test",
    )


def test_api_tap_forwards_and_announces_writes(stack):
    events = []
    stream = urllib.request.urlopen("http://127.0.0.1:4568/events", timeout=5)
    assert stream.readline() == b": connected\n"

    def read():
        try:
            for line in stream:
                if line.startswith(b"data: "):
                    events.append((time.monotonic(), json.loads(line[6:])))
        except (OSError, ValueError):
            pass  # the test closed the stream

    threading.Thread(target=read, daemon=True).start()
    ec2().describe_vpcs()  # a read: no event
    vpc = ec2().create_vpc(CidrBlock="10.78.0.0/16")["Vpc"]["VpcId"]
    returned = time.monotonic()
    deadline = returned + 1
    while not events:
        assert time.monotonic() < deadline, "no CreateVpc event on the SSE stream within 1 s"
        time.sleep(0.01)
    assert [e["action"] for _, e in events] == ["CreateVpc"] and events[0][1]["write"] is True
    via_tap = ec2(4566).describe_vpcs(VpcIds=[vpc])["Vpcs"]
    direct = ec2(4567).describe_vpcs(VpcIds=[vpc])["Vpcs"]
    assert via_tap == direct
    stream.close()


def test_floci_lifecycle(stack, capsys):
    assert main(["start", "fixture-vpc"]) == 0
    assert main(["check", "fixture-vpc"]) == 1
    vpc = ec2().create_vpc(
        CidrBlock="10.77.0.0/16",
        TagSpecifications=[{"ResourceType": "vpc", "Tags": [{"Key": "lab", "Value": "fixture-vpc"}]}],
    )["Vpc"]["VpcId"]
    capsys.readouterr()
    assert main(["check", "fixture-vpc"]) == 0
    assert vpc in capsys.readouterr().out
    rows = sqlite3.connect(stack / "progress.db").execute("SELECT check_id, passed FROM check_runs").fetchall()
    assert rows == [("vpc-exists", 0), ("vpc-exists", 1)]

    assert main(["reset", "fixture-vpc"]) == 0
    assert main(["check", "fixture-vpc"]) == 1


def moto_ec2(env: dict[str, str]):
    return boto3.client(
        "ec2", endpoint_url=env["AWS_ENDPOINT_URL"], region_name="us-east-1",
        aws_access_key_id=env["AWS_ACCESS_KEY_ID"], aws_secret_access_key=env["AWS_SECRET_ACCESS_KEY"],
    )


def test_moto_enforces_iam_and_checks_as_the_admin_user(stack, capsys):
    assert main(["start", "fixture-moto"]) == 0
    env = AwsProvider("moto").env()
    assert env["AWS_ACCESS_KEY_ID"] != "test"
    with pytest.raises(ClientError, match="AuthFailure"):  # the fake keys no longer work
        moto_ec2(env | {"AWS_ACCESS_KEY_ID": "test", "AWS_SECRET_ACCESS_KEY": "test"}).describe_vpcs()
    moto_ec2(env).create_vpc(
        CidrBlock="10.77.0.0/16",
        TagSpecifications=[{"ResourceType": "vpc", "Tags": [{"Key": "lab", "Value": "fixture-vpc"}]}],
    )
    assert main(["check", "fixture-moto"]) == 0

    assert main(["reset", "fixture-moto"]) == 0
    with pytest.raises(ClientError, match="AuthFailure"):  # reset wiped the old admin user
        moto_ec2(env).describe_vpcs()
    assert main(["check", "fixture-moto"]) == 1  # new admin, empty account
    capsys.readouterr()


def test_down_leaves_nothing_behind(stack):
    # Leave an instance container and a VPC network running so down has orphans to clean.
    assert main(["start", "fixture-vpc"]) == 0
    client = ec2()
    vpc = client.create_vpc(CidrBlock="10.77.0.0/16")["Vpc"]["VpcId"]
    subnet = client.create_subnet(VpcId=vpc, CidrBlock="10.77.1.0/24")["Subnet"]["SubnetId"]
    client.run_instances(ImageId="ami-0abcdef1234567890", InstanceType="t3.micro", MinCount=1, MaxCount=1, SubnetId=subnet)
    f = owner_filters()
    deadline = time.monotonic() + 60
    while not lines(docker("ps", "-a", *f, "-q")):  # Floci creates the container asynchronously
        assert time.monotonic() < deadline, "Floci never created the instance container"
        time.sleep(1)
    assert main(["down"]) == 0
    assert lines(docker("ps", "-a", *f, "-q")) == []
    assert lines(docker("network", "ls", *f, "-q")) == []
    assert lines(docker("volume", "ls", *f, "-q")) == []
    assert lines(docker("ps", "-a", "--filter", "label=com.docker.compose.project=cloudy-labs", "-q")) == []
