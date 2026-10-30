---
title: "M5: chat gợi ý lệnh CLI"
description: "Người học mô tả việc muốn làm bằng ngôn ngữ tự nhiên; LLM do người dùng tự cấu hình chọn op trong danh mục builder, server dựng lệnh và validate trên graph thật, người học bấm Run từng bước hoặc cả chuỗi, hoặc chép lệnh ở chế độ luyện tập."
status: in-progress
priority: P1
effort: 30h
branch: master
tags: [feature, backend, frontend, api, llm, m5]
blockedBy: [261030-1045-m4-builder-lab-07]
blocks: []
created: 2026-10-30
---

# M5: chat gợi ý lệnh CLI

## Overview

Mốc M5 trong [roadmap](../../docs/roadmap.md), phạm vi PRD F5.1–F5.7. Contract đã chốt ở [báo cáo brainstorm](../reports/brainstorm-261030-1336-m5-chat-command-suggestions.md): LLM **không viết lệnh CLI**. LLM trả JSON gồm các bước `{op, params, explanation}`, với `op` lấy từ danh mục op của lab đang mở. Server dựng argv bằng `Op.argv`, validate bằng `validate()` có sẵn, rồi trả về giống `/api/preview`. Lệnh chỉ chạy qua `/api/run` có sẵn khi người học bấm Run (A1, F5.4).

Lab 6 và 7 thật chưa có nội dung, nên bộ câu hỏi mẫu chạy trên `fixture-lab-06` và `fixture-lab-07`. Khi có lab thật phải chạy lại bộ mẫu rồi mới đóng M5.

Ngữ cảnh đã có (M3, M4):
- `builder/ops.py`: `OPS`, `catalog(palette)`, `Op.argv`, `display`, `practice_expectation`, `server_fields` (`currentGroups` do server điền).
- `builder/validate.py`: `validate(op_name, params, graph, azs, choices)` trả `list[Problem]`.
- `server/app.py`: `op_request` kiểm Origin, content-type, JSON, op, palette, `server_fields`; `checked` dựng argv và validate; `/api/run` validate lại, khoá `runner.busy`, trả `expect`.
- Web: `use-builder.ts` có `expectMet`, `practiceMet`; `builder-api.ts` có `previewOp`, `runOp`, `BuilderError`; công tắc luyện tập nằm trong `builder-panel.tsx` (`localStorage` khoá `cloudy-labs:practice`).

## Quyết định thiết kế

- **Module mới `cloudy_labs/chat/`**: `settings.py` (đọc cấu hình LLM), `provider.py` (gọi `openai` hoặc `anthropic` bằng `httpx.AsyncClient`), `prompt.py` (dựng system prompt), `suggest.py` (parse, sửa một lần, giải ref, validate). Không thêm dependency.
- **Cấu hình**: biến môi trường `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_API_FORMAT`; nếu thiếu thì đọc file `llm.env` (dạng `KEY=VALUE`) trong `CLOUDY_LABS_HOME`. Biến môi trường thắng file. `LLM_BASE_URL` có hoặc không có hậu tố `/v1` đều được.
- **Không lộ key**: key chỉ nằm trong header của request tới provider. Mọi chuỗi lỗi trả về trình duyệt đi qua `redact()` thay key bằng `***`. Không log request hay response của provider. `/api/lab` chỉ báo `chat: {enabled, model, format}` hoặc `{enabled: false, missing: [...]}`.
- **Đầu ra của LLM**: JSON trong text, `{"reply": str, "refusal": str | null, "steps": [{"op", "params", "explanation"}]}`. Parse bằng pydantic. Lỗi parse thì gửi lại một lần kèm thông báo lỗi; vẫn lỗi thì trả `reply` báo model không làm theo định dạng.
- **Ref giữa các bước**: giá trị param có thể là `{"ref": n}` (n bắt đầu từ 1), nghĩa là id tài nguyên do bước n tạo. Server kiểm: n trỏ bước trước đó, bước đó là op `create`. Bước có ref không validate theo graph lúc gợi ý (`deferred: true`), lệnh hiển thị dùng chỗ giữ chỗ `<id từ bước n>`.
- **`/api/chat` chỉ gợi ý, không chạy.** Body `{messages: [{role, content}]}`, tối đa 12 lượt và 8000 ký tự mỗi lượt. Dùng chung kiểm Origin và content-type với `op_request` (tách thành hàm `guard_request`). Trả `{reply, refusal, steps: [{op, params, explanation, command, problems, deferred, refs, practiceExpect}]}`.
- **Web chạy chuỗi**: mỗi bước, web thay ref bằng id thật rồi gọi `previewOp` (lấy lệnh và problem mới nhất) và `runOp`. Chế độ thường lấy id từ `outcome.expect.node`; chế độ luyện tập lấy id từ node khớp `practiceExpect` của bước trước (node mới, không nằm trong `known`). Run cả chuỗi dừng ở bước đầu tiên bị refused, exit code khác 0, hoặc quá `WAIT_MS`.
- **Một công tắc luyện tập cho cả builder và chat**: tách `savedPractice`/`savePractice` thành hook `use-practice.ts`.
- **Builder và chat không chạy chồng**: chat tắt Run khi builder `busy`, và palette tắt khi chat đang chạy; server đã chặn bằng `runner.busy`.

