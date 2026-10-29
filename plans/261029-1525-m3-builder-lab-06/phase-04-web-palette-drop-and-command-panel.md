---
phase: 4
title: "Web: palette, thả vào cảnh, panel lệnh"
status: completed
priority: P1
effort: "8h"
dependencies: [3]
---

# Phase 4: Web: palette, thả vào cảnh, panel lệnh

## Goal

Người học kéo một tài nguyên từ palette, thả vào khay hợp lệ, điền form, thấy lệnh và lỗi cập nhật theo form, bấm Run và đọc output; cảnh chỉ đổi khi graph mới tới (F4.1–F4.5).

## Files to Create / Modify

- Create: `web/src/builder/builder-api.ts` (+ `.test.ts`): `fetchLab`, `preview`, `run`, kiểu dữ liệu
- Create: `web/src/builder/use-builder.ts` (+ `.test.ts`): state máy `idle → dragging → form → running → waiting-graph → done/error`
- Create: `web/src/builder/palette.tsx`, `web/src/builder/build-form.tsx`, `web/src/builder/command-panel.tsx`
- Create: `web/src/builder/drop-targets.ts` (+ `.test.ts`): kind nào thả được vào khay nào, chọn khay sâu nhất
- Modify: `web/src/scene/tray-layer.tsx` (raycast được, tô sáng ô hợp lệ khi kéo), `web/src/scene/live-scene.tsx` (nhận trạng thái kéo), `web/src/app.tsx` (gắn builder vào chế độ live)

## Tasks & Steps

- [x] Palette HTML cạnh canvas, chỉ hiện kind trong `lab.palette` (F4.1), dùng icon có sẵn của thư viện object.
- [x] Kéo bằng pointer event (không dùng HTML5 drag-and-drop vì canvas không raycast trên `dragover`): `pointerdown` ở palette bắt đầu kéo; trong canvas, raycast khay theo vị trí con trỏ, lấy khay sâu nhất. Khay hợp lệ tô sáng theo màu chủ đề, khay sai làm mờ; thả ngoài khay hợp lệ thì huỷ, có dòng giải thích vì sao.
- [x] Bảng `drop-targets.ts` lấy từ danh mục op của server (trả kèm trong `/api/lab`) để hai phía không lệch nhau.
- [x] Form tối thiểu theo op: Name, CIDR (gợi ý /24 trống kế tiếp trong VPC), AZ (mặc định AZ đầu chưa có subnet; khoá nếu thả lên khay AZ), EIP cho NAT (chọn từ EIP chưa gắn). Mỗi lần form đổi, debounce 200 ms rồi gọi `/api/preview`; lỗi hiện cạnh trường tương ứng.
- [x] Panel lệnh: lệnh đầy đủ, nút Copy, nút Run (tắt khi có problem hoặc đang chạy). Sau Run hiện exit code, stdout, stderr nguyên văn trong khối monospace.
- [x] F4.5: cảnh không thêm gì khi thả hay khi Run. Panel ở trạng thái "đang chờ cảnh" cho tới khi graph mới chứa id lấy từ stdout (ví dụ `Vpc.VpcId`), quá 5 giây thì báo collector chưa thấy tài nguyên.
- [x] Bàn phím: Esc huỷ kéo hay form; form và panel đi được bằng Tab. Chủ đề sáng tối dùng token có sẵn trong `scene/theme.ts`.

## Verification

- `cd web && pnpm test && pnpm typecheck`
- Unit test `drop-targets` (khay sâu nhất, kind sai bị từ chối), `use-builder` (chuyển trạng thái, chờ graph theo id, timeout), `builder-api` (lỗi 403/409/422 thành thông báo người đọc được).
- Kiểm trình duyệt bằng `playwright-core` theo mẫu `web/scripts/check-live.mjs`: kéo VPC vào region, preview hiện đúng lệnh, chưa bấm Run thì không có request `/api/run` và số node không đổi.

## Ghi chú triển khai

- Tô sáng khay khi kéo là một lớp phủ riêng (`scene/drop-highlight.tsx`), không sửa material của khay trong `live-scene.tsx`.
- Nút Copy tên là "Chép". Run và Chép chỉ bật khi preview khớp lần sửa cuối của form; lệnh cũ mờ đi trong lúc chờ preview mới.
- Lệnh lỗi để lại nút "Sửa và chạy lại" thay vì đóng form.
- Cảnh mất kết nối emulator thì thao tác đang dở bị huỷ; `pointercancel` cũng kết thúc lượt kéo.
