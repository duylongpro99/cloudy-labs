---
title: Lab coverage hardening plan after red-team
date: 2026-10-31
summary: Hard-mode plan to cover arbitrary labaws.site labs; 15 red-team findings applied; 358h over 11 phases
---

# Lab coverage hardening plan after red-team

## What happened
- Lab-001 (RDS vs Aurora) could not run end to end on the current platform. A resource kind is hard-coded in about 15 places, and region is fixed to us-east-1 in 42 files. The web parser throws on unknown kinds, hints never reach the learner, and the profile always points at Floci.
- The plan `plans/261031-1358-lab-coverage-hardening/` has 11 phases: registry, web registry, region/account root, local content, botocore builder, coverage, reachability, and service waves 1–3, then lab-001 acceptance.
- The red team (4 personas) raised 37 findings, which deduplicate to 15 (4 Critical, 8 High, 3 Medium). All 15 were accepted.

## Decisions
- One `account` root with child `region` nodes and a `global` node. This replaces the single-region-root rule in `graph/schema.py:81-83` and the `next()` root pick in `twin.py:55`.
- One api-tap per emulator, each with a fixed upstream. Moto signs requests through `credential_process`, which reads `moto-credentials.json`, so keys are never written to config. No runtime admin endpoint is added, because the tap binds 0.0.0.0.
- The registry adds `scope`, `enrich`, `filter`, `protected`, `chat_props` and `caveats`. Hooks resolve from a static dict, never through importlib. A failing service is dropped and recorded in `graph.warnings`. A differential test runs against the old `build_graph`.
- The 16 existing builder ops keep their hand-written argv as overrides. A step-0 sanitiser rejects `file://`/`fileb://` at every leaf and list elements starting with `-`, and never emits shorthand.
- Theory is shown as one tab per H2. labaws hints live in a gitignored `content/hints.yaml`. Lab content never reaches the chat prompt. An n-gram leak check scans tracked files.
- The Resource Explorer scan is dropped. The web shows a fallback node for kinds it doesn't know.
- Reachability results grade only behind `GRADING_ENABLED`, which turns on after the scenario table and a recorded Floci e2e both pass. Phase 7 now depends on Phase 8.
- Coverage uses four verdicts plus `catalog-overrides.yaml` for API gaps the namespace-level CSV misses (EBS snapshot, DHCP, egress-only IGW, placement group, Oracle, CodeCommit).

## Next steps
- `/ak:cook plans/261031-1358-lab-coverage-hardening/plan.md`, starting with Phase 1.
- Re-estimate Phases 9–10 from the per-service hours measured in Phase 8.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
