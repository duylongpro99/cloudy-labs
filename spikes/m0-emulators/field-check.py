#!/usr/bin/env python3
"""Compare recorded describe-* output with the fields the resource graph needs (PRD F2.4).

Usage: python3 field-check.py [out-dir]
Reads out/<backend>/*.json written by lab-06-07.sh and prints, per backend, every
required field as "có" (present and correct), "thiếu" (missing or empty) or
"sai" (present but contradicts what the lab created), then a resource x backend summary.
"""
import ipaddress
import json
import sys
from pathlib import Path

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "out"
OK, MISSING, WRONG = "có", "thiếu", "sai"


def load(backend_dir: Path, command: str):
    match = sorted(backend_dir.glob(f"*-{command}.json"))
    if not match:
        return None
    try:
        return json.loads(match[0].read_text() or "null")
    except json.JSONDecodeError:
        return None


def empty(v):
    return v is None or v == "" or v == [] or v == {}


def verdict(value, expected_ok=True):
    """MISSING if empty; otherwise OK when expected_ok holds, else WRONG."""
    if empty(value) and value is not False:
        return MISSING
    return OK if expected_ok else WRONG


def has_tag(tags, key, value):
    return any(t.get("Key") == key and t.get("Value") == value for t in tags or [])


def has_rule(perms, port, cidr):
    return any(
        p.get("IpProtocol") in ("tcp", "6") and p.get("FromPort") == port and p.get("ToPort") == port
        and any(r.get("CidrIp") == cidr for r in p.get("IpRanges", []))
        for p in perms or []
    )


