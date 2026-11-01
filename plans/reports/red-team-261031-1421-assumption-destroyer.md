# Red team: Assumption Destroyer — plan 261031-1358-lab-coverage-hardening

10 findings: 2 Critical, 6 High, 2 Medium. Full text was kept in the controller session. Summary:

1. Critical — catalog "gap = 0" is graded at namespace level from the inferred CSV. Labs that need EBS snapshot, CodeCommit, placement groups, Oracle or DHCP come out `ready`. Phase 10's escape via `extract.py` is unrelated to catalog mode.
2. Critical — a single `list` call plus 3 hooks cannot express the current collector (per-resource calls in collector.py:259-310) or the parent-scoped kinds in Phases 8–10. Needs `list.scope` and `enrich`.
3. High — byte-identical argv cannot hold. The ops use CLI shorthand, `--count`, prefix-selected params and composite merges (ops.py:161,184,222,248). Needs `argv_override`.
4. High — `coverage <lab>` on console prose: the "uncertain → gap" rule conflicts with AC2 ("no human review") and with Phase 11 expecting ready-with-caveats. Caveats should come from the registry, not from prose.
5. High — Resource Explorer does not index NACL, ENI, TGW and others. Matching is by ARN while node ids are bare ids. Per-lab narrowing turns registered kinds into `unknown`.
6. High — reachability: collector holds ingress only (collector.py:166-174). Phase 7 actually depends on Phase 8. Fixtures are self-authored. Restrict to display until validated.
7. High — `ResourceGraph.emulator: Literal["floci"]` (schema.py:60), single region root (schema.py:81-83), twin root picked by `next()` (twin.py:55). Not in Phase 3 or 8 files.
8. High — AC taxonomy conflicts (verdicts and caveats). AC4 does not test chat or twin. AC3 latency is not measured. contract-results.json is not stamped with the Floci digest.
9. Medium — DHCP options, egress-only IGW, placement groups and Oracle are missing in Floci and should be marked `missing` up front.
10. Medium — the effort for Phases 9 and 10 is underestimated. Estimate per service.
