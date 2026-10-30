# M4 code review: builder for Lab 7 and practice mode

Date: 2026-10-30. Scope: uncommitted working tree on `master` (28 modified files, ~1,000 LOC, plus the untracked
`ec2_choices.py`, `fixture-lab-07`, `test_fixture_lab_07.py`, `build-form.test.ts`, `practice-mode.test.tsx` and
`e2e-builder-lab-07.mjs`). Reviewed against `plan.md` and phase files 01-06. No files changed besides this report.
Docker, the lab-server (8730) and Vite (5174) were not touched.

## Overall

The structure is sound and consistent with M3. The server gates argv construction, runs no shell, refuses
`currentGroups`, overwrites it from the graph, and never logs stdout. The web app keeps `KeyMaterial` in memory only,
and the e2e JSON strips stdout. I found one confirmed trust-boundary defect: the AWS CLI expands `file://` in the two
new free-text fields. Practice mode also has a false-completion bug. The rest are medium or low.

## Findings (most severe first)

### 1. HIGH: free-text params are expanded by the AWS CLI (`file://`), so the browser can make the lab-server read local files

- `server/src/cloudy_labs/builder/ops.py:234` (`--description p.description`), `ops.py:187` (`--user-data p.user_data`).
  `validate.py:221` only checks ASCII and length. `_run_instances` (`validate.py:285-303`) only checks size.
- The AWS CLI treats any string parameter that starts with `file://` or `fileb://` as a path and sends the file's
  contents. I verified this locally with aws-cli 2.36.31 against a dead endpoint (`--debug`):
  `--description file:///…/secret.txt` sent `GroupDescription: 'SECRET-LINE-42\n'`, and `--user-data file://…` sent
  its base64.
- Scenario: a request from the web app's origin (or a learner who pastes a snippet) with
  `{"op":"run-instances","params":{…,"userData":"file:///Users/<u>/.ssh/id_ed25519"}}`. It passes validation. The
  lab-server process reads the private key and stores it as instance UserData in the emulator, where
  `describe-instance-attribute --attribute userData` returns it. It also runs as the boot script when the content
  starts with `#!`. `description` behaves the same way, up to the 255-character literal limit on the *path*, not the
  content. This breaks the documented invariant that the browser sends only typed params and the server decides
  what runs.
- Fix: in `validate.py`, refuse any free-text value (`description`, `userData`, and any future one) that starts with
  `file://`, `fileb://`, `http://` or `https://` (case-insensitive, after `lstrip()`). Explain the refusal to the
  learner. Add a test per field. For defense in depth, set `cli_follow_urlparam = false` in the `lab` profile.
  Paramfile expansion has no global off switch, so validation is the real gate.

### 2. MEDIUM-HIGH: practice mode completes without the learner running anything when a same-named resource already exists

- `ops.py:306` `practice_expectation` returns `{kind, label}`. `use-builder.ts:61-65` `practiceMet` matches *any*
  node of that kind and label. `use-builder.ts:102-104` `practice` never records which nodes existed when the command
  was copied.
- `validate` refuses duplicate names only for key pairs and for security groups within one VPC. It does not refuse
  them for instances, VPCs, subnets, IGWs, EIPs, NATs or route tables, or for SGs in another VPC.
- Scenario: instance `web` is running. The learner opens Run Instances and changes the name to `web`, then presses
  Copy. On the next graph push, which in Lab 7 comes every few seconds from the earlier instance's
  `pending → running` change, the panel says "Xong" before anything was pasted. The same happens if the pasted
  command fails, for example with a typo, while any other write refreshes the graph.
- Fix: in the `practice` action, snapshot the ids of nodes that already match (pass the current graph in, or compute
  them in `CommandPanel`). Then require a match whose id is not in that set, for example `{kind, label, except: ids}`.
  Also, `practice` should evaluate the current graph right away, so an already-met attribute or edge expectation is
  caught at copy time instead of on some later push.

### 3. MEDIUM: `modify-instance-attribute` builds `--groups` from a possibly stale graph, which can silently detach a security group

