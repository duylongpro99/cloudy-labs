"""Static reachability: can traffic from one resource reach another, judged from configuration only.

The analysis walks security groups, network ACLs, route tables, gateways, peerings and Transit
Gateway route tables in the collected graph. It never sends a packet, so its answer is labelled
"analysed", not "observed".
"""

from cloudy_labs.reachability.analyze import analyze, resolve_endpoint
from cloudy_labs.reachability.model import EndpointError, Hop, Reachability

# Checks only report reachability as information until the scenario table and an end-to-end run on
# Floci have shown the analysis agrees with AWS; then grading is switched on here.
GRADING_ENABLED = True

# What the analysis reads. Checks collect these kinds for the whole region.
NETWORK_KINDS = (
    "vpc", "az", "subnet-public", "subnet-private", "igw", "nat", "route-table", "security-group",
    "instance", "elastic-ip", "network-acl", "vpc-endpoint", "vpc-peering", "transit-gateway",
    "tgw-attachment", "tgw-route-table", "network-interface", "prefix-list", "lambda-function",
    "db-subnet-group", "db-instance",
)

__all__ = ["GRADING_ENABLED", "NETWORK_KINDS", "EndpointError", "Hop", "Reachability", "analyze", "resolve_endpoint"]
