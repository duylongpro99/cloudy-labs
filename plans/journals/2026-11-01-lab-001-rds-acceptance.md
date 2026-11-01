---
title: "Lab-001 RDS acceptance on Floci"
date: 2026-11-01
summary: "Lab-001 (RDS MySQL and Aurora) now runs end to end on Floci through the builder and the terminal, and passes 12 of 12 checks both ways. Running it exposed three platform gaps, all fixed: storage fields, a default Aurora refuses, and `aws ... wait` in coverage."
---

# Lab-001 RDS acceptance on Floci

## What happened
The user downloaded the lab page and imported it into `labs/lab-001/content/` (gitignored). We wrote our own `lab.yaml`, `checks.py` and target: 7 tasks, 13 checks and 13 target nodes. The lab was built twice.
- Builder over `/api/run`: 12/12 passed.
- Terminal with the AWS CLI only: 12/12 passed. The twin bound all 13 nodes with no ghosts.
- Reset left only the setup network.

The chat run did not happen because no LLM provider is configured.

## What the lab exposed
- **The builder could not make the lab's MySQL instance.** `create-db-instance` had no `StorageType` or `MaxAllocatedStorage` field.
- **A default broke Aurora.** `AllocatedStorage: 20` was forced onto Aurora members, which AWS refuses. That default was removed, and the op note now says which fields belong to a standalone instance.
- **Coverage reported a false gap for `aws rds wait db-instance-available`.** The extractor now maps a CLI waiter to the describe API it polls, using botocore's waiter model.
- **The leak check flagged the plan.** The lab's 9-word URL slug counts as an 8-word run of lab content. The plan now names the lab `lab-001`.

## Floci facts learned
- StorageType is always `gp2`, on both create and modify. This is the new caveat `rds-storage-type-gp2`, and the gp3 check is INFO only.
- `failover-db-cluster` only swaps `IsClusterWriter`.
- The Aurora cluster's security group is ignored.
- Instances are `available` immediately.

## Open
- ~~The SG ingress op in the builder takes a CIDR, not a source SG. There is also no failover op, so the lab needs the terminal for those two steps.~~ Resolved the same day: the ingress op takes a source SG and the registry has `failover-db-cluster`; lab-001 passes 12/12 through the builder alone.
- The researcher's catalog CSV labels lab-001 as a CIDR lab, but the site's lab-001 is RDS. The CSV is not re-scraped (user decision).

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
