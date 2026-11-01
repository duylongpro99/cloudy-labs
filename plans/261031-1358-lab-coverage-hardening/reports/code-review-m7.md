# Code Review: M7 (lab coverage hardening)

Scope: the uncommitted work against HEAD be5fc9d. I covered builder (sanitize, shapes, catalog, validate, ops, runner), chat (prompt, suggest), emulator and credentials (aws_profile, orphans, stack, providers/aws, cli), lab content (loader, content, image endpoint), registry hooks, graph collector, tap listener/hub, and web registry.ts/fly-target.ts.
Tests run: 187 passed (`-m "not docker"`) across test_builder_sanitize/shapes/catalog/validate, test_chat_prompt/suggest, test_orphans, test_aws_profile, test_lab_content, test_loader and test_moto_profile_keys. I did not run docker tests or start the emulator.

## Critical

### C1. A list field written as a JSON array gets past both the `file://` check and the leading-`-` check
- Where: `server/src/cloudy_labs/builder/sanitize.py:81-83`, `server/src/cloudy_labs/builder/shapes.py:189-198` (list coerce: text that starts with `[` is parsed with `json.loads`), `shapes.py:310` (each list element becomes its own argv token).
- Cause: `sanitize()` splits a list field's raw text on `[\s,]+` and walks the raw string. It never parses JSON. Tokens such as `["file:///etc/hosts"]` or `"--endpoint-url"` do not start with `file://` or `-`, because they still have the leading `[` or quote. `coerce` then parses the JSON, and `argv` emits each element as a bare token.
- Reproduced through `prepare()` with string input, the same path `/api/run` and chat use:
  - `cloudwatch put-metric-alarm`, `AlarmActions='["file:///etc/hosts"]'` gives argv `--alarm-actions file:///etc/hosts` with zero problems. aws-cli v2 (2.36.31) reads that file into the request; a sentinel file confirmed it. This is a local file read sent to the endpoint.
  - `AlarmActions='["arn:a","--endpoint-url","http://127.0.0.1:9"]'` gives argv with an injected global option and zero problems. The same trick redirects the request (credentials sign it and the body goes off-box), or injects `--cli-input-json file://...`, `--profile`, `--debug`, and so on.
- Reach: `/api/run` (browser) and chat-suggested steps both go through `catalog.prepare`. Chat output comes from an LLM, so a prompt-injected scene name could also produce this.
- Fix: run the sanitizer on the typed request after `coerce`/`shapes.request`, not only on the raw text. Walk every leaf string in the request dict and refuse (a) `file://` or `fileb://` at any depth and (b) any list element that starts with `-`. Keep the raw-text check as defence in depth. Add regression tests that pass **strings** (as the app does) through `prepare()` for JSON-array list input.

## High

### H1. The `version` member becomes the global `--version` flag: the CLI prints its version, exits 0, and creates nothing
- Where: `server/src/cloudy_labs/builder/shapes.py:278` (`CLI_RENAMES` holds only sns Subscribe `Endpoint`), argv at `shapes.py:281-315`.
- Affected ops: `eks create-cluster` (`version`, a non-advanced field, so it is also offered in the chat prompt), `apigateway create-rest-api` (`version`), and `apigatewayv2 create-api` / `update-api` (`Version`). The aws CLI renames these to `--kubernetes-version` and `--api-version`.
- Failure: if the learner fills the field, argv carries `--version 1.29`. The CLI handles the global `--version`, prints `aws-cli/...`, and exits 0. The builder reports success, but no resource exists, and the check later fails with no explanation.
- Fix: add the 4 renames to `CLI_RENAMES`. Add a test that compares every generated flag against the CLI's global options (`--version`, `--debug`, `--endpoint-url`, `--profile`, `--region`, `--output`, `--query`, `--cli-input-json`, ...) so this collision cannot come back silently.

## Medium

