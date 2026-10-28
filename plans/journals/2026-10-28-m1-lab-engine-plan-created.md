---
title: M1 lab engine plan created
date: 2026-10-28
summary: "Planned labctl + Floci/moto stack in 5 phases; user chose server/ package, moto container, labctl down, restart-based reset"
---

# M1 lab engine plan created

## What happened
User chose to start M1 (labctl + emulator) before the remaining M2 collector work. Plan: plans/261028-1104-m1-lab-engine-labctl/ (5 phases, 17h).

## Decision
- Python package `cloudy_labs` under `server/`, shared later by lab-server.
- moto runs as `motoserver/moto:5.2.4` container in the same compose as Floci, both bound to 127.0.0.1.
- Add `labctl down` (beyond PRD F1.2) because `docker compose down` leaves Floci orphans.
- Reset = restart emulator container + label-scoped orphan cleanup (~1 s per M0).
- No lab content yet: only schema, loader, checker runner and a test fixture lab.

## Next steps
- Execute with /ak:cook. Verify the `io.floci.owner` label value before writing the cleanup filter.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
