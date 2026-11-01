"""Security groups: stateful, allow-only. Traffic passes when any rule of any attached group allows it."""

from __future__ import annotations

from cloudy_labs.reachability.model import ANY, Endpoint, Index, contains, net

PROTOCOLS = {"tcp": "6", "udp": "17", "icmp": "1", "-1": "-1", "all": "-1"}


def proto_number(proto: object) -> str:
    text = str(proto).lower()
    return PROTOCOLS.get(text, text)


def port_matches(proto: str, low: object, high: object, port: int) -> bool:
    """`port` within [low, high]; ICMP rules carry a type and code, not ports, and match any ICMP flow."""
    if proto in ("-1", "1") or low is None or high is None:
        return True
    lo, hi = int(low), int(high)
    return lo == -1 or lo <= port <= hi


def rule_matches(rule_proto: object, proto: str) -> bool:
    rp = proto_number(rule_proto)
    return rp == "-1" or rp == proto


def _source_matches(index: Index, source: str, peer: Endpoint) -> bool:
    if source.startswith("sg-"):
        return source in peer.groups
    if source.startswith("pl-"):
        cidrs = index.props(source).get("cidrs")
        if index.kind(source) != "prefix-list" or cidrs is None:
            # An AWS-managed list (S3, DynamoDB...) is not collected: it stands for the service.
            return peer.gateway_endpoint is not None
        return any(contains(net(c), peer.network) for c in cidrs)
    cidr = net(source)
    if peer.gateway_endpoint is not None:
        return cidr == ANY
    return contains(cidr, peer.network)


def check(index: Index, groups: tuple[str, ...], direction: str, peer: Endpoint, port: int, proto: str) -> tuple[bool, str, str | None]:
    """(allowed, group id that decided, rule text). `direction` is "ingress" or "egress"; `peer` is the
    other end. Denied flows name the first group, which is where the learner should look."""
    proto = proto_number(proto)
    for gid in groups:
        for i, rule in enumerate(index.props(gid).get(direction) or []):
            if not rule_matches(rule.get("protocol"), proto) or not port_matches(proto, rule.get("from"), rule.get("to"), port):
                continue
            for source in rule.get("sources") or []:
                if _source_matches(index, str(source), peer):
                    return True, gid, f"{direction}[{i}] {rule.get('protocol')} {rule.get('from')}-{rule.get('to')} {source}"
    return False, groups[0], None
