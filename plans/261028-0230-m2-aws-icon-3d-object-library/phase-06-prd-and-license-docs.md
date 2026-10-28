---
phase: 6
title: "Cập nhật PRD, roadmap và ghi chú giấy phép"
status: completed
priority: P1
effort: "1h"
dependencies: [1]
---

# Phase 6: Cập nhật PRD, roadmap và ghi chú giấy phép

## Goal

Ghi quyết định ngày 2026-10-28 (dùng và được sửa icon AWS) vào tài liệu sản phẩm, kèm rủi ro pháp lý, để tài liệu khớp với những gì code sẽ làm.

## Files to Create / Modify

- Modify: `docs/product-requirements.md`
  - F3.2 và F3.8: bộ icon mặc định là AWS Architecture Icons (bản 07312026), được ép đùn thành khối 3D và chỉnh màu theo chủ đề. Vẫn giữ interface "bộ icon có thể thay thế". Bỏ điều khoản "không cắt, lật, xoay hay đổi màu".
  - Mục 10: ghi quyết định mới vào bảng đã chốt. Cập nhật A5: icon được dùng trước khi có ý kiến pháp lý, người dùng chấp nhận rủi ro; vẫn cần xem lại trước bản phát hành công khai.
  - Mục 11 (Rủi ro), mục 5: cập nhật phần giảm thiểu rủi ro pháp lý (bỏ "icon tự vẽ làm mặc định", thay bằng "icon nằm sau interface có thể thay thế").
- Modify: `docs/roadmap.md`, dòng M2: thay "Bộ icon tự vẽ cho các tài nguyên ở F2.4" bằng thư viện 3D object từ icon AWS, link tới plan này.
- Modify: `plans/261027-1353-m0-spike-emulator-and-render-validation/notes/license-summary.md`, thêm một dòng cho AWS Architecture Icons: nguồn, bản phát hành, trạng thái "dùng và sửa đổi theo quyết định 2026-10-28; điều khoản phân phối chưa xác nhận".

## Tasks & Steps

1. Đọc lại F3.2, F3.8, A5 và mục Rủi ro trong PRD trước khi sửa.
2. Sửa đúng các chỗ trên, giữ văn phong và cách đánh số hiện có. Tăng phiên bản PRD.
3. Kiểm tra mọi link mới trỏ tới file có thật.

## Verification

- `grep -n "tự vẽ" docs/product-requirements.md docs/roadmap.md` chỉ còn những chỗ nói về phương án thay thế, không còn chỗ nói "mặc định".
- Link check: mọi link tương đối trong hai file trỏ tới file có thật.

## Rủi ro và rollback

- Nếu ý kiến pháp lý về sau yêu cầu bỏ icon AWS: chuyển interface "bộ icon" sang bộ icon từ nguồn khác có giấy phép phù hợp (người dùng chốt 2026-10-28; không nhất thiết tự vẽ) và đảo lại các dòng PRD này. Code cảnh không phải sửa nhờ manifest.