def check_backend(d: Path, ids: dict):
    rows = {}  # resource -> list of (field, status, note)

    def add(resource, field, status, note=""):
        rows.setdefault(resource, []).append((field, status, note))

    vpcs = (load(d, "describe-vpcs") or {}).get("Vpcs", [])
    vpc = next((v for v in vpcs if v.get("VpcId") == ids["vpc"]), {})
    add("VPC", "VpcId", verdict(vpc.get("VpcId")))
    add("VPC", "CidrBlock", verdict(vpc.get("CidrBlock"), vpc.get("CidrBlock") == "10.0.0.0/16"), vpc.get("CidrBlock", ""))
    add("VPC", "Tags", verdict(vpc.get("Tags"), has_tag(vpc.get("Tags"), "Name", "lab06-vpc")))

    azs = (load(d, "describe-availability-zones") or {}).get("AvailabilityZones", [])
    names = {z.get("ZoneName") for z in azs}
    add("AZ", "ZoneName", verdict(azs and names, {"us-east-1a", "us-east-1b"} <= names), f"{len(azs)} AZ")
    add("AZ", "ZoneId", verdict([z.get("ZoneId") for z in azs if z.get("ZoneId")]))

    subnets = {s["SubnetId"]: s for s in (load(d, "describe-subnets") or {}).get("Subnets", [])}
    expect = {
        ids["public_subnets"][0]: ("10.0.1.0/24", "us-east-1a", True),
        ids["public_subnets"][1]: ("10.0.2.0/24", "us-east-1b", True),
        ids["private_subnets"][0]: ("10.0.11.0/24", "us-east-1a", False),
        ids["private_subnets"][1]: ("10.0.12.0/24", "us-east-1b", False),
    }
    found = [subnets.get(sid, {}) for sid in expect]
    add("Subnet", "SubnetId", verdict([s for s in found if s], len([s for s in found if s]) == 4), f"{len(subnets)} trong VPC")
    add("Subnet", "VpcId", verdict([s.get("VpcId") for s in found if s.get("VpcId")], all(s.get("VpcId") == ids["vpc"] for s in found)))
    add("Subnet", "CidrBlock", verdict([s.get("CidrBlock") for s in found if s.get("CidrBlock")],
                                       all(s.get("CidrBlock") == e[0] for s, e in zip(found, expect.values()))))
    add("Subnet", "AvailabilityZone", verdict([s.get("AvailabilityZone") for s in found if s.get("AvailabilityZone")],
                                              all(s.get("AvailabilityZone") == e[1] for s, e in zip(found, expect.values()))))
    mpi = [s.get("MapPublicIpOnLaunch") for s in found]
    add("Subnet", "MapPublicIpOnLaunch", MISSING if any(v is None for v in mpi) else
        (OK if mpi == [e[2] for e in expect.values()] else WRONG), str(mpi))

    igws = (load(d, "describe-internet-gateways") or {}).get("InternetGateways", [])
    igw = next((g for g in igws if g.get("InternetGatewayId") == ids["igw"]), {})
    att = (igw.get("Attachments") or [{}])[0]
    add("Internet Gateway", "InternetGatewayId", verdict(igw.get("InternetGatewayId")))
    add("Internet Gateway", "Attachments[].VpcId", verdict(att.get("VpcId"), att.get("VpcId") == ids["vpc"]))
    # Real AWS reports "available" for an attached IGW.
    add("Internet Gateway", "Attachments[].State", verdict(att.get("State"), att.get("State") == "available"), att.get("State", ""))

    nats = (load(d, "describe-nat-gateways") or {}).get("NatGateways", [])
    nat = next((n for n in nats if n.get("NatGatewayId") == ids["nat"]), {})
    addrs = nat.get("NatGatewayAddresses") or []
    add("NAT Gateway", "NatGatewayId", verdict(nat.get("NatGatewayId")))
    add("NAT Gateway", "SubnetId", verdict(nat.get("SubnetId"), nat.get("SubnetId") == ids["public_subnets"][0]))
    add("NAT Gateway", "VpcId", verdict(nat.get("VpcId"), nat.get("VpcId") == ids["vpc"]))
    add("NAT Gateway", "State", verdict(nat.get("State"), nat.get("State") == "available"), nat.get("State", ""))
    add("NAT Gateway", "NatGatewayAddresses", verdict(addrs, any(a.get("AllocationId") == ids["eip"] and a.get("PublicIp") for a in addrs)),
        ",".join(a.get("PublicIp", "?") for a in addrs))

    rts = {r["RouteTableId"]: r for r in (load(d, "describe-route-tables") or {}).get("RouteTables", [])}
    pub, pri = rts.get(ids["rt_public"], {}), rts.get(ids["rt_private"], {})
    add("Route Table", "RouteTableId", verdict(pub and pri), f"{len(rts)} trong VPC")
    add("Route Table", "VpcId", verdict(pub.get("VpcId"), pub.get("VpcId") == ids["vpc"] == pri.get("VpcId")))
    assoc = lambda rt: {a.get("SubnetId") for a in rt.get("Associations", []) if a.get("SubnetId")}
    add("Route Table", "Associations[].SubnetId", verdict(assoc(pub) | assoc(pri),
        assoc(pub) == set(ids["public_subnets"]) and assoc(pri) == set(ids["private_subnets"])))
    mains = [a for r in rts.values() for a in r.get("Associations", []) if a.get("Main") is True]
    add("Route Table", "Associations[].Main", verdict(mains, len(mains) == 1), f"{len(mains)} main")
    default_route = lambda rt: next((x for x in rt.get("Routes", []) if x.get("DestinationCidrBlock") == "0.0.0.0/0"), {})
    pr, vr = default_route(pub), default_route(pri)
    local = any(x.get("GatewayId") == "local" for x in pub.get("Routes", []))
    add("Route Table", "Routes[].DestinationCidrBlock", verdict(pr and vr, local), "có route local" if local else "không có route local")
    add("Route Table", "Routes[].GatewayId", verdict(pr.get("GatewayId"), pr.get("GatewayId") == ids["igw"]))
    add("Route Table", "Routes[].NatGatewayId", verdict(vr.get("NatGatewayId"), vr.get("NatGatewayId") == ids["nat"]))

    sgs = (load(d, "describe-security-groups") or {}).get("SecurityGroups", [])
    sg = next((g for g in sgs if g.get("GroupId") == ids["sg"]), {})
    add("Security Group", "GroupId", verdict(sg.get("GroupId")), f"{len(sgs)} trong VPC")
    add("Security Group", "VpcId", verdict(sg.get("VpcId"), sg.get("VpcId") == ids["vpc"]))
    ing = sg.get("IpPermissions")
    add("Security Group", "IpPermissions", verdict(ing, has_rule(ing, 22, "203.0.113.10/32") and has_rule(ing, 80, "0.0.0.0/0")))
    eg = sg.get("IpPermissionsEgress")
    add("Security Group", "IpPermissionsEgress", verdict(eg, any(p.get("IpProtocol") == "-1" for p in eg or [])))

    kps = (load(d, "describe-key-pairs") or {}).get("KeyPairs", [])
    kp = next((k for k in kps if k.get("KeyName") == "lab07-key"), {})
    add("Key Pair", "KeyName", verdict(kp.get("KeyName")))
    add("Key Pair", "KeyPairId", verdict(kp.get("KeyPairId")))

    res = (load(d, "describe-instances") or {}).get("Reservations", [])
    inst = next((i for r in res for i in r.get("Instances", []) if i.get("InstanceId") == ids["instance"]), {})
    state = (inst.get("State") or {}).get("Name")
    add("Instance", "InstanceId", verdict(inst.get("InstanceId")))
    add("Instance", "State.Name", verdict(state, state == "running"), state or "")
    add("Instance", "SubnetId", verdict(inst.get("SubnetId"), inst.get("SubnetId") == ids["public_subnets"][0]))
    add("Instance", "VpcId", verdict(inst.get("VpcId"), inst.get("VpcId") == ids["vpc"]))
    add("Instance", "SecurityGroups", verdict(inst.get("SecurityGroups"), any(g.get("GroupId") == ids["sg"] for g in inst.get("SecurityGroups") or [])))
    add("Instance", "PublicIpAddress", verdict(inst.get("PublicIpAddress")), inst.get("PublicIpAddress", ""))
    priv = inst.get("PrivateIpAddress")
    in_subnet = bool(priv) and ipaddress.ip_address(priv) in ipaddress.ip_network("10.0.1.0/24")
    add("Instance", "PrivateIpAddress", verdict(priv, in_subnet), priv or "")
    add("Instance", "KeyName", verdict(inst.get("KeyName"), inst.get("KeyName") == "lab07-key"))
    return rows


def main():
    backends = sorted(p for p in OUT.iterdir() if (p / "ids.json").exists())
    if not backends:
        sys.exit(f"no out/<backend>/ids.json under {OUT}")
    results = {b.name: check_backend(b, json.loads((b / "ids.json").read_text())) for b in backends}

    for name, rows in results.items():
        print(f"\n## {name}\n\n| Tài nguyên | Trường | Kết quả | Ghi chú |\n|---|---|---|---|")
        for resource, fields in rows.items():
            for field, status, note in fields:
                print(f"| {resource} | `{field}` | {status} | {note} |")

    print("\n## Tổng hợp\n\n| Tài nguyên | " + " | ".join(results) + " |\n|---|" + "---|" * len(results))
    for resource in next(iter(results.values())):
        cells = []
        for rows in results.values():
            fields = rows[resource]
            bad = [f"{f} {s}" for f, s, _ in fields if s != OK]
            cells.append(f"{len(fields) - len(bad)}/{len(fields)} có" + (f" ({'; '.join(bad)})" if bad else ""))
        print(f"| {resource} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