## Non-goals

- Lệnh ngoài danh mục op; chat trả lời là ngoài phạm vi.
- Streaming, lưu lịch sử chat phía server hoặc qua lần tải lại trang.
- Sửa tay một bước trong chat (người học hỏi lại, hoặc dùng builder).
- Tool calling, function calling, JSON mode riêng của provider.
- Twin, ghost (M6), lab ngoài Lab 6 và 7, nội dung lab thật.

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Cấu hình LLM và client provider](./phase-01-llm-settings-and-provider.md) | Completed |
| 2 | [Prompt, parse và gợi ý đã validate](./phase-02-prompt-and-suggestions.md) | Completed |
| 3 | [API: /api/chat và trạng thái chat](./phase-03-chat-api.md) | Completed |
| 4 | [Web: panel chat, Run từng bước và cả chuỗi, luyện tập](./phase-04-web-chat-panel.md) | Completed |
| 5 | [Bộ câu hỏi mẫu với LLM thật và tài liệu](./phase-05-live-question-set-and-docs.md) | In progress (chờ chạy bộ câu hỏi với LLM thật) |

Phase 1 độc lập. Phase 2 cần `provider.complete` của Phase 1. Phase 3 cần Phase 2. Phase 4 cần API của Phase 3. Phase 5 cần tất cả.

## Kiến trúc

```text
 trình duyệt (Vite :5174)                           labctl serve :8730                      LLM provider
 ┌──────────────────────────────────┐ POST /api/chat ┌─────────────────────────────────┐   (người dùng cấu hình)
 │ ChatPanel: ô hỏi, lịch sử        │ ─────────────► │ guard_request (Origin, JSON)    │
 │  bước: lệnh, giải thích, problem │ {messages}     │ prompt.py: catalog + schema,    │  POST /v1/chat/completions
 │  Run | Run cả chuỗi | Chép       │                │   graph rút gọn, AZ, AMI, task  │ ─────────────────────────►
 │  ref → id thật (expect / graph)  │ ◄───────────── │ provider.py (openai|anthropic)  │ ◄─────────────────────────
 │                                  │ {reply, steps} │ suggest.py: parse, sửa 1 lần,   │  hoặc /v1/messages
 │ mỗi bước: POST /api/preview,     │                │   ref, Op.argv, validate()      │
 │   rồi POST /api/run (có sẵn)     │ ─────────────► │ /api/run: validate lại, runner  │
 │       ▲ /ws: graph + api-event   │                └─────────────────────────────────┘
 └───────┴──────────────────────────┘
```

## Success Criteria

- [x] Chưa cấu hình provider: `/api/lab` trả `chat.enabled = false` kèm tên biến còn thiếu, panel chat hiện hướng dẫn, builder vẫn kéo-thả và Run được.
- [x] Unit test cho cả `openai` và `anthropic` qua `httpx.MockTransport`: đúng URL, header, body; parse được nội dung; JSON hỏng được sửa sau một lần gửi lại; lỗi HTTP và timeout thành thông báo dễ hiểu.
- [x] Test khẳng định key không có trong response của `/api/chat`, `/api/lab`, thông báo lỗi, hay log (`caplog`).
- [x] Gợi ý có op ngoài danh mục của lab, param sai, ref trỏ sai, hay lệnh không qua validate đều được trả về kèm `problems`, không bị bỏ đi và không chạy được.
- [x] Web: Run một bước, Run cả chuỗi dừng ở bước lỗi đầu tiên, ref được thay đúng id ở chế độ thường và luyện tập; ở chế độ luyện tập không gọi `runOp`.
- [ ] Bộ câu hỏi mẫu cho `fixture-lab-06` và `fixture-lab-07` chạy với provider OpenAI-compatible thật: mọi bước dùng id có trong graph hoặc ref hợp lệ, qua validate; câu ngoài phạm vi bị từ chối; kết quả ghi vào `notes/live-results.md`.
- [ ] Với mỗi lab fixture, một câu hỏi bao trọn lab cho ra chuỗi mà khi Run hết thì `labctl check <lab>` đạt (bắt buộc để qua mốc).
- [x] `uv run pytest`, `pnpm test`, `pnpm typecheck` xanh.

