---
phase: 5
title: "Đo hiệu năng và kiểm thử hình ảnh"
status: completed
priority: P1
effort: "2h"
dependencies: [4]
---

# Phase 5: Đo hiệu năng và kiểm thử hình ảnh

## Goal

Chứng minh cảnh 200 node dùng thư viện object mới vẫn đạt ngưỡng NFR2 trên Safari và Chrome, và ghi lại số liệu để so với M0.

## Files to Create / Modify

- Create: bộ đo cho cảnh mới, dùng lại phương pháp của `spikes/m0-render/src/bench.ts` và `scripts/run-chrome-bench.mjs`: 10 s đo, 2 s làm nóng, camera xoay 30°/s, canvas 1280×800.
- Create: `plans/261028-0230-m2-aws-icon-3d-object-library/notes/perf-results.md`.

## Tasks & Steps

1. Chạy 3 mức hậu kỳ × 2 chủ đề × 2 DPR trên Chrome (Playwright, `channel: 'chrome'`).
2. Chạy cùng bộ đó trên Safari theo `plans/261027-1353-m0-spike-emulator-and-render-validation/notes/safari-checklist.md`: Safari phải ở trước suốt lúc đo, và lần đo hỏng thì chuyển vào `invalid/`.
3. So với M0: draw call, số tam giác, số program, p50/p95/p99.
4. Kiểm tra idle: 0 khung hình trong 10 s sau khi hoạt ảnh xuất hiện xong.
5. Nếu dư ngân sách thì thử bật bevel cho glyph, đo lại, và chỉ giữ nếu vẫn đạt.

## Verification

- Mọi cấu hình có p95 ≤ 20 ms. Safari ở DPR 2 với mức `full` là điều kiện bắt buộc.
- Draw call ở mức `full` ≤ 680 (mức của M0). Kỳ vọng thấp hơn nhiều nhờ instancing.
- Idle: 0 khung hình.

## Rủi ro và rollback

- Bài đo M0 chạm trần vsync nên không thấy dư địa. Nếu cần biết dư địa, đo thêm với 400 và 800 node; đây là tham khảo, không phải điều kiện qua phase.
- Nếu không đạt: giảm `curveSegments`, thêm LOD theo zoom, hoặc chuyển icon nặng nhất sang texture phẳng. Ghi lại lựa chọn.
