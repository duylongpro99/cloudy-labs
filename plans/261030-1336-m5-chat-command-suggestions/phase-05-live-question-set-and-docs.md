---
phase: 5
title: "Bộ câu hỏi mẫu với LLM thật và tài liệu"
status: in-progress
priority: P1
effort: "4h"
dependencies: [1, 2, 3, 4]
---

# Phase 5: Bộ câu hỏi mẫu với LLM thật và tài liệu

## Goal

Chứng minh điều kiện qua mốc M5 bằng provider OpenAI-compatible thật của người dùng trên `fixture-lab-06` và `fixture-lab-07`, và ghi cách cấu hình chat vào tài liệu.

## Files to Create / Modify

- Create: `server/tests/fixtures/chat/questions.yaml`
- Create: `server/tests/test_chat_live.py`
- Modify: `server/pyproject.toml` (marker `llm`, mặc định bỏ qua cùng `docker`)
- Create: `plans/261030-1336-m5-chat-command-suggestions/notes/live-results.md`
- Modify: `docs/labctl.md` (mục "Chat gợi ý lệnh", bảng biến môi trường)
- Modify: `docs/roadmap.md` (trạng thái M5, link plan và kết quả)
- Modify: `README.md` (chỉ nếu README có mục tính năng cần nhắc chat)

## Tasks & Steps

- [x] `questions.yaml`: mỗi mục có `lab`, `question`, và kỳ vọng: `ops` (tập op phải xuất hiện), hoặc `refusal: true`. Tối thiểu 6 câu cho mỗi lab fixture, gồm câu một bước, chuỗi có ref, câu dùng tài nguyên có sẵn (id thật), một câu ngoài phạm vi (ví dụ tạo bucket S3), một câu về việc emulator không hỗ trợ.
- [x] `test_chat_live.py` (marker `llm` và `docker`, bỏ qua kèm lý do khi `load_settings()` trả `Missing`): với mỗi lab, `labctl start`, lấy graph, gọi `suggest` cho từng câu. Đạt khi: câu `refusal` có `refusal` và không có bước; câu khác có đủ `ops` kỳ vọng, mọi bước không có `problems`, mọi id trong params có trong graph hoặc là ref hợp lệ. Thêm một kịch bản cho mỗi lab: hỏi một câu bao trọn các task, chạy hết chuỗi gợi ý qua `/api/run` (giải ref như web), rồi `labctl check <lab> --json` báo `passed: true`.
- [ ] Người dùng đặt cấu hình provider của mình (agent không đọc hay in key), chạy `uv run pytest -m llm tests/test_chat_live.py`, ghi model, số câu đạt, câu trượt và lý do vào `notes/live-results.md`. Câu trượt do model thì ghi lại, không sửa test cho qua.
- [x] `docs/labctl.md`: cách cấu hình (biến môi trường hoặc `~/.cloudy-labs/llm.env`, ví dụ OpenAI, OpenRouter, Ollama, Anthropic với key giả `sk-...`), quy tắc `/v1`, cảnh báo key không bao giờ commit, chat làm được gì và không làm gì, cách chạy bộ câu hỏi mẫu.
- [x] `docs/roadmap.md`: M5 xong với lab fixture, chờ kiểm lại bằng Lab 6 và 7 thật; link plan và `notes/live-results.md`.

## Verification

- `cd server && uv run pytest && uv run pytest -m llm tests/test_chat_live.py`
- `cd web && pnpm test && pnpm typecheck`
- `git grep -n "LLM_API_KEY=" -- ':!docs' ':!plans'` không có giá trị thật.

## Kết quả

- Bộ câu hỏi: 9 câu mỗi lab (6 `fresh` gồm 2 câu ngoài phạm vi, 1 `build`, 2 `built`); `test_chat_live.py` thu được 18 test, bỏ qua với `no LLM provider set` khi chưa cấu hình. Marker `llm` mặc định bị bỏ qua cùng `docker`.
- **Chưa chạy với LLM thật**: máy phát triển chưa có provider (thiếu cả bốn biến). Việc còn lại thuộc người dùng: đặt provider rồi chạy lệnh ở [notes/live-results.md](notes/live-results.md) và điền bảng kết quả.