## Rủi ro

- **Model nhỏ không làm theo schema.** Sửa lại một lần chỉ giảm rủi ro. Bộ câu hỏi mẫu ghi tỉ lệ đạt theo model đã thử; không hạ điều kiện validate để cho qua.
- **Endpoint OpenAI-compatible khác nhau** (OpenRouter cần base URL có `/api/v1`, Ollama ở `/v1`). Quy tắc hậu tố `/v1` và thông báo lỗi nêu URL đã gọi (không có key) giúp người dùng tự sửa.
- **Prompt dài khi graph lớn.** Graph rút gọn chỉ giữ trường validate dùng; Phase 2 đo độ dài prompt cho fixture và ghi lại. Đo lại ở M7.
- **Prompt injection qua Name tag** (người học đặt tên tài nguyên là chỉ dẫn cho LLM). Hậu quả bị chặn bởi thiết kế: LLM chỉ chọn được op trong danh mục, server tự dựng argv và validate, không gì tự chạy.
- **Lab thật khác fixture.** Chạy lại bộ mẫu khi có Lab 6 và 7 thật.

## Validation Log

### Phiên 1 (2026-10-30)

- **Cách tiếp cận**: LLM chọn op trong danh mục, server dựng argv (chốt ở brainstorm).
- **Chế độ luyện tập**: chat hỗ trợ đầy đủ, id của bước sau lấy từ graph (chốt ở brainstorm).
- **Provider để chạy bộ mẫu**: OpenAI-compatible của người dùng; code vẫn hỗ trợ cả `anthropic`.
- **File cấu hình**: `~/.cloudy-labs/llm.env` (`CLOUDY_LABS_HOME`), biến môi trường thắng file (đề xuất).
- **Qua mốc**: kịch bản một câu bao trọn lab, Run hết, `labctl check` đạt là bắt buộc với LLM thật (đề xuất).
- **Lịch sử chat**: trong bộ nhớ trang, xoá khi đổi lab hoặc lần làm (đề xuất).
- **Vị trí panel**: cạnh phải, thu gọn được (đề xuất).

### Verification Results

- Claims checked: 14. Verified: 12. Failed: 2 (đã sửa). Unverified: 0. Tier: Full.
- Đã kiểm: `catalog`, `OPS`, `server_fields`, `practice_expectation`, `result_id` (`builder/ops.py`); chữ ký `validate(op_name, params, graph, azs, choices)` (`validate.py:117`); `op_request` và `checked` điền `currentGroups` (`server/app.py`); `httpx` đã là dependency (`pyproject.toml`); `config.home()` đọc `CLOUDY_LABS_HOME`; `expectMet`, `practiceMet(expect, graph, known)`, `WAIT_MS` (`use-builder.ts`); `previewOp`, `runOp`, `BuilderError` (`builder-api.ts`); `savedPractice`/`savePractice` và khoá `cloudy-labs:practice` (`builder-panel.tsx`); fixture `lab-06-07.graph.json`; prop `cidr`, `attachedVpc`, `groupName`, `state`, `ingress` mà validate đọc.
- Đã sửa: node không có `parent` (quan hệ cha con nằm ở `graph.contains`, cạnh dùng `from`/`to`, `graph/schema.py:29-46`); `labctl check` chạy mọi check của lab, không theo từng task (`cli.py:94`).

### Whole-Plan Consistency Sweep

- Đã rà `llm.env`, `ref`, `deferred`, `practiceExpect`, `guard_request`, `chat.enabled`, 12 lượt và 8000 ký tự trong mọi file phase: tên và hình dạng thống nhất giữa Phase 2, 3, 4, 5. Không còn mâu thuẫn.
