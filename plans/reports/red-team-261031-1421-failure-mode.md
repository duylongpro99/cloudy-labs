# Red team: Failure Mode Analyst — plan 261031-1358-lab-coverage-hardening

10 findings: 3 Critical, 5 High, 2 Medium. Also noted: Phases 2/3/4 run in parallel but edit the same app.py and labs/schema.py, and graph emulator is Literal["floci"].

1. High — build_graph has about 10 more special cases than the 3 hooks (collector.py:36-37,111-226,259-309). Needs an `enrich` stage plus a differential test against the old build_graph as an oracle.
2. Critical — moto: profile `lab` hard-codes test keys (aws_profile.py:38-41), but moto keys rotate on every reset (providers/aws.py:21-25,88-103). The api-tap admin endpoint on 127.0.0.1 inside the container is unreachable, and TAP_UPSTREAM sits in a closure, so the setting is lost on restart (api_tap.py:154,299).
3. Critical — byte-identical argv is impossible (`--count`, shorthand tags, bare boolean flags, ip-permissions UX). Deleting Params breaks expectation(), validate.py:127, suggest.py:17/128-154 and app.py:20.
4. High — fileb:// / JSON editor bypasses the file:// guard (validate.py:32,133-136; runner.py:62-66). Make it step 0 for every string leaf.
5. High — the `global` root breaks schema, twin, targets and web (schema.py:81-83, twin.py:55, labs/schema.py:107-112, graph-to-scene.ts:19, layout.ts:75). Move multi-root into Phases 1/2.
6. High — the lab-scoped collector makes nodes flicker, misses moto writes, and lets reachable() pass falsely when a NACL is not collected. CheckContext has only a client (checks.py:23, engine.py:88).
7. High — the collector does not keep SG egress, route targets pcx/tgw/vpce, blackhole or main-table association (collector.py:115-118,166-174,217-226). Move the prop contract into Phase 1. Golden consumers on the web side are affected.
8. High — region switch misses about 37 test files. Floci fixtures must be re-recorded with a script, not edited with sed. The region_zones cache is set once (app.py:133).
9. Medium — icons are bundled through import.meta.glob (geometry-cache.ts:11-18), and web/public/icons does not exist. AC4 needs a rebuild.
10. Medium — catalog mode misses missing ops inside a supported namespace. gap=0 can be gamed by extract.py. AC1 has 3 verdicts versus 4.
