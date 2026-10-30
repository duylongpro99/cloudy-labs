---
phase: 3
title: "API: /api/chat và trạng thái chat"
status: completed
priority: P1
effort: "4h"
dependencies: [2]
---

# Phase 3: API: /api/chat và trạng thái chat

## Goal

Đưa gợi ý lên lab-server qua `POST /api/chat` với cùng lớp bảo vệ của builder, và báo trạng thái chat trong `/api/lab` để web bật hoặc tắt panel (F5.4, F5.7).

## Files to Create / Modify

- Modify: `server/src/cloudy_labs/server/app.py`
- Modify: `server/tests/test_app.py`

## Tasks & Steps

- [x] Tách phần kiểm Origin, content-type và JSON hợp lệ của `op_request` thành `guard_request(request) -> dict | JSONResponse`; `op_request` gọi lại hàm này, hành vi không đổi (test hiện có vẫn xanh).
- [x] `create_app` nhận thêm `llm: Callable[[], LlmSettings | Missing] = load_settings` và `complete=provider.complete` để test tiêm vào.
- [x] `/api/lab` thêm `chat`: `{enabled: true, model, format}` hoặc `{enabled: false, missing: [...], error?: str}`. Không bao giờ có key hay base URL đầy đủ có query string.
- [x] `POST /api/chat`: `guard_request`; body đúng dạng `{messages: [{role: "user" | "assistant", content: str}]}`, lượt cuối là `user`, tối đa 12 lượt, mỗi lượt tối đa 8000 ký tự (sai thì 422). Không có lab thì 409, graph không `ok` thì 503, chat chưa cấu hình thì 409 kèm hướng dẫn. Gọi `suggest` với graph hiện tại của hub; `ProviderError` thành 502 với message đã che key. Không chạy lệnh nào.
- [x] Test: Origin lạ 403, text/plain 415; chưa cấu hình 409 và `/api/lab` báo `enabled: false`; trả gợi ý hai bước với `complete` giả; provider lỗi 502 và message không chứa key; `caplog` ở mức DEBUG không chứa key; `/api/chat` không gọi runner (runner giả đếm số lần).

## Verification

- `cd server && uv run pytest tests/test_app.py`
- `cd server && uv run pytest`
