"""Route tables: which table a subnet uses and the longest-prefix route for a destination."""

from __future__ import annotations

from cloudy_labs.reachability.model import Index, Network, contains, net


def table_of(index: Index, subnet: str) -> str | None:
    """The table explicitly associated with `subnet`, else the main table of its VPC."""
    vpc = index.ancestor(subnet, "vpc")
    main = None
    for rt in index.of_kind("route-table"):
        assocs = rt.props.get("associations") or []
        if any(a.get("subnet") == subnet for a in assocs):
            return rt.id
        if index.parent.get(rt.id) == vpc and (rt.props.get("main") or any(a.get("main") for a in assocs)):
            main = rt.id
    return main


def lookup(routes: list[dict], destination: Network) -> dict | None:
    """The most specific IPv4 route holding the whole destination; prefix-list routes are skipped."""
    best: tuple[int, dict] | None = None
    for r in routes or []:
        dest = net(r.get("destination"))
        if contains(dest, destination) and (best is None or dest.prefixlen > best[0]):
            best = (dest.prefixlen, r)
    return best[1] if best else None


def table_routes(index: Index, table: str | None) -> list[dict]:
    return index.props(table).get("routes") or []
