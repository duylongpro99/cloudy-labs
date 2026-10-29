from cloudy_labs.emulator import orphans


def fake_docker(calls, listing):
    def docker(*args):
        calls.append(args)
        if args[:2] == ("ps", "-a"):
            return listing.get("forwarders", "") if "name=floci-aws-ec2-fwd-" in args else listing["containers"]
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
        "networks": "floci-aws-vpc-4567-us-east-1-vpc-1\n",
        "volumes": "floci-aws-ec2-volumes\n",
        "forwarders": "floci-aws-ec2-fwd-i-1-80\n",
    }
    monkeypatch.setattr(orphans, "docker", fake_docker(calls, listing))
    found = orphans.remove_orphans()
    assert len(found) == 5
    removals = [c for c in calls if c[0] == "rm" or c[1] == "rm"]
    assert removals == [
        ("rm", "-f", "-v", "floci-aws-ec2-i-1", "floci-aws-ec2-volume-helper", "floci-aws-ec2-fwd-i-1-80"),
        ("network", "rm", "floci-aws-vpc-4567-us-east-1-vpc-1"),
        ("volume", "rm", "-f", "floci-aws-ec2-volumes"),
    ]
    listings = [c for c in calls if c not in removals and "name=floci-aws-ec2-fwd-" not in c]
    assert len(listings) == 3 and all("label=io.floci.owner=4567" in c and "label=io.floci=aws" in c for c in listings)


def test_nothing_to_remove(monkeypatch):
    calls = []
    monkeypatch.setattr(orphans, "docker", fake_docker(calls, {"containers": "", "networks": "\n", "volumes": ""}))
    assert len(orphans.remove_orphans()) == 0
    assert len(calls) == 3  # only the listings: containers, networks, volumes; no instance, no forwarder


def test_forwarders_of_another_flocis_instances_stay(monkeypatch):
    calls = []
    listing = {
        "containers": "floci-aws-ec2-i-1\n",
        "networks": "",
        "volumes": "",
        # i-10 shares a prefix with i-1 and, like i-2, belongs to a Floci labctl does not own.
        "forwarders": "floci-aws-ec2-fwd-i-1-80\nfloci-aws-ec2-fwd-i-10-80\nfloci-aws-ec2-fwd-i-2-80\n",
    }
    monkeypatch.setattr(orphans, "docker", fake_docker(calls, listing))
    assert orphans.find_orphans().containers == ["floci-aws-ec2-i-1", "floci-aws-ec2-fwd-i-1-80"]


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
