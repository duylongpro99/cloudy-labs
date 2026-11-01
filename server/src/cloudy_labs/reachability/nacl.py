"""Network ACLs: stateless, ordered allow/deny rules on subnet boundaries.

An address or port range is reachable when some address and some port in it pass: the flow comes
from one host and one ephemeral port, and the analysis does not know which. Rules decide piecewise,
so evaluating each segment of the address range at each port boundary is exact.
"""

from __future__ import annotations

from cloudy_labs.reachability.model import Index, Network, net
from cloudy_labs.reachability.sg import port_matches, proto_number, rule_matches

EPHEMERAL = (1024, 65535)


def acl_of(index: Index, subnet: str) -> str | None:
    """The NACL associated with `subnet`, else its VPC's default one; None when none was collected."""
    vpc = index.ancestor(subnet, "vpc")
    default = None
    for acl in index.of_kind("network-acl"):
        if subnet in (acl.props.get("associations") or []):
            return acl.id
        if acl.props.get("isDefault") and index.parent.get(acl.id) == vpc:
            default = acl.id
    return default


def _ports(entries: list[dict], low: int, high: int) -> list[int]:
    points = {low, high}
    for e in entries:
        for p in e.get("port_range") or []:
            for q in (int(p) - 1, int(p), int(p) + 1):
                if low <= q <= high:
                    points.add(q)
    return sorted(points)


def _decide(entries: list[dict], peer: Network, port: int, proto: str) -> tuple[bool, dict | None]:
    remaining = [peer]
    denied_by = None
    for e in entries:
        cidr = net(e.get("cidr"))
        rng = e.get("port_range") or [None, None]
        if cidr is None or not rule_matches(e.get("protocol"), proto) or not port_matches(proto, rng[0], rng[1], port):
            continue
        inside = [part for part in remaining if part.overlaps(cidr)]
        if not inside:
            continue
        if e.get("action") == "allow":
            return True, e
        denied_by = denied_by or e
        rest: list[Network] = []
        for part in remaining:
            if not part.overlaps(cidr):
                rest.append(part)
            elif not part.subnet_of(cidr):
                rest.extend(part.address_exclude(cidr))
        remaining = rest
        if not remaining:
            break
    return False, denied_by


def check(index: Index, acl: str | None, egress: bool, peer: Network, ports: tuple[int, int], proto: str) -> tuple[bool, str | None, str]:
    """(allowed, rule text, reason) for traffic crossing `acl` in one direction. `peer` is the other
    end's address range: the destination when leaving, the source when entering."""
    if acl is None:
        return True, None, "allowed"
    proto = proto_number(proto)
    entries = sorted((e for e in index.props(acl).get("entries") or [] if bool(e.get("egress")) == egress),
                     key=lambda e: int(e.get("rule_number") or 0))
    first_deny = None
    for port in _ports(entries, *ports) if proto in ("6", "17") else [ports[0]]:
        allowed, entry = _decide(entries, peer, port, proto)
        if allowed:
            return True, f"#{entry['rule_number']} allow", "allowed"
        first_deny = first_deny or entry
    if first_deny is not None:
        return False, f"#{first_deny['rule_number']} deny", "denied-by-rule"
    return False, None, "no-matching-rule"
