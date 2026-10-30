---
phase: 4
title: "Web: panel chat, Run từng bước và cả chuỗi, luyện tập"
status: completed
priority: P1
effort: "8h"
dependencies: [3]
---

# Phase 4: Web: panel chat, Run từng bước và cả chuỗi, luyện tập

## Goal

Người học hỏi trong panel chat, xem từng bước với lệnh, giải thích và problem, rồi bấm Run một bước, Run cả chuỗi, hoặc ở chế độ luyện tập chép lệnh và chạy ở terminal; id của bước sau được điền khi bước trước xong (F5.1, F5.3, F5.4, F4.7).

## Files to Create / Modify

- Create: `web/src/chat/chat-api.ts` (kiểu `ChatStep`, `ChatReply`, `sendChat`)
- Create: `web/src/chat/use-chat.ts` (reducer lịch sử và chạy chuỗi)
- Create: `web/src/chat/chat-panel.tsx`
- Create: `web/src/chat/use-chat.test.ts`
- Create: `web/src/chat/chat-panel.test.tsx`
- Create: `web/src/builder/use-practice.ts` (chuyển `savedPractice`/`savePractice` từ `builder-panel.tsx`)
- Modify: `web/src/builder/builder-panel.tsx` (dùng `use-practice.ts`)
- Modify: `web/src/builder/builder-api.ts` (`LabInfo.chat`)
- Modify: `web/src/app.tsx` (gắn panel chat, khoá chéo với builder)

## Tasks & Steps

- [x] `use-practice.ts`: hook `usePractice()` trả `[on, set]`, đọc và ghi `localStorage` trong `try/catch`, đồng bộ giữa builder và chat (sự kiện `storage` hoặc state nâng lên `app.tsx`). Test luyện tập hiện có vẫn xanh.
- [x] `use-chat.ts`, reducer thuần:
  - Trạng thái: `messages` (user và assistant, assistant giữ `ChatReply`), `asking`, `error`, và `runs: Record<stepIndex, StepRun>` cho câu trả lời mới nhất, với `StepRun` là `pending | resolving | running | waiting | practicing | done(id?) | failed(message)`.
  - `resolveParams(step, runs)`: thay `{ref: n}` bằng id của bước n đã `done`; thiếu id thì bước chưa chạy được.
  - Chạy một bước: giải ref, gọi `previewOp` với params đã giải (lấy `command` và `problems` mới, có problem thì `failed`), rồi `runOp`; chờ graph khớp `outcome.expect` như builder, quá `WAIT_MS` là `failed`. Id của bước create lấy từ `expect.node`.
  - Run cả chuỗi: chạy lần lượt từ bước đầu chưa `done`, dừng ở bước đầu `failed`.
  - Luyện tập: không gọi `runOp`. Bước ở `practicing` hiện lệnh đã giải để chép; khi graph có node khớp `practiceExpect` mà không có trong `known` lúc chép thì `done` với id của node đó (dạng `kind`/`label`), hoặc `done` không id (cạnh, prop).
  - Lịch sử gửi lên server: 12 lượt gần nhất; lượt assistant gửi `reply` và danh sách `op` của các bước dưới dạng text.
  - Lịch sử chỉ nằm trong bộ nhớ trang: mất khi tải lại trang, và được xoá khi `lab.id` hoặc `lab.attempt` đổi (id cũ không còn đúng sau reset).
- [x] `chat-panel.tsx`: ô nhập (Enter gửi, Shift+Enter xuống dòng), danh sách tin nhắn; mỗi bước có số thứ tự, giải thích, lệnh trong `<pre>` cuộn được, problem màu cảnh báo, nhãn "kiểm khi chạy" nếu `deferred`, nút Run hoặc Chép, trạng thái. Nút "Run cả chuỗi" khi có hơn một bước. `refusal` hiện như tin nhắn thường có nhãn "Ngoài phạm vi". Chat tắt thì hiện hướng dẫn đặt `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_API_FORMAT` trong biến môi trường hoặc `~/.cloudy-labs/llm.env`, liệt kê biến còn thiếu. Run tắt khi `!lab.canRun` (hiện `runBlocker`) hoặc builder đang `busy`.
- [x] `app.tsx`: panel chat ở cạnh phải, thu gọn được; palette tắt khi chat đang chạy một bước.
- [x] Test reducer: chuỗi hai bước có ref chạy đúng thứ tự và thay đúng id; bước 1 lỗi thì bước 2 không chạy; refused 409 thành `failed`; luyện tập không gọi `runOp` và lấy id từ graph; node cùng tên có sẵn trước khi chép không được tính.
- [x] Test panel (jsdom): chat tắt hiện hướng dẫn; bước có problem không bấm Run được; refusal hiển thị.

## Verification

- `cd web && pnpm test && pnpm typecheck`
- Kiểm thủ công với `labctl serve` và provider thật: hỏi "tạo subnet công khai 10.0.1.0/24 trong VPC của tôi và cho ra internet", Run cả chuỗi, cảnh cập nhật từng bước.

## Kết quả

- Kiểm thủ công với provider thật chưa làm (chưa có provider trên máy phát triển); hành vi được phủ bằng test hook và panel (jsdom).
