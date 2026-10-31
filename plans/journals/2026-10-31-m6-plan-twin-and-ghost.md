---
title: "M6 plan: twin and ghost"
date: 2026-10-31
summary: "Wrote 5-phase M6 plan; lab-server auto-runs checks, ghosts bind to real ids through check resource_ids, web merges ghosts into the layout"
---

# M6 plan: twin and ghost

## What happened
Brainstormed and wrote `plans/261031-0838-m6-twin-ghost/` (plan.md + 5 phases). The brainstorm report is `plans/reports/brainstorm-261031-0830-m6-twin-ghost.md`.

## Decision
- Checks run automatically. The lab-server reruns them after each published graph, and on the 5 s poll while any check still fails, because some checks (an HTTP probe of the web server) change without the graph changing. Progress is written only when results differ, so `labctl status` is not flooded; `labctl check` still always writes.
- Ghosts bind to real resources only through the `resource_ids` of passed checks, matched by kind and graph parent. A second property-matching language was rejected because it would drift from the checkers. AZ ghosts carry no checks and bind through their children, since AZ node ids are `{vpc}/{az}` and no checker returns them.
- Scouting found two fixture gaps that the binding rule depends on: the Lab 6 NAT check does not return the EIP allocation id, and nothing in Lab 7 returns the ids of the network that `setup` builds. The plan fixes both in the fixtures, with a new `network-ready` check for Lab 7. Real labs must follow the same rule, and docs will say so.
- The user chose node ghosts only (no edge ghosts), and ghosts on by default with a toggle, including while the builder is in use.

## Next steps
- Run `/ak:cook` on the plan, starting with Phase 1.
- Re-verify with the real Lab 6 and Lab 7 once they exist.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