### M1. Signing names resolve to the wrong botocore service, so the tap-driven "seen kinds" misses resources the learner created
- Where: `server/src/cloudy_labs/graph/collector.py:457-477` (`_signing_names` uses `setdefault` over sorted service names). The new caller is `server/src/cloudy_labs/server/tap_listener.py` (`hub.see(kinds_of_action(...))`).
- Evidence: signing `rds` maps to `docdb`, `elasticloadbalancing` to `elb` (not elbv2), `apigateway` to `apigateway` only (not apigatewayv2), and `events` to `eventbridgev2` rather than `events`.
- Failure: in a lab-scoped collect, a learner who writes with the CLI to RDS, ELBv2 or EventBridge (or creates an HTTP API) outside the lab palette gets an empty or wrong kind set. The new resource never appears on the graph. This defeats the reason `seen_kinds` was added.
- Fix: build the signing-name map from the services in the registry (`registry.signing_name(service)`), so one signing name maps to a *set* of services, and take the union of kinds.

### M2. `labctl env` prints the moto admin access key and secret
- Where: `server/src/cloudy_labs/cli.py` `cmd_env` (~line 123), which prints `export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...` from `provider.env()` (`providers/aws.py` ~line 72). For a moto lab, `credentials()` now returns the admin keys from `~/.cloudy-labs/moto-credentials.json`.
- Failure: this breaks the invariant that moto keys are printed only by `labctl credentials moto` (credential_process). The keys land in the terminal, shell history (if eval'd and logged), and screen shares. The behaviour is new in M7, because `cmd_env` existed before but moto creds did not.
- Fix: for the moto provider, `env()` should not export the keys. Emit `AWS_PROFILE=lab` (or an endpoint-only env) and point the user to the credential_process profile.

### M3. `file://` nested inside JSON-text fields is not refused, and the tests that seem to cover it are phantom
- Where: `sanitize.py` walks the raw string for `json`/structure fields. `tests/test_builder_sanitize.py:18-25,53` pass Python dicts and lists, which the app never sends (`/api/run` refuses any non-string param).
- Impact: nested values are not expanded by the CLI, so I found no exploit. Still, the contract says "every string leaf, including inside JSON" must be refused, and the tests give false assurance. The fix for C1 (sanitizing the typed request) closes this too. Rewrite the tests to pass JSON **text**.

## Low

### L1. Botocore drift: the server's botocore (1.43.120) is newer than the botocore bundled in the installed aws CLI v2
Members the CLI does not know are rendered as flags, and the CLI fails with "Unknown options" when they are filled in. Examples: `put-metric-alarm ActionConfiguration`, cognito `AcrConfiguration`/`AcrMapping`, glue `CatalogId`, kinesis `RecordDistributionStrategy`, rds `DBCapacityReservationIdentifier`, s3 `ObjectLockEventHold*`, transfer `HostKeyStorageType`. Fix: pin botocore to the CLI's version, or mark members missing from the CLI's model as hidden/advanced (check with `aws <svc> <op> help` at build time or in a contract test).

### L2. Registry hooks can crash the whole collect
- `server/src/cloudy_labs/registry/hooks.py:153-156` `private_ip_guard`: `ipaddress.ip_network(cidr)` on an unvalidated `CidrBlock` raises `ValueError` (for example, from a host-bits-set value with `strict=True`, or a malformed emulator response).
- The `tags` hook uses `t["Key"]`, which raises `KeyError` on an entry without a key.
- Props hooks run in `build_graph` at `graph/collector.py:279`, outside the per-service isolation. One bad record turns the whole graph into "emulator down". Fix: catch per node or per hook, use `strict=False`, and use `t.get("Key")`.

### L3. The protected-identity guard is case-sensitive
The expression `UserName == 'cloudy-labs-admin'` (`builder/catalog.py:252-260`) does not match `Cloudy-Labs-Admin`. Real IAM names are case-insensitive. This is mitigated today, because moto is case-sensitive and the admin is hidden from the scene (so ref checks fail). Fix: compare lowercased.

### L4. Minor
- `catalog._build` has no guard against duplicate op ids. None exist today, but a later registry entry would silently shadow an earlier one.
- `labs/content.py` `fetch_images` uses urllib, whose redirect handler also follows `ftp://`. Restrict it to https.

## Checked, no issue
- All 16 legacy EC2 ops still use the hand-written `spec.argv` (16/16; `ops.py` is unchanged).
- `runner.py` uses `create_subprocess_exec` (no shell), strips `AWS_*` except `AWS_CONFIG_FILE`, and kills the process group on timeout.
- `/api/run` refuses non-string params, re-runs `prepare()`, and refuses when there are problems. Chat steps use the same `prepare`.
- Names go through the allowlist, and the top-level `file://` and leading-`-` checks work for plain (non-JSON) text.
- Chat prompt: lab title, tasks, non-advanced op fields, and a compact graph with only `chat_props` minus `CHAT_PROPS_DENY`. No hints or `labs/*/content/` text. I reviewed the SSM, Secrets Manager, Lambda and IAM props, and none carry secret values.
- `loader.lab_path`: `LAB_SLUG` fullmatch plus `is_relative_to` after resolve (symlink-safe).
- Image endpoint (`server/app.py:284-300`): name regex, resolve plus `is_relative_to`, `nosniff`, `no-store`, and `CSP sandbox` for SVG.
- Web lab panel: react-markdown renders raw HTML as text, and images come only from the content endpoint.
- `aws_profile.render` refuses a `[profile lab]` without the labctl marker, writes atomically at 0600, and the moto profile uses `credential_process` (no keys in `~/.aws/config`). The moto creds file is 0600.
- Orphans: filtered by the `io.floci.owner=4567` label. The forwarder prefix `floci-aws-ec2-fwd-<iid>-` ends with `-` (no prefix collision). `unowned_service_containers` only lists and never removes.
- `hub.py`: `seen_kinds` is updated only from `ok` graphs, and the collect failure path still cannot crash the server.
- Web `actionKinds` (longest noun plus signing-name filter) and `fly-target.ts` delegation are correct. The server always sends `actions`.

## Recommended order
1. C1: sanitize the typed request and add string-input regression tests. This blocks shipping.
2. H1: add the CLI renames and a global-flag collision test.
3. M2: stop exporting moto keys in `labctl env`.
4. M1: build the signing-name map from the registry.
5. M3, then L1-L4.

## Fix status (2026-11-01)
| Finding | Status | Change | Test |
|---|---|---|---|
| C1, M3 | Fixed | `sanitize`: a list field written as a JSON array is checked one element at a time, and JSON text for a structure is checked for `file://` at every depth. A `-` inside a structure stays allowed, because the structure is passed as a single argument. | `test_a_list_sent_as_json_text_is_checked_element_by_element`, `test_structures_sent_as_json_text_are_checked_at_every_depth` |
| H1 | Fixed | `CLI_RENAMES` covers eks `CreateCluster`/`CreateNodegroup`/`UpdateNodegroupVersion` (`--kubernetes-version`) and apigateway `CreateRestApi` plus apigatewayv2 `CreateApi`/`UpdateApi` (`--api-version`), checked against `aws … help` for CLI 2.36.31. `argv()` refuses a flag that is a global option. | `test_no_op_sends_a_member_as_a_global_cli_option` (272 ops, 0 collisions) |
| M1 | Fixed | A signing name maps to the set of services that sign with it. | `test_a_signing_name_several_services_share_reaches_each_of_their_kinds` |
| M2 | Fixed | On moto, `env()` returns `AWS_PROFILE=lab` and no keys, and `labctl env` first prints `unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN`. Docs updated. | `test_env_for_a_moto_lab_prints_no_keys_and_clears_old_ones`, `test_env_points_at_the_lab_emulator` |
| L2 | Fixed | `tags` skips entries without a string Key, and `private_ip_guard` ignores a malformed address or CIDR. | `test_tags_skip_entries_without_a_key`, `test_the_private_ip_guard_ignores_a_malformed_address` |
| L1, L3, L4 | Not fixed, recorded as limitations | botocore being newer than the CLI, case-sensitive admin protection, and duplicate op ids or redirects in the image fetcher were judged low impact. | — |
