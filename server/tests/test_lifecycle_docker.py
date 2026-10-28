"""End-to-end lifecycle against the real emulator stack. Run with `uv run pytest -m docker`."""

import shutil
import sqlite3
import time
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


def ec2():
    return boto3.client(
        "ec2", endpoint_url="http://127.0.0.1:4566", region_name="us-east-1",
        aws_access_key_id="test", aws_secret_access_key="test",
    )


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
