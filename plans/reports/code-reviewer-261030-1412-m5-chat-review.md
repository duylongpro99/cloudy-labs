# Code review: M5 chat gợi ý lệnh (uncommitted changes)

## Verdict

**Changes requested. Not a merge blocker on security.** The key-handling contract holds: the key goes only in the provider request header, every provider error goes through `redact()`, nothing in `chat/` logs, and `/api/chat` never reaches the runner. Gates are green: `uv run pytest` 380 passed, `ruff` clean, `pnpm test` 183 passed, `pnpm typecheck` clean.

Fix 1–3 before calling M5 done:
1. A stale async path can still call `runOp` after the lab attempt changes.
2. A `{ref}` on `keyName` is accepted but can never run.
3. One `null` param throws away the model's whole answer.

Also fix one docs claim that the code contradicts (item 4).

## Scope

- Server: `chat/{settings,provider,prompt,suggest}.py`, `server/app.py` (`guard_request`, `chat_status`, `chat_messages`, `/api/chat`), `builder/validate.py` (`attached_groups` moved).
- Web: `chat/{chat-api,use-chat,chat-panel}.ts(x)`, `builder/use-practice.ts`, and the chat wiring in `app.tsx`, `builder-api.ts`, `builder-panel.tsx`.
- Tests and docs: `test_chat_*.py`, the chat section of `test_app.py`, `questions.yaml`, `web/src/chat/*.test.*`, `docs/labctl.md`, `docs/roadmap.md`, `README.md`.
- Empirical probes (scratchpad scripts, nothing edited): parsing a `null` param, an Anthropic content block that is not a dict, malformed base URLs, and `pytest --collect-only -m docker`.

## Findings by severity

### High

**1. `runOp` can fire after a lab reset or attempt change, against the new attempt.** `web/src/chat/use-chat.ts:236-254`

`sender()` captures `gen`. A reset bumps `gen` (`:188-191`), so the old `send(...)` calls become no-ops. But `start` never checks whether its generation is still current after `await previewOp(...)` (`:238`). It goes straight on to `await runOp(step.op, params)` (`:250`).

Failure scenario:
1. The learner presses Run (or Run cả chuỗi) on a step with no id params, for example `create-vpc` or `create-internet-gateway`.
2. While the preview is in flight, `labctl reset` or `labctl start` opens a new attempt.
3. The preview resolves. `send({type:'running'})` is dropped, but `runOp` still POSTs `/api/run`.
4. The server validates against the new attempt's graph, which passes for a create step with only literal params. A VPC or IGW is created in the new attempt without the learner pressing Run there, and the chat UI shows nothing.

This breaks the "nothing runs unless pressed" invariant (F5.4) across an attempt boundary. The test at `use-chat.test.ts:161` only covers a finished answer, not an in-flight preview.

The same gap applies when practice mode is turned off during the preview from the builder panel's toggle (`builder-panel.tsx`). That toggle is not disabled while the chat is busy, and `practiceRef.current` is read only after the await (`:241`).

Fix: check before the run.
```ts
const mine = gen.current          // capture alongside send
...
if (mine !== gen.current) return  // after preview, before practice branch and runOp
```
Or have `send` return a boolean and bail out when it returns false. Add a test that resets the attempt between preview and run and asserts `runOp` was not called.

### Medium

**2. A `{ref}` on `keyName` that points at `create-key-pair` passes the server check but can never run.**
- Ref check: `server/src/cloudy_labs/chat/suggest.py:130-137`. It only requires the target to be a `create` op.
- Deferred steps skip `validate`: `suggest.py:152-153`.
- The web fills the ref with the made id: `web/src/chat/use-chat.ts:83` (`expect.node`).

`create-key-pair` returns `KeyPairId` (`ops.py:244`, `result_id="KeyPairId"`), and the collector uses that as the node id (`collector.py:177-180`). But `run-instances.keyName` must be the key *name*, and `validate.py:314` checks it by label.

Failure scenario:
1. A Lab 7 "build" question gets `[create-key-pair{name:"lab07-key"}, …, run-instances{keyName:{"ref":k}}]`. The prompt encourages refs for anything an earlier create step makes (`prompt.py:63-64`).
2. The server shows the step as sound ("kiểm khi chạy", no problems).
3. On Run, the web sends `keyName: "key-0abc…"`. The preview returns "there is no key pair named key-0abc…".
4. The chain stops.

In practice mode, `madeId` returns the node id as well, so the result is the same.

Fix: reject refs on params that are not ids. Allow `{ref}` only for `*Id` params, or keep a per-op allow-list. Add a `Problem("keyName", "write the key pair's name, not a ref")` for this case. Also say in `FORMAT` that `keyName` takes the name.

