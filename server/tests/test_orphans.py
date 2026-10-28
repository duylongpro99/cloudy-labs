from cloudy_labs.emulator import orphans


def fake_docker(calls, listing):
    def docker(*args):
        calls.append(args)
        if args[:2] == ("ps", "-a"):
            return listing["containers"]
        if args[:2] == ("network", "ls"):
            return listing["networks"]
        if args[:2] == ("volume", "ls"):
            return listing["volumes"]
        return ""

    return docker


def test_remove_orphans_removes_containers_before_networks_and_volumes(monkeypatch):
    calls = []
    listing = {
        "containers": "floci-aws-ec2-i-1\nfloci-aws-ec2-volume-helper\n",
        "networks": "floci-aws-vpc-4566-us-east-1-vpc-1\n",
        "volumes": "floci-aws-ec2-volumes\n",
    }
    monkeypatch.setattr(orphans, "docker", fake_docker(calls, listing))
    found = orphans.remove_orphans()
    assert len(found) == 4
    removals = [c for c in calls if c[0] == "rm" or c[1] == "rm"]
    assert removals == [
        ("rm", "-f", "-v", "floci-aws-ec2-i-1", "floci-aws-ec2-volume-helper"),
        ("network", "rm", "floci-aws-vpc-4566-us-east-1-vpc-1"),
        ("volume", "rm", "-f", "floci-aws-ec2-volumes"),
    ]
    listings = [c for c in calls if c not in removals]
    assert all("label=io.floci.owner=4566" in c and "label=io.floci=aws" in c for c in listings)


def test_nothing_to_remove(monkeypatch):
    calls = []
    monkeypatch.setattr(orphans, "docker", fake_docker(calls, {"containers": "", "networks": "\n", "volumes": ""}))
    assert len(orphans.remove_orphans()) == 0
    assert len(calls) == 3  # only the three listings


def test_one_failed_removal_does_not_stop_the_rest(monkeypatch):
    calls = []
    listing = {"containers": "floci-aws-ec2-i-1\n", "networks": "floci-aws-vpc-1\n", "volumes": "floci-aws-ec2-volumes\n"}
    inner = fake_docker(calls, listing)

    def docker(*args):
        if args[:2] == ("network", "rm"):
            calls.append(args)
            raise orphans.DockerError("network floci-aws-vpc-1 has active endpoints")
        return inner(*args)

    monkeypatch.setattr(orphans, "docker", docker)
    found = orphans.remove_orphans()
    assert found.errors == ["network floci-aws-vpc-1 has active endpoints"]
    assert ("volume", "rm", "-f", "floci-aws-ec2-volumes") in calls
