# Reachability: end-to-end on Floci

Date: 2026-10-31 21:40. Floci 2.3.0, region ap-southeast-2, emulator stack from `labctl up`.

## Setup

On a fresh Floci (`labctl down && labctl up`), the network was created and recorded:

```
uv run python scripts/record-floci-fixtures.py build-reachability
uv run python scripts/record-floci-fixtures.py record-reachability   # 33 calls; 91 nodes, 53 edges, no warnings
```

The scenario table `server/tests/fixtures/reachability/scenarios.yaml` (24 cases, each linked to AWS
docs) passes against that recording: `uv run pytest tests/test_reachability.py -q`, 33 passed.

## Live queries (no recording, no patches)

`CheckContext(client=AwsProvider("floci", "ap-southeast-2").client).graph(NETWORK_KINDS)` was
collected from the running emulator and analysed. Script: `reach-e2e.py` in the session scratchpad.

| Query | Result | Blocked at | Reason |
|---|---|---|---|
| internet → rx-web:22 | blocked | rx-sg-web | no-matching-rule |
| internet → rx-web:80 | ok | | |
| rx-web → rx-app:8080 | ok | | |
| rx-app → rx-db:5432 | ok | | |
| rx-web → rx-db:5432 | blocked | rx-sg-db | no-matching-rule |
| rx-app → internet:443 | ok | | |
| rx-black-host → internet:443 | blocked | rx-rt-a-black | blackhole |
| rx-web → rx-nacl-host:80 | blocked | rx-acl | return-denied |
| rx-app → rx-c-host:80 | blocked | rx-pcx-ab | not-transitive |
| rx-d-host → rx-e-host:80 | blocked | rx-rt-d-main | route-target-unknown |

All match the scenario table except the TGW case. On live Floci, the VPC route created with
`--transit-gateway-id` comes back with no target, so the analysis honestly reports
`route-target-unknown` instead of guessing. The recorded tests put the target back with
`patches.yaml`; see docs/emulator-differences.md.

## A change through the AWS CLI

```
aws ec2 authorize-security-group-ingress --group-id sg-0ce61b20372180cec --protocol tcp --port 22 --cidr 0.0.0.0/0
→ True
```

After this, internet → rx-web:22 is `ok` (reason `delivered`). The answer follows the change made
with the CLI.

## Decision

The scenario table is green and the live run agrees with it, so `GRADING_ENABLED` is set to `True`
in `server/src/cloudy_labs/reachability/__init__.py`. Rollback: set it back to `False`, and every
reachability check returns to `info`.
