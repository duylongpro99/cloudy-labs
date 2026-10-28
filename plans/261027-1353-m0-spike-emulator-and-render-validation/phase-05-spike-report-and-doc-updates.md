---
phase: 5
title: "Báo cáo spike và cập nhật PRD/roadmap"
status: completed
priority: P1
effort: "1.5h"
dependencies: [1, 2, 3, 4]
---

# Phase 5: Báo cáo spike và cập nhật PRD/roadmap

## Goal

Tổng hợp kết quả Phase 1–4 thành một báo cáo, đóng các giả định A4, A6, A8 trong PRD, và đánh dấu M0 hoàn thành trong roadmap.

## Files to Create / Modify

- Create: `plans/reports/spike-<YYMMDD-HHmm>-m0-validation.md`
- Modify: `docs/product-requirements.md`, mục 10 (giả định), và F3.7 nếu mức hậu kỳ mặc định thay đổi
- Modify: `docs/roadmap.md`, cột trạng thái và link của M0, cùng điều chỉnh M1–M2 nếu phát hiện làm thay đổi phạm vi
- Modify: `plan.md` của plan này (trạng thái)

## Nội dung báo cáo

1. **Kết luận ngắn.** Backend được chọn, mức hậu kỳ mặc định, kết luận về api-tap và kết luận về giấy phép.
2. **Ma trận trường của Floci và MiniStack**, kèm danh sách những gì collector ở M2 phải suy luận hoặc vá.
3. **Hành vi của emulator khác AWS thật.** Đây sẽ là đầu vào cho phần "ghi chú lab" (NFR5).
4. **Kết quả moto Lab 3.**
5. **Bảng hiệu năng p50/p95** theo mức hậu kỳ, chủ đề, DPR và trình duyệt, kèm ảnh chụp.
6. **Tóm tắt giấy phép.**
7. **Phiên bản ghim** của mọi image và gói, để M1 dùng lại.
8. **Câu hỏi mở**, nếu có.

## Tasks & Steps

1. Đọc các ghi chú trong `plans/261027-1353-m0-spike-emulator-and-render-validation/notes/` và kết quả của từng phase.
2. Viết báo cáo, với mỗi kết luận trỏ tới file bằng chứng trong `spikes/`.
3. Cập nhật PRD:
   - Chuyển A4 và A6 sang "đã kiểm chứng" hoặc "sai, kèm hướng xử lý".
   - Nếu chọn MiniStack thay vì Floci, sửa bảng kiến trúc ở mục 9.
4. Cập nhật roadmap: đánh dấu M0 hoàn thành và gắn link báo cáo.
5. Kiểm tra lần cuối không còn tiến trình nào của spike: `docker ps` và `lsof -i :4566 -i :4567 -i :4580 -i :5000 -i :5173`.

## Verification

- Mọi link trong báo cáo, PRD và roadmap đều trỏ tới file có thật.
- Mỗi tiêu chí trong mục Success Criteria của `plan.md` đều có bằng chứng tương ứng.
