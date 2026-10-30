---
phase: 5
title: "Web: chế độ luyện tập"
status: completed
priority: P2
effort: "4h"
dependencies: [3, 4]
---

# Phase 5: Web: chế độ luyện tập

## Goal

Có công tắc "Luyện tập" trên panel builder (F4.7): builder dựng và validate lệnh như thường nhưng không chạy; người học chép lệnh sang terminal, và panel báo xong khi graph khớp `practiceExpect`.

## Files to Create / Modify

- Modify: `web/src/builder/use-builder.ts` (trạng thái `practicing`, hành động `practice`)
- Modify: `web/src/builder/builder-panel.tsx` (công tắc, lưu `localStorage` trong `try/catch`)
- Modify: `web/src/builder/command-panel.tsx` (ẩn Run, đổi chữ hướng dẫn, hiện sự kiện api-tap gần nhất)
- Modify: `web/src/builder/use-builder.test.ts`
- Modify: `web/src/builder/builder-api.ts` (kiểu `PracticeExpect` nếu chưa có ở Phase 4)

## Tasks & Steps

- [x] Máy trạng thái: thêm `{ phase: 'practicing'; draft; preview; since }`. Từ `form` có preview hiện hành và không có problem, hành động `practice` (bấm Chép ở chế độ luyện tập) chuyển sang `practicing`. Hành động `graph` chuyển `practicing → done` khi graph khớp `preview.practiceExpect`. Không có `tick` timeout; Esc huỷ được (khác `running`/`waiting`).
- [x] `practiceMet(expect, graph)`: dạng `{kind, label}` đạt khi có node `kind` (hoặc một trong hai kind subnet khi `kind = "subnet"`) có `label` bằng Name tag; các dạng khác dùng lại `expectMet`.
- [x] Ở `practicing`, panel hiện "Dán lệnh vào terminal và chạy; cảnh sẽ tự cập nhật", và sự kiện `api-event` ghi gần nhất (service, action) để người học thấy lệnh của mình đã tới emulator. Nếu có sự kiện ghi đúng action (ví dụ `RunInstances`) nhưng sau 10 giây graph vẫn chưa khớp, hiện gợi ý kiểm tên (Name tag) đã gõ, không chuyển sang `failed`.
- [x] Công tắc tắt khi đang `running`/`waiting`; bật lại chế độ thường ở `practicing` thì quay về `form` với cùng draft.
- [x] Chế độ luyện tập không bao giờ gọi `runOp`; test khẳng định điều này.

## Verification

- `cd web && pnpm test && pnpm typecheck`
- Test reducer: `form → practicing → done` theo graph; Esc ở `practicing` về `idle`; không chuyển trạng thái khi graph không khớp; `runOp` không được gọi.
- Kiểm thủ công: bật luyện tập, kéo SG vào VPC, chép lệnh, chạy ở terminal (`aws ... --profile lab`), panel báo xong trong ≤ 2 giây sau khi lệnh trả.
