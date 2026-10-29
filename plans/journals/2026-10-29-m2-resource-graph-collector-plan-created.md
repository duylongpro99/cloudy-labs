---
title: M2 resource graph and live scene plan created
date: 2026-10-29
summary: "Planned collector, api-tap, lab-server and live 3D scene in 6 phases; user chose separate labctl serve, api-tap on 4566, Vite proxy"
---

# M2 resource graph and live scene plan created

## What happened
Planned the remaining half of M2: plans/261029-1006-m2-resource-graph-collector-scene/ (6 phases, 27h). It connects the finished 3D object library to real Floci state.

## Decision
- `labctl serve` is a separate foreground command; `labctl up` stays emulator-only.
- api-tap takes the learner port 4566 and Floci moves to host port 4567. Because serve is optional, api-tap runs as a compose service and publishes write events over SSE on 4568.
- The web app runs on the Vite dev server (5174) and proxies `/api` and `/ws` to lab-server on 8730.
- A golden graph JSON produced by the server tests is read by the web tests so the schema cannot drift between the two sides.
- The three carry-overs from the object-library plan (keep entrance progress, browser check that only new ids animate, re-run the bench) are in phases 5 and 6.

## Next steps
- Execute with /ak:cook. Phase 1 step 1 must first confirm that the `io.floci.owner` label and EC2 instances still work after Floci's host port changes.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
