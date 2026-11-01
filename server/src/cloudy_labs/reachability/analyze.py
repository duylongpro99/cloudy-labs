"""Walk a flow through the collected configuration and say where it is stopped, if anywhere.

Order of a flow from a resource in a subnet:
1. the source's security groups (egress);
2. the source subnet's NACL, outbound plus the inbound return on ephemeral ports;
3. route tables, by longest prefix: local, internet gateway, NAT gateway, peering, Transit Gateway,
   network interface or instance, gateway endpoint;
4. coming from the internet: the destination needs a public IP and a route back to an attached IGW;
5. the destination subnet's NACL, inbound plus the outbound return, then its security groups.

NACLs are only crossed between subnets. Return routes are checked for peering and Transit Gateway,
where a one-sided route is the usual mistake.
"""

from __future__ import annotations

from typing import Any

from cloudy_labs.graph.schema import ResourceGraph
from cloudy_labs.reachability import nacl, routes, sg
from cloudy_labs.reachability.model import (
    ANY, SUBNET_KINDS, Endpoint, EndpointError, Hop, Index, Network, Reachability, contains, net,
)

MAX_HOPS = 32
ENDPOINT_KINDS = ("instance", "network-interface", "lambda-function", "db-instance", "vpc-endpoint")


class _Blocked(Exception):
    pass


def _host(index: Index, subnet: str | None, ip: Any) -> Network:
    """The host's /32 when its IP lies in its subnet, else the whole subnet."""
    cidr = index.subnet_cidr(subnet)
    addr = net(ip)
    if addr is not None and (cidr is None or contains(cidr, addr)):
        return addr
    return cidr or ANY


def _node_endpoint(index: Index, node: Any, text: str) -> Endpoint:
    p, kind = node.props, node.kind
    groups = index.groups_of(node.id)
    if kind in ("instance", "network-interface"):
        subnet = index.ancestor(node.id, *SUBNET_KINDS)
        return Endpoint(text, kind, _host(index, subnet, p.get("privateIp")), node.id, subnet,
                        index.ancestor(subnet, "vpc"), groups, bool(p.get("hasPublicIp")))
    if kind == "lambda-function":
        subnets = p.get("subnets") or []
        if not subnets:
            raise EndpointError(f"{text}: the function is not in a VPC")
        subnet = subnets[0]
        return Endpoint(text, kind, index.subnet_cidr(subnet) or ANY, node.id, subnet, index.ancestor(subnet, "vpc"), groups)
    if kind == "db-instance":
        group = index.ancestor(node.id, "db-subnet-group")
        members = index.props(group).get("subnets") or []
        in_az = [s for s in members if index.props(s).get("az") == p.get("az")]
        subnet = (in_az or members or [None])[0]
        if subnet is None:
            raise EndpointError(f"{text}: the database has no subnet group in the graph")
        return Endpoint(text, kind, index.subnet_cidr(subnet) or ANY, node.id, subnet, index.ancestor(subnet, "vpc"),
                        groups, bool(p.get("publiclyAccessible")))
    # vpc-endpoint
    vpc = index.ancestor(node.id, "vpc")
    if str(p.get("type", "")).lower() == "gateway":
        return Endpoint(text, kind, ANY, node.id, None, vpc, (), False, gateway_endpoint=node.id)
    subnets = p.get("subnets") or []
    subnet = subnets[0] if subnets else None
    return Endpoint(text, kind, index.subnet_cidr(subnet) or ANY, node.id, subnet, vpc, groups)


