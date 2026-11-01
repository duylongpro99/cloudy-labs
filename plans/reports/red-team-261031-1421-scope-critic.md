# Red team: Scope & Complexity Critic — plan 261031-1358-lab-coverage-hardening

9 findings: 2 Critical, 4 High, 3 Medium.

1. Critical — `web/src/graph/types.ts` (`parseGraph`/`parseTwin`) throws on an unknown kind or edge kind (types.ts:5,10,31,82,94,111). `EDGE_KINDS` and the edge styles in edge-layer.tsx:27-31 are hard-coded. Phase 2 is missing types.ts, edge-layer, label-layer, aws-object-layer and fixture.ts. `/api/registry` needs `edgeKinds`.
2. Critical — Phase 5 deletes the Params classes that `expectation()`/`practice_expectation()` depend on (ops.py:284-311). The wire gesture today is `create|connect|attribute` (builder-api.ts:5). Op ids are kebab-case. Needs a registry `expect:` field and kebab op ids.
3. High — byte-identical argv contradicts the generic rules: shorthand tags, id-prefix dispatch, bare boolean flags, `server_fields` (ops.py:136,158-162,219-233,247-250).
4. High — multiple roots break the single-root rule (schema.py:81-83; twin.py:55; graph-to-scene.ts:19-24; api-fly-layer.tsx:71). Suggests a synthetic `account` root.
5. High — the collector special logic is undercounted (UserData, DNS attribute, docker ports, gone states). Behaviour when one service fails is undefined. Needs per-service failure isolation plus `graph.warnings`.
6. High — moto rotates admin keys on reset (providers/aws.py:19-48,88-91), but profile `lab` hard-codes test/test (aws_profile.py:33-43).
7. Medium (question) — is the Resource Explorer unknown-node scan wanted beyond the pre-lab coverage check?
8. Medium (question) — 9 section roles and `tasks[].section` versus one tab per H2.
9. Medium — Phase 7 deps should be [1,2,8]. SG egress shape change, golden change, expectation migration, and the endpoint must go through `guard_request` (app.py:71-86).