- `server/app.py:59-63` `attached_groups(hub.graph, …)`, used at `app.py:192` for both preview and run.
- `--groups` replaces the whole list. If the collector has not yet seen an earlier attach, the new command leaves
  that group out. Ways the earlier attach can be unseen: the earlier Run hit the 5 s `WAIT_MS` and showed `failed`
  even though the command succeeded, or the learner attached a group in the terminal (practice) and the next poll
  has not landed. AWS then removes the group with exit 0, and the panel reports success.
- Fix: for this op only, read the live list (`describe-instances --instance-ids … --query
  Reservations[0].Instances[0].SecurityGroups[].GroupId`) at run time. Or refuse the run when
  `hub.graph.version` has not advanced past the last builder run (`hub.notify` and await one collect). At minimum,
  show the groups that will remain in the form.

### 4. MEDIUM: the `server_fields` gate is bypassed with the snake_case name

- `app.py:166` compares raw body keys with `("currentGroups",)`. `Params` uses `populate_by_name=True`
  (`ops.py:26`), so `{"current_groups": ["--debug"]}` passes the gate and validates. I confirmed this:
  `ModifyInstanceAttribute.model_validate({..., 'current_groups': ['--debug']})` succeeds.
- Today `checked()` overwrites the field, so the value is not exploitable. The plan's contract ("browser sends this
  field → 422", phase 03), the docs claim, and the only test (`test_browser_cannot_send_the_current_groups`, camelCase
  only) all overstate it. Any future caller of `op_request` that skips `checked()` would pass browser argv through.
- Fix: compare against both alias and field name, e.g. map each server field to `{name, to_camel(name)}`. Better: give
  the server field `Field(exclude=True)` with `validation_alias` set to an unreachable name, or remove it from the
  browser model and pass it separately. Add a snake_case test.

### 5. MEDIUM: in practice mode Copy is enabled for a refused command, and the docs say it is not

- `web/src/builder/command-panel.tsx:99` `disabled={!command || stale}` ignores `blocked`. At `:102` it always writes
  the clipboard, then dispatches `practice`, which the reducer drops silently (`use-builder.ts:103`).
- Scenario: the form shows "SSH (port 22) to the whole Internet" refused, but Copy still puts that command on the
  clipboard. The panel gives no feedback and stays in `form`. In practice mode, Copy is the "run", so the
  SSH-to-world guard and every other validation are one paste away. The e2e (`e2e-builder-lab-07.mjs:222-224`) only
  asserts that the phase stays `form`, not that the clipboard stays clean.
- The docs (`docs/labctl.md:75`) say "Run và Chép chỉ bật khi form hết lỗi". That is false for Chép, a claim carried
  over from M3 that now matters.
- Fix: `disabled={!command || stale || (practice && blocked)}`, or keep copy-to-read in normal mode and fix the doc
  sentence.

### 6. MEDIUM: the port label promises ranges the server refuses

- `web/src/builder/build-form.tsx:23` labels the field "Cổng (hoặc dải, ví dụ 8000-8080)". `validate.py:261`
  rejects `8000-8080` ("enter one number"), and `ops.py` comments "one port".
- Fix: change the label to "Cổng" (one port), or implement ranges (`from`/`to`) in `ip_permissions`, `_ingress`
  duplicate detection and `ingress_rule`.

### 6b. MEDIUM: the UserData bind hint fires on the lab's own default script and gives outdated advice

This finding comes from the updated fixture, in which UserData now binds every IPv4 address except `lo`.

- `web/src/builder/build-form.tsx:39` `BINDS_ALL = /0\.0\.0\.0:80|…/` is matched against raw text, comments
  included. The new `fixture-lab-07/lab.yaml` UserData has the comment "…so 0.0.0.0:80 is taken". I checked the
  regex against the fixture's UserData with node, and `BINDS_ALL.test(...)` is `true`.
- Scenario: every learner who drops an Instance sees the warning "IMDS đã chiếm 0.0.0.0:80 …" on the lab's correct
  default script. The hint text at `build-form.tsx:42` ("bind vào IP private") also contradicts the updated
  `docs/emulator-differences.md:13`, which now says that binding the private IP alone is not enough. Finally,
  `build-form.test.ts:13` still tests the old private-IP-only script as the "good" example.