def resolve_endpoint(index: Index | ResourceGraph, text: str) -> Endpoint:
    """A resource id or name, `internet`, or an IPv4 address or CIDR."""
    index = index if isinstance(index, Index) else Index(index)
    text = str(text).strip()
    if text.lower() == "internet":
        return Endpoint("internet", "internet", ANY, public=True)
    node = index.nodes.get(text)
    if node is None:
        named = [n for n in index.of_kind(*ENDPOINT_KINDS) if n.label == text]
        if len(named) > 1:
            raise EndpointError(f"{text}: more than one resource has this name; use its id")
        node = named[0] if named else None
    if node is not None:
        if node.kind not in ENDPOINT_KINDS:
            raise EndpointError(f"{text}: a {node.kind} is not an end of a flow")
        return _node_endpoint(index, node, text)
    address = net(text)
    if address is None:
        raise EndpointError(f"{text}: no resource has this id or name, and it is not an IPv4 address")
    subnet = index.subnet_at(address)
    if subnet is None:
        return Endpoint(text, "address", address, public=True)  # somewhere outside every VPC
    return Endpoint(text, "address", address, subnet=subnet, vpc=index.ancestor(subnet, "vpc"))


class _Walk:
    def __init__(self, index: Index, src: Endpoint, dst: Endpoint, port: int, proto: str):
        self.index, self.src, self.dst, self.port, self.proto = index, src, dst, port, sg.proto_number(proto)
        self.hops: list[Hop] = []
        self.visited: set[str] = set()
        # What the destination sees as the source; a NAT gateway changes it.
        self.from_net, self.from_groups = src.network, src.groups

    # -- hops
    def _hop(self, rid: str, verdict: str, reason: str, rule: str | None = None) -> None:
        self.hops.append(Hop(rid, self.index.kind(rid) or "endpoint", verdict, reason, rule))

    def allow(self, rid: str, rule: str | None = None) -> None:
        self._hop(rid, "allow", "allowed", rule)

    def forward(self, rid: str, rule: str | None = None) -> None:
        self._hop(rid, "forward", "routed", rule)

    def deny(self, rid: str, reason: str, rule: str | None = None) -> None:
        self._hop(rid, "deny", reason, rule)
        raise _Blocked()

    def run(self) -> Reachability:
        try:
            self._go()
        except _Blocked:
            last = self.hops[-1]
            return Reachability(False, self.hops, last.resource_id, last.reason)
        return Reachability(True, self.hops)

    # -- steps
    def _go(self) -> None:
        s, d = self.src, self.dst
        if s.groups:
            ok, gid, rule = sg.check(self.index, s.groups, "egress", d, self.port, self.proto)
            self.allow(gid, rule) if ok else self.deny(gid, "no-matching-rule")
        if s.subnet is None:
            self._from_internet()
            return
        if d.subnet == s.subnet and d.gateway_endpoint is None:
            self._arrive(crossed=False)
            return
        self._route(s.subnet, public=s.public)

    def _leave(self, subnet: str) -> None:
        acl = nacl.acl_of(self.index, subnet)
        ok, rule, reason = nacl.check(self.index, acl, True, self.dst.network, (self.port, self.port), self.proto)
        if not ok:
            self.deny(acl, reason, rule)
        ok, back, _ = nacl.check(self.index, acl, False, self.dst.network, nacl.EPHEMERAL, self.proto)
        if not ok:
            self.deny(acl, "return-denied", back)
        if acl:
            self.allow(acl, rule)

    def _arrive(self, crossed: bool = True) -> None:
        d = self.dst
        if crossed and d.subnet:
            acl = nacl.acl_of(self.index, d.subnet)
            ok, rule, reason = nacl.check(self.index, acl, False, self.from_net, (self.port, self.port), self.proto)
            if not ok:
                self.deny(acl, reason, rule)
            ok, back, _ = nacl.check(self.index, acl, True, self.from_net, nacl.EPHEMERAL, self.proto)
            if not ok:
                self.deny(acl, "return-denied", back)
            if acl:
                self.allow(acl, rule)
        if d.groups:
            peer = Endpoint(self.src.label, self.src.kind, self.from_net, groups=self.from_groups)
            ok, gid, rule = sg.check(self.index, d.groups, "ingress", peer, self.port, self.proto)
            self.allow(gid, rule) if ok else self.deny(gid, "no-matching-rule")
        self._hop(d.node_id or d.label, "allow", "delivered")

    def _seen(self, rid: str) -> None:
        if rid in self.visited:
            self.deny(rid, "loop-detected")
        self.visited.add(rid)

    def _route(self, subnet: str, public: bool) -> None:
        d, ix = self.dst, self.index
        self._leave(subnet)
        for _ in range(MAX_HOPS):
            vpc = ix.ancestor(subnet, "vpc")
            rt = routes.table_of(ix, subnet)
            if rt is None:
                self.deny(subnet, "no-route")
            self._seen(rt)
            if d.gateway_endpoint:
                if ix.ancestor(d.gateway_endpoint, "vpc") == vpc and rt in (ix.props(d.gateway_endpoint).get("routeTables") or []):
                    self.forward(rt, f"-> {d.gateway_endpoint}")
                    self._hop(d.gateway_endpoint, "allow", "delivered")
                    return
                self.deny(d.gateway_endpoint, "endpoint-not-associated", f"{ix.label(rt)} is not one of its route tables")
            route = routes.lookup(routes.table_routes(ix, rt), d.network)
            if route is None:
                self.deny(rt, "no-route", f"no route holds {d.network}")
            target, text = route.get("target"), f"{route.get('destination')} -> {route.get('target')}"
            if not target:
                self.deny(rt, "route-target-unknown", text)
            if route.get("state") == "blackhole":
                self.deny(rt, "blackhole", text)
            if target == "local":
                self.forward(rt, text)
                if d.subnet is None or ix.ancestor(d.subnet, "vpc") != vpc:
                    self._hop(d.node_id or d.label, "allow", "delivered")  # an address of this VPC with no subnet
                    return
                self._arrive()
                return
            if target not in ix.nodes:
                self.deny(rt, "blackhole", f"{text}: the target no longer exists")
            self.forward(rt, text)
            kind = ix.kind(target)
            if kind == "igw":
                self._via_igw(target, vpc, public)
                return
            if kind == "nat":
                if ix.props(target).get("state") not in (None, "available"):
                    self.deny(target, "blackhole", f"state {ix.props(target).get('state')}")
                self.forward(target)
                subnet, public = ix.ancestor(target, *SUBNET_KINDS), True
                self.from_net = net(ix.props(target).get("publicIp")) or ANY
                self.from_groups = ()
                self._leave(subnet)
                continue
            if kind == "vpc-peering":
                self._via_peering(target, vpc)
                return
            if kind == "transit-gateway":
                nxt = self._via_tgw(target, vpc)
                if nxt is None:
                    return
                subnet = nxt
                continue
            if kind in ("network-interface", "instance"):
                self.forward(target)
                subnet = ix.ancestor(target, *SUBNET_KINDS)
                continue
            self.deny(rt, "unsupported-target", text)
        self.deny(subnet, "loop-detected")

    def _via_igw(self, igw: str, vpc: str | None, public: bool) -> None:
        if self.index.props(igw).get("attachedVpc") != vpc:
            self.deny(igw, "blackhole", "not attached to this VPC")
        if not public:
            self.deny(self.src.node_id or self.src.label, "no-public-ip")
        self.forward(igw)
        if self.dst.subnet is None:
            self._hop(self.dst.node_id or self.dst.label, "allow", "delivered")
            return
        self._from_internet()

    def _from_internet(self) -> None:
        d, ix = self.dst, self.index
        if d.subnet is None:
            self._hop(d.node_id or d.label, "allow", "delivered")  # both ends outside every VPC
            return
        if not d.public:
            self.deny(d.node_id or d.label, "no-public-ip")
        igws = [g.id for g in ix.of_kind("igw") if g.props.get("attachedVpc") == d.vpc]
        if not igws:
            self.deny(d.vpc or d.label, "no-route", "no internet gateway is attached")
        rt = routes.table_of(ix, d.subnet)
        back = routes.lookup(routes.table_routes(ix, rt), self.from_net)
        if back is None or back.get("target") not in igws:
            self.deny(rt or d.subnet, "no-return-route", f"no route to {self.from_net} through {igws[0]}")
        self.forward(igws[0])
        self._arrive()

    def _return_route(self, via: str) -> None:
        rt = routes.table_of(self.index, self.dst.subnet)
        back = routes.lookup(routes.table_routes(self.index, rt), self.src.network)
        if back is None or back.get("target") != via:
            self.deny(rt or self.dst.subnet, "no-return-route", f"no route to {self.src.network} through {via}")

    def _via_peering(self, pcx: str, vpc: str | None) -> None:
        p = self.index.props(pcx)
        if p.get("status") != "active":
            self.deny(pcx, "blackhole", f"status {p.get('status')}")
        peer = p.get("accepterVpc") if p.get("requesterVpc") == vpc else p.get("requesterVpc")
        if self.dst.vpc != peer:
            self.deny(pcx, "not-transitive", "a peering only joins its own two VPCs")
        self.forward(pcx)
        self._return_route(pcx)
        self._arrive()

    def _attachment(self, tgw: str, vpc: str | None) -> str | None:
        for att in self.index.of_kind("tgw-attachment"):
            if self.index.ancestor(att.id, "vpc") == vpc and tgw in self.index.linked(att.id, "tgw-attached"):
                return att.id
        return None

    def _via_tgw(self, tgw: str, vpc: str | None) -> str | None:
        """Deliver through the Transit Gateway; the subnet to keep routing from when the destination is
        not in the VPC the TGW hands the flow to."""
        ix, d = self.index, self.dst
        att = self._attachment(tgw, vpc)
        if att is None:
            self.deny(tgw, "blackhole", "this VPC is not attached")
        self.forward(att)
        trt = ix.props(att).get("routeTable")
        if not trt or trt not in ix.nodes:
            self.deny(att, "no-route", "the attachment has no route table")
        self._seen(trt)
        route = routes.lookup(ix.props(trt).get("routes") or [], d.network)
        if route is None:
            self.deny(trt, "no-route", f"no route holds {d.network}")
        text = f"{route.get('destination')} -> {route.get('attachment') or 'blackhole'}"
        if route.get("state") == "blackhole" or route.get("attachment") not in ix.nodes:
            self.deny(trt, "blackhole", text)
        self.forward(trt, text)
        out = route["attachment"]
        self.forward(out)
        out_vpc = ix.ancestor(out, "vpc")
        if d.vpc is not None and d.vpc == out_vpc:
            self._return_route(tgw)
            back_rt = ix.props(out).get("routeTable")
            back = routes.lookup(ix.props(back_rt).get("routes") or [], self.src.network)
            if back is None or back.get("state") == "blackhole" or ix.ancestor(back.get("attachment"), "vpc") != self.src.vpc:
                self.deny(back_rt or out, "no-return-route", f"no route to {self.src.network} back to the source VPC")
            self._arrive()
            return None
        subnets = ix.props(out).get("subnets") or []
        if not subnets:
            self.deny(out, "no-route", "the attachment has no subnet")
        return subnets[0]


def analyze(graph: ResourceGraph | Index, src: str | Endpoint, dst: str | Endpoint, port: int, proto: str = "tcp") -> Reachability:
    """Whether `src` can open a flow to `dst` on `port`/`proto`, judged from configuration. Raises
    EndpointError for an end that is neither a resource of the graph nor an IPv4 address."""
    index = graph if isinstance(graph, Index) else Index(graph)
    s = src if isinstance(src, Endpoint) else resolve_endpoint(index, src)
    d = dst if isinstance(dst, Endpoint) else resolve_endpoint(index, dst)
    return _Walk(index, s, d, int(port), proto).run()
