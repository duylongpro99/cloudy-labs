---
title: "M7 implemented: lab coverage hardening"
date: 2026-11-01
summary: "Phases 1–10 of the lab-coverage plan are done and review findings are fixed. Phase 11 waits for the user to import lab-001 content. Floci timing flakes under load are left as they are."
---

# M7 implemented: lab coverage hardening

## What happened
Phases 1–10 of `plans/261031-1358-lab-coverage-hardening/` are finished. The resource registry now holds 51 kinds, and the builder ops are generated from botocore. The 16 legacy EC2 ops keep their hand-written argv. The 530-lab catalog now stands at ready 1, ready-with-caveats 468, blocked 61 and gap 0. Blocked mostly means Floci lacks the service (FSx, VPN, Direct Connect, EBS snapshots and similar). Phase 11 has run everything except the lab-001 RDS walkthrough, because `labs/lab-001/content/` has not been imported yet. Results are in `notes/e2e-results.md`.

## Review findings worth remembering
- The sanitizer saw list fields only as raw text, but the form sends lists as JSON text that `shapes` later parses into separate argv tokens. A `["file:///etc/hosts"]` value passed both checks. The rule now: check what will become a token, after the same parsing the argv builder does.
- botocore member `version` becomes the global `--version`, which prints the CLI version and exits 0 without sending anything. The test suite missed this because nothing failed. A test now checks every generated op flag against the CLI's global options. Only renames confirmed in `aws … help` were added. The CLI has no rename for `eks update-cluster-version`, so that op cannot be generated.
- The SigV4 signing name is shared across services (`rds`, `elasticloadbalancing`, `events`, `apigateway`). A first-wins map sent RDS writes to DocumentDB's kinds.
- `labctl env` printed moto admin keys. It now exports `AWS_PROFILE=lab` and unsets any old key variables.

## Friction
- The contract suite's 2.0 s latency limit flakes on this shared machine (load average 5–6, other projects' containers running). Each run, 2 of 105 kinds miss by 0.07–0.6 s, and they are different kinds each time. The threshold was not raised.
- The contract test rewrites `contract-results.json` from that run alone, so only a full run can update it.
- Floci leaves `floci-aws-*` service containers without an owner label. `labctl down` now names them but does not remove them.

## Next steps
- The user imports lab-001 content, then Phase 11 steps 1–4 (RDS via the builder, `labctl check`, compare with labaws).
- Rerun the contract suite on a quiet machine to get a clean results file.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