- The same outdated advice appears in `fixture-lab-07/checks.py` `web_server_answers` ("check … that the server binds
  the private IP"). It is also in `docs/roadmap.md:23` (M1: "UserData Lab 7 bind vào IP private").
- Fix: strip `#` comment lines before testing. Match only real bind commands (`--bind 0.0.0.0`, `http.server 80`
  with no `--bind`). Reword the hint to say "bind each non-lo IPv4 address (see emulator-differences)". Add a test
  that the fixture's own `userData` gives no hint, and update the `checks.py` message.

### 7. LOW-MEDIUM: Unicode digits crash `/api/preview` with a 500

- `ops.py:166` `_port` and `validate.py:261-264` use `str.isdigit()`, which is True for `"²"`, but `int("²")` raises
  `ValueError`. I reproduced this: `ip_permissions(...port='²')` raises. Argv is built before validation
  (`app.py:193`), so each debounced preview returns 500 while the learner types it. Arabic-Indic and full-width digits
  are accepted and silently normalised.
- Fix: use `re.fullmatch(r"[0-9]{1,5}", value.strip())` in both places.

### 8. LOW-MEDIUM: the security group description check is looser than real AWS

- `validate.py:221` accepts any ASCII, and `build-form.tsx:36` renders description as a multi-line `<textarea>`.
  For VPC security groups, AWS allows only `a-zA-Z0-9`, space and `._-:/()#,@[]+=&;{}!$*`. Newlines, `'`, `"`, `?`
  and `<` pass the builder and Floci but fail on real AWS with `InvalidParameterValue`. That contradicts the
  "validation teaches real AWS" goal.
- Fix: `re.fullmatch(r"[A-Za-z0-9 ._\-:/()#,@\[\]+=&;{}!$*]{1,255}", d)` and a single-line input for `description`.

### 9. LOW: the practice "seen" line and name hint ignore whether the call failed

- `command-panel.tsx:45-47` and `lastWrite`: api-tap events carry `status`, but `graph-client.ts:52` drops it. A
  `CreateSecurityGroup` that returned 400 (`InvalidGroup.Duplicate`, a typo'd VPC id) shows "Emulator vừa nhận", and
  10 s later the hint tells the learner to check the Name tag, which is the wrong cause.
- Fix: forward `status` in `ApiEvent`. On status ≥ 400, say the emulator refused the call and to read the terminal's
  error.

### 10. LOW: documentation does not match the code

- `docs/labctl.md:72` says the UserData default comes from "`builder.user_data` trong `lab.yaml`". The schema accepts
  only `userData`: `Builder.model_validate({'user_data': 'x'})` fails with `extra="forbid"`. Lab authors following the
  doc get a load error.
- `docs/roadmap.md` M4 row links `plans/261030-1045-m4-builder-lab-07/notes/e2e-results.md`. The file does not exist
  yet; only `floci-ec2-ops.md` is there. Write it when the docker e2e finishes, or drop the link.
- `docs/labctl.md:75`: "Chép chỉ bật khi form hết lỗi" is false (see finding 5).
- `docs/labctl.md` says the browser "không được gửi danh sách đó". That is true in effect only because of the
  overwrite (see finding 4).

### 11. LOW: minor robustness and UX issues

- `validate.py` `ModifyInstanceAttribute` does not check AWS's 5-security-groups-per-interface limit, so the 6th
  attach fails at run time instead of being explained.
- `property-panel.tsx` `ruleText` uses `key={ruleText(r)}`. Floci duplicates repeated rules (as documented), so
  React gets duplicate keys. `from: null` from the collector (JSON null, not `undefined`) renders as `"<proto> null"`
  for any non-tcp/udp/icmp/-1 protocol.
- `command-panel.tsx` `download` revokes the object URL after 0 ms, which can cancel the download in Firefox. Use
  about 1 s.
- `Copy` dispatches `practice` even when `navigator.clipboard.writeText` rejects or is missing. The panel then says
  "paste" with an empty clipboard. Dispatch only in the `.then` success path.
- `since` is api-tap's `seq`, which restarts at 1 when api-tap restarts (`labctl up`/`reset`). A practice in
  progress across a restart never shows "seen" or the hint.
- With practice on and the state `failed`, the Retry button is hidden (`practice ? null`) and Copy cannot start
  practice. The only way out is to edit a field or toggle the switch.
- `ec2_choices.choices()` falls back to x86 silently for an unknown `platform.machine()`. That is harmless, but a
  warning would help on unusual hosts.

## Checked and found OK

- No shell anywhere: `--ip-permissions` is JSON built server-side, `shlex.join` is used for display only, names are
  limited to `[A-Za-z0-9._-]`, and tag text cannot start a paramfile prefix because the whole argument starts with
  `ResourceType=`.
- Private key: there is no logger call with stdout (`grep` over `server/src`), api-tap logs only service and action,
  the web app uses `localStorage` only for the practice toggle, and the e2e JSON strips `stdout`
  (`e2e-builder-lab-07.mjs:275`).
- UserData 16 KB raw limit matches AWS. The CLI base64-encodes `--user-data` itself, which I verified.
- No Lab 6 regression. `fixedDraft` now frees `protocol/port/cidr`, but no M3 connect or attribute op has those
  fields. `connectOp` defaults `edges = []`. `validate` defaults `choices`. The `graph` reducer branch for `waiting`
  is unchanged.
- The ingress `includes` match (`expectMet`) agrees with the collector's shape for tcp, icmp (`-1/-1`) and `-1`
  (no ports).

## Recommended actions

1. Refuse `file://`/`fileb://`/`http(s)://` prefixes in `description` and `userData`, with tests (finding 1).
2. Make the practice expectation require a new node, and evaluate it at copy time (finding 2).
3. Read the live security-group list, or wait for a fresh graph, before `modify-instance-attribute` (finding 3).
4. Close the snake_case `server_fields` gap and add a test (finding 4).
5. Disable Copy for blocked commands in practice mode, fix the port label, harden port parsing, and tighten the
   description check (findings 5-8). Make the UserData hint ignore comments and match the new bind-every-address
   advice (finding 6b).
6. Correct `docs/labctl.md` (`userData` key, Chép sentence) and the roadmap link (finding 10).

## Plan follow-ups

Phases 01-05 appear implemented as written. Phase 03's "browser sends `currentGroups` → 422" holds only for camelCase
(finding 4). Phase 06 cannot be closed until `notes/e2e-results.md` exists, and the real Lab 7 still has to be re-run
as the plan states.

## Unresolved questions

- Is copy-to-read of a refused command in normal mode intended? If so, only the docs need fixing for normal mode, and
  practice mode still needs the guard.
- Should practice mode also reject a learner-typed name that differs from the form's? It currently waits forever by
  design, with only the hint.

## Resolution (2026-10-30)

| Finding | Status |
|---|---|
| 1 `file://` | Fixed: `validate` refuses any param value starting with `file://` or `fileb://`, with tests per field and through `/api/preview`. `http(s)://` is not refused: aws CLI v2 does not follow URLs by default (`cli_follow_urlparam` off) |
| 2 practice and same name | Fixed: practice ignores nodes that existed when Copy was pressed |
| 3 stale `--groups` | Fixed: `/api/run` collects a fresh graph for `modify-instance-attribute` and answers 503 if that collect fails |
| 4 snake_case gate | Fixed, with a test |
| 5 Copy on a refused command | Fixed in both modes; the docs sentence is now true |
| 6 port label | Fixed |
| 6b UserData hint | Fixed: comments are ignored and the advice is now to bind every address but `lo` |
| 7 Unicode digits | Fixed: ASCII digits only |
| 8 description | Fixed: AWS character set, single-line field |
| 9 "seen" counts failed calls | Open: api-tap does not pass the HTTP status to the browser |
| 10 docs | Fixed: `userData` key, `notes/e2e-results.md` written |
| 11 SG limit, duplicate keys, `from: null`, pem revoke | Fixed |
| 11 Copy on clipboard failure | Kept on purpose: the command stays visible to copy by hand, and headless Chrome has no clipboard |
| 11 api-tap `seq` restart, no Retry in practice, x86 fallback warning | Open, low |

The docker suite after these fixes: 10 passed ([e2e-results.md](../notes/e2e-results.md)).
