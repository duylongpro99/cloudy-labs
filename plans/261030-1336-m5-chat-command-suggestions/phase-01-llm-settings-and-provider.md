---
phase: 1
title: "Cấu hình LLM và client provider"
status: completed
priority: P1
effort: "6h"
dependencies: []
---

# Phase 1: Cấu hình LLM và client provider

## Goal

Đọc cấu hình LLM từ biến môi trường hoặc `llm.env` ngoài git, và gọi được cả định dạng `openai` lẫn `anthropic` qua `httpx` mà key không bao giờ lọt ra ngoài header gửi tới provider (F5.5, F5.7, NFR6).

## Files to Create / Modify

- Create: `server/src/cloudy_labs/chat/__init__.py`
- Create: `server/src/cloudy_labs/chat/settings.py`
- Create: `server/src/cloudy_labs/chat/provider.py`
- Create: `server/tests/test_chat_settings.py`
- Create: `server/tests/test_chat_provider.py`

## Tasks & Steps

- [x] `settings.py`: `LlmSettings` (frozen dataclass: `base_url`, `api_key`, `model`, `api_format`), có `__repr__` không in key. `load_settings(environ=None, home=None) -> LlmSettings | Missing`, với `Missing.names` là danh sách biến còn thiếu. Thứ tự: biến môi trường, rồi `config.home() / "llm.env"` (`KEY=VALUE`, bỏ dòng trống và `#`, bỏ nháy bao quanh). `LLM_API_FORMAT` chỉ nhận `openai` hoặc `anthropic`; giá trị khác là lỗi cấu hình kèm giải thích. Đọc lại mỗi lần gọi để người dùng sửa file không phải khởi động lại server.
- [x] `provider.py`: `async def complete(settings, system: str, messages: list[Message], *, client: httpx.AsyncClient | None = None, timeout=60) -> str`.
  - `openai`: `POST {root}/v1/chat/completions`, header `Authorization: Bearer <key>`, body `{model, messages: [{role: system}, ...], temperature: 0}`; đọc `choices[0].message.content`.
  - `anthropic`: `POST {root}/v1/messages`, header `x-api-key`, `anthropic-version: 2023-06-01`, body `{model, system, messages, max_tokens: 4096, temperature: 0}`; nối các khối `content[].text`.
  - `root`: `base_url` bỏ `/` cuối và bỏ hậu tố `/v1` nếu có.
- [x] `ProviderError(message)`: lỗi kết nối, timeout, HTTP khác 2xx (kèm status và tối đa 300 ký tự body), JSON thiếu trường. Mọi message đi qua `redact(text, settings)` thay key bằng `***`. Không gọi `logging` với request hay response.
- [x] Test settings: chỉ env; chỉ file; env thắng file; thiếu biến trả `Missing` đúng tên; format lạ; `repr` không có key.
- [x] Test provider bằng `httpx.MockTransport`: URL đúng với base có và không có `/v1`; header đúng từng định dạng; body có `model` và `system`; parse nội dung; 401 và 500 thành `ProviderError`; body lỗi có chứa key thì message đã được che; timeout.

## Verification

- `cd server && uv run pytest tests/test_chat_settings.py tests/test_chat_provider.py`
- `grep -rn "api_key" server/src/cloudy_labs/chat` chỉ thấy ở `settings.py` và chỗ dựng header trong `provider.py`.
