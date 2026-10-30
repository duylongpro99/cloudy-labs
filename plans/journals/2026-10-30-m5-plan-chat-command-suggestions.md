---
title: "M5 plan: chat command suggestions"
date: 2026-10-30
summary: "Wrote 5-phase M5 plan; LLM picks builder ops as JSON, server builds argv and validates, web runs steps via existing /api/run"
---

# M5 plan: chat command suggestions

## What happened
Brainstormed and wrote `plans/261030-1336-m5-chat-command-suggestions/` (plan.md + 5 phases). The brainstorm report is `plans/reports/brainstorm-261030-1336-m5-chat-command-suggestions.md`.

## Decision
- The LLM never writes CLI text. It returns JSON steps `{op, params, explanation}` drawn from the lab's op catalog. The server builds argv with `Op.argv` and checks each step with the existing `validate()`. Free CLI was rejected: it cannot be validated (F5.3), and an LLM-written argv could carry `--profile default` and reach real AWS.
- A chained step refers to an earlier step's resource as `{"ref": n}`. The server marks such steps `deferred`, and the web resolves the id at run time: from `expect.node` in normal mode, or from the graph node matching `practiceExpect` in practice mode. The server stays stateless.
- Providers are called with plain `httpx` for both `openai` and `anthropic` formats. The model returns JSON in text with one repair retry; tool calling was skipped because self-hosted OpenAI-compatible endpoints vary.
- Config comes from env, then `~/.cloudy-labs/llm.env`. The key is redacted from every error and never logged.
- Passing M5 requires a real OpenAI-compatible run, including one whole-lab question per fixture lab that ends with `labctl check` passing.

## Next steps
- Run `/ak:cook` on the plan, starting with Phase 1.
- The user configures their own provider for Phase 5; the agent does not read the key.
- Re-run the question set when the real Lab 6 and Lab 7 land.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