**3. One `null` param makes the whole answer unparseable, and the "never dropped" contract fails.** `server/src/cloudy_labs/chat/suggest.py:43,46-52`

`params: dict[str, str | Ref]`, and `_numbers_as_text` coerces only numbers. Verified: `{"op":"run-instances","params":{"keyName":null}}` raises `ValidationError` for the whole `Reply`. That uses up the single retry, then returns `FORMAT_FAILED` with every step lost.

`null` is a very likely encoding here, because the prompt itself says "keyName … or empty for none; userData … or empty for none" (`prompt.py:39-41`). This contradicts the plan's acceptance criterion: "param sai … đều được trả về kèm `problems`, không bị bỏ đi".

Fix: in the `before` validator, map `None` to `""`. Coerce or report other non-str, non-Ref values at the step level (as a `Problem`) instead of failing the whole `Reply`.

**4. Docs claim is false: `-m docker` *does* select the live chat suite.** `docs/labctl.md:222`

`test_chat_live.py` has `pytestmark = [llm, docker, skipif(...)]`, and a command-line `-m docker` replaces the `addopts` `-m 'not docker and not llm'`. Verified: `uv run pytest --collect-only -q -m docker` collects 18 `test_chat_live` items.

Consequence: with a provider configured, a plain `pytest -m docker` (the documented builder e2e command, `docs/labctl.md:219`) also spends the learner's LLM tokens. It also runs a second module-scoped `labctl up`/`down` stack alongside the other docker tests.

Fix: drop the `docker` mark and gate the module on `llm` only (it still needs Docker). Alternatively, add `skipif` on a config-option check so it runs only when `llm` is selected. Then the docs line becomes true.

### Low

**5. The Anthropic response parser crashes on a non-dict content block.** `server/src/cloudy_labs/chat/provider.py:55`

`b.get("type")` raises `AttributeError`, which `_text` does not catch (verified with `{"content": ["oops"]}`). The result is an unhandled 500 from `/api/chat` instead of the intended "answered without content[].text" 502.

Related: an OpenAI `content: null` (refusals, reasoning or tool-only replies) gives the misleading hint "is LLM_API_FORMAT right?" (`:87-89`).

Fix: add `AttributeError` to the except clause, and skip any block that is not a dict.

**6. An `httpx.InvalidURL` from the base URL escapes as a 500.** `provider.py:69-73`

`InvalidURL` is not an `httpx.HTTPError`. `LLM_BASE_URL=http://[::1` passes the `startswith` check in `settings.py:66` and then raises uncaught (verified). The error message would not contain the key, but the learner gets "Internal Server Error" instead of guidance.

Fix: also catch `httpx.InvalidURL`, or validate the URL with `httpx.URL()` in `load_settings`.

**7. A non-UTF-8 `llm.env` takes down `/api/lab`, and the builder with it.** `server/src/cloudy_labs/chat/settings.py:39-42`

`read_text()` raises `UnicodeDecodeError`, which is a `ValueError`, not an `OSError`. `/api/lab` calls `llm()` on every request (`app.py:192`), so a corrupt file returns a 500 and the web app loses the builder. That breaks the success criterion "chưa cấu hình … builder vẫn kéo-thả và Run được". Same class of issue as 6.

Fix: catch `(OSError, UnicodeDecodeError)`. Optionally run `llm()` through `asyncio.to_thread` there, as `/api/chat` does.

**8. A whitespace-only assistant reply makes every later question fail until the next reset.**
- `web/src/chat/use-chat.ts:94-96`: `parts.filter(Boolean)` keeps `"\n"`.
- `server/src/cloudy_labs/server/app.py`, `chat_messages`: rejects content that is whitespace-only.

If the model answers `reply:"\n"`, `refusal:null`, `steps:[]`, that turn is sent back on every later question and each one gets a 422. Fix: trim each part on the web side before the fallback.

**9. A refusal can still come with runnable steps, contrary to the docs.** `suggest.py:179`, `docs/labctl.md:99`

The docs say an out-of-scope request gets "không có bước nào", but the server passes through `steps` even when `refusal` is set. Fix: enforce `steps=[]` when `refusal` is set, or soften the docs.

**10. A practicing step gets stuck if practice mode is turned off.** `use-chat.ts:59-63`

`practicing` is not `runnable`, so after the learner turns practice off, that step cannot be Run. Steps that ref it stay blocked until a new answer arrives. The builder handles the same toggle by reopening its form (`builder-panel.tsx` toggle). Fix: on practice off, revert `practicing` runs to `pending`.

**11. The `/api/lab` setup error echoes the raw `LLM_API_FORMAT` value.** `settings.py:64`

