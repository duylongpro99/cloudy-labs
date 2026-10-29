---
title: M3 builder Lab 6 plan
date: 2026-10-29
summary: "Planned the drag-and-drop VPC builder against a Lab-6-shaped fixture lab; locked command, profile, subnet-drop, undo and tag decisions."
---

# M3 builder Lab 6 plan

## What happened

Wrote the M3 plan at `plans/261029-1525-m3-builder-lab-06/` (6 phases, ~35h). Real Lab 6 content does not exist yet, so the plan adds `fixture-lab-06` (steps 1–21 of `spikes/m0-emulators/lab-06-07.sh`) as the acceptance target. M3 must be re-checked against the real Lab 6 before it closes.

## Decisions

- The browser sends typed operations (`{op, params}`), not command strings. The server builds `argv` from a fixed catalogue, validates it against the current graph, and runs `aws` without a shell. The displayed command comes from the same `argv`. Validation lives only in Python so M5 chat can reuse it.
- One Run is one AWS command, so the output panel shows verbatim stdout/stderr. NAT needs an existing Elastic IP.
- The user chose to have `labctl up` write a `[profile lab]` block into the user's AWS config, so displayed commands carry `--profile lab` as PRD F4.4 says. This is risky because it is the user's real config file: the plan uses a text-block replace with a marker, takes a backup, and refuses to overwrite a foreign `lab` profile.
- A Subnet is dropped on the VPC (or an existing AZ tray), and the AZ is picked in the form. No placeholder AZ trays.
- No delete operations in M3; mistakes are fixed with `labctl reset`.
- Lab YAML gets a `builder` section with `palette` and `tags`.
- Write routes require an allowed Origin and a JSON content type, which blocks CSRF from other pages.

## Verification findings

- `GraphHub` already has `notify()` with a 150 ms debounce; the draft wrongly assumed a `refresh_soon()`.
- The collector does not expose `enableDnsHostnames` or `mapPublicIpOnLaunch`. `describe-vpcs` lacks the first, so Phase 5 adds a `describe-vpc-attribute` call per VPC and must re-measure collector latency.

## Next steps

Run `/ak:cook plans/261029-1525-m3-builder-lab-06/plan.md`. Phases 1 and 2 can run in parallel.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
