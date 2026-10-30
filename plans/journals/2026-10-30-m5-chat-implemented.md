---
title: M5 chat gợi ý lệnh đã làm xong code, chưa chạy với LLM thật
date: 2026-10-30
summary: "Chat gợi ý lệnh xong 5 phase với lab fixture, sửa các mục review; bộ câu hỏi mẫu chưa chạy vì máy chưa có provider LLM"
---

# M5 chat gợi ý lệnh đã làm xong code, chưa chạy với LLM thật

## Chuyện gì đã xảy ra
- Làm đủ 5 phase của plan `261030-1336-m5-chat-command-suggestions`.
  - Phía server: module `cloudy_labs/chat/` gồm cấu hình (biến môi trường hoặc `~/.cloudy-labs/llm.env`), client `openai`/`anthropic` bằng httpx, prompt có danh mục op và graph rút gọn, và parse kèm sửa một lần, ref giữa các bước, validate. Thêm `POST /api/chat` và trường `chat` trong `/api/lab`.
  - Phía web: panel "Trợ lý lệnh" ở góc dưới phải (góc trên phải đã có panel thuộc tính), Run từng bước, Run cả chuỗi có ref, Chép ở chế độ luyện tập. Công tắc luyện tập tách thành `use-practice.ts`, dùng chung với builder.
- Test luyện tập "storage ném lỗi" trượt: `setItem` lỗi nhưng `getItem` vẫn trả giá trị cũ. Store giờ giữ bản sao trong trang khi ghi lỗi.
- Review có một High: `labctl reset` xảy ra trong lúc chờ preview thì bước của câu trả lời cũ vẫn được chạy trong lần làm mới. Cùng đó là các Medium:
  - Server nhận ref cho `keyName` dù ref là id chứ không phải tên.
  - Một param `null` làm hỏng cả câu trả lời.
  - Docs nói sai rằng `-m docker` không chạy test chat live. Thật ra test có cả marker `docker`, nên có thể tốn token của người dùng.
- Đã sửa các mục trên cùng phần lớn mục Low, kèm test. Test của race trượt khi bỏ lệnh kiểm.

## Kết quả
- Server: 386 passed, ruff sạch.
- Web: 185 passed, typecheck và build sạch.
- Prompt đo trên graph fixture: 8196 ký tự (Lab 6), 8030 ký tự (Lab 7).
- Bộ câu hỏi mẫu (18 test) **chưa chạy**: thiếu cả bốn biến `LLM_*`. Agent không đặt hay đọc key. Điều kiện qua mốc "Run hết chuỗi thì `labctl check` đạt" vì vậy chưa được chứng minh.

## Quyết định
- LLM chỉ chọn op và param; server dựng argv và validate, nên prompt injection qua Name tag không vượt được danh mục op.
- Test live chỉ mang marker `llm`, không mang `docker`, để `-m docker` không gọi provider trả tiền.
- `null` trong params nghĩa là `""` ("không có"). Param sai vẫn hiện kèm problem chứ không bị bỏ.
- Lịch sử gửi đi luôn bắt đầu bằng lượt user (tối đa 11 lượt khi cắt), vì có provider từ chối hội thoại mở đầu bằng assistant.

## Bước tiếp
- Người dùng đặt provider rồi chạy `cd server && uv run pytest -m llm tests/test_chat_live.py -v` và ghi kết quả vào `notes/live-results.md`. Sau đó chạy lại khi có Lab 6 và 7 thật.
- Người dùng chốt: nút Run và công tắc Luyện tập của builder tắt khi chat đang chạy một bước (đã làm, có test). Bước đã Chép vẫn treo nếu tắt luyện tập giữa chừng: chấp nhận, hỏi lại thì hết.
- Chưa commit; chờ người dùng yêu cầu.