If the user swaps lines in `llm.env` and the key ends up in `LLM_API_FORMAT`, the key is returned in `/api/lab.chat.error` without `redact()`. The response is same-origin only (Host and CORS), so exposure is limited to the local page. Still, it breaks the rule "every error string sent to the browser goes through redact()". Fix: do not echo the value, or redact any of the four values.

### Informational (verified OK)

- **Key confinement:** the key appears only in `_request` headers (`provider.py:42,46`). `LlmSettings.api_key` has `repr=False`. `chat_status` returns only model and format. Every provider error string is wrapped in `redact()` (`provider.py:71,73,81,85,89`) and redacted again in `app.py`. `chat/` has no logging calls. Tests check `caplog` at DEBUG.
  - httpx's own `INFO` logger does emit `HTTP Request: POST <url> …`. That line has no key and only appears if someone sets root logging to INFO; worth knowing.
- **`/api/chat`** shares `guard_request` (Origin and content-type) with the builder endpoints, has a strict body shape, and enforces the turn and length limits. It never touches `runner`, and `test_chat_suggests_checked_steps_and_runs_nothing` asserts `runner.calls == []`.
- **Contract:** the server `Step.to_dict` keys match the web `ChatStep` type exactly (`op, params, explanation, command, problems[{field,message}], deferred, refs, practiceExpect`). `ChatStatus` matches `chat_status`.
- **Practice switch:** `use-practice.ts` uses a module-level `useSyncExternalStore`, so the two `usePractice()` callers (`app.tsx` and `builder-panel.tsx`) stay in sync.
- **Chain runner:** marking `resolving` synchronously before the first await (`use-chat.ts:234`) prevents a double start. The reducer guards reject `ran` and `blocked` for runs that are no longer in the matching state.
- **Docs claims checked:** 5-second wait (`WAIT_MS = 5000`), 60-second timeout, 12 turns, 8000 characters, `/v1` suffix handling for OpenRouter `/api` and `/api/v1`, and the 409/503/502 statuses all match the code.

## Plan follow-ups

Phases 1–4 match their acceptance criteria apart from findings 1–3. Phase 5 is still open: the live question set has not run. Findings 2 and 3 will likely surface as live-run failures on the Lab 7 "build" question, and the plan says not to loosen validation to get it through, so fix them first.

## Unresolved questions

1. Anthropic Messages API: `history()` takes `slice(-12)`, which starts with an `assistant` turn once the conversation is longer than 12 turns (alternating, ending with `user`). Does the configured Anthropic endpoint still reject a leading assistant message? If so, drop the leading assistant turn on the web side.
2. Should Run in the builder panel also be disabled while a chat chain is running? The plan only requires disabling the palette; today a builder Run between chain steps makes the next chain step fail with 409 from `runner.busy`.

Status: DONE_WITH_CONCERNS
Summary: The key handling and the "suggest only" server path hold, and all gates are green. But a stale `runOp` can fire after a lab attempt change, a ref on `keyName` is accepted but cannot run, a `null` param throws away the whole answer, and one docs claim about `-m docker` is false.
Concerns/Blockers: Fix findings 1–3 before running the Phase 5 live question set.

## Trạng thái sau khi sửa (2026-10-30)

- Đã sửa và có test:
  - Chạy lệnh sang lần làm mới: `start` dừng trước `runOp` nếu lab đổi trong lúc chờ preview (test "runs nothing when the lab is reset while the preview is out" trượt khi bỏ lệnh kiểm).
  - Ref trên `keyName`: ref chỉ nhận cho param tên kết thúc bằng `Id`.
  - `null` làm hỏng cả câu trả lời: giờ `null` thành `""` (nghĩa là "không có"); param sai vẫn hiện kèm problem.
  - Dòng docs về `-m docker`: test live giờ chỉ mang marker `llm`, nên `-m docker` thu 0 test chat; lệnh chạy là `uv run pytest -m llm tests/test_chat_live.py -v`.
  - Block Anthropic không phải dict: bỏ qua. `httpx.InvalidURL`: thành `ProviderError`. `llm.env` không phải UTF-8: coi như rỗng.
  - Câu trả lời chỉ có khoảng trắng; lịch sử mở đầu bằng lượt assistant (giờ luôn bắt đầu bằng lượt user); refusal kèm bước (bỏ hết bước); lỗi `LLM_API_FORMAT` không còn lặp lại giá trị đã đặt.
- Theo quyết định của người dùng: nút Run và công tắc Luyện tập của builder tắt khi chat đang chạy một bước (có test). Bước đã chép ở chế độ luyện tập vẫn treo nếu tắt luyện tập; người dùng chấp nhận, hỏi lại thì hết.
