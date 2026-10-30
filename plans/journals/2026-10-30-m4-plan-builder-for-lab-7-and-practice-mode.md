---
title: "M4 plan: builder for Lab 7 and practice mode"
date: 2026-10-30
summary: "Wrote 6-phase M4 plan using fixture-lab-07; EC2 ops, SG rules, key pair, practice mode via api-tap"
---

# M4 plan: builder for Lab 7 and practice mode

## What happened
Wrote `plans/261030-1045-m4-builder-lab-07/` (plan.md + 6 phases), mirroring the M3 layout. Real Lab 7 content does not exist, so the plan uses `fixture-lab-07` with a `setup` step that rebuilds the Lab 6 network after reset.

## Decision
- Key pair: stdout stays verbatim; browser builds `<name>.pem` from a Blob. Server never writes or logs the key.
- SSH (22) from 0.0.0.0/0 is blocked in validate with a teaching message.
- UserData: free textarea pre-filled from lab `builder.userData`, max 16 KB, non-blocking hint when binding 0.0.0.0:80 (Floci IMDS holds that port).
- Practice mode: no `/api/run`; panel waits with no timeout until the graph matches `practiceExpect` (kind + Name tag, or edge/prop).
- New expect shape `includes` for SG ingress; `result_id` must handle list indexes (`Instances.0.InstanceId`).

## Next steps
- Phase 2 first probes Floci for `modify-instance-attribute --groups` and key-pair tags (unverified).
- Phase 6 also settles the M3 open question on overlapping subnet CIDRs.
- Re-run e2e when real Lab 7 lands.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
