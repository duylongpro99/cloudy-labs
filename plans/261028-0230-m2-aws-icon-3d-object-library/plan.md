---
title: "M2: thư viện 3D object từ bộ AWS Architecture Icons"
description: "Biến icon AWS (bản 07312026) thành các khối 3D có thể tái dùng cho cảnh kiến trúc M2, ở cả chủ đề sáng và tối, trong ngân sách hiệu năng đã đo ở M0."
status: completed
priority: P1
effort: 15.5h
tags: [frontend, 3d, assets, m2]
blockedBy: []
blocks: []
created: 2026-10-28
---

# M2: thư viện 3D object từ bộ AWS Architecture Icons

## Overview

Đây là một phần của mốc M2 trong [roadmap](../../docs/roadmap.md). Plan này làm một thư viện 3D object cho cảnh kiến trúc. Mỗi loại tài nguyên trong PRD F2.4 có một khối 3D dựng từ artwork của bộ AWS Architecture Icons trong `aws-icon-pkg/` (bản 07312026).

Quyết định của người dùng ngày 2026-10-28:
- **Được sửa icon AWS tuỳ ý**, kể cả ép đùn (extrude) path SVG thành hình khối 3D, đổi màu theo chủ đề và ghép lên đế. Quyết định này thay thế điều khoản "không cắt, lật, xoay hay đổi màu" và mặc định "icon tự vẽ" trong F3.8. PRD sẽ được cập nhật ở Phase 6.
- Đã thực hiện bằng `/ak:cook` ngày 2026-10-28. Kết quả: [thiết kế object](./notes/object-design.md), [hiệu năng](./notes/perf-results.md), [thống kê hình khối](./notes/geometry-stats.md).

Ngữ cảnh đã có:
- [Báo cáo spike M0](../reports/spike-261027-2248-m0-validation.md): công thức render, số đo hiệu năng, các cạm bẫy của R3F.
- Code tham khảo (dùng một lần): `spikes/m0-render/`. Thư viện mới không kế thừa code này, chỉ dùng lại kết luận và bộ đo.
- [Kỹ thuật dựng cảnh](../reports/researcher-261027-1616-3d-architecture-rendering-techniques.md).

## Đã khảo sát gói icon

- Icon tài nguyên (`Resource-Icons_07312026/`, 48 px) là SVG có **một path, một màu, `fill-rule="evenodd"`**, không có gradient. Định dạng này ép đùn trực tiếp được bằng `SVGLoader` + `ExtrudeGeometry` của three.
- Icon nhóm (`Architecture-Group-Icons_07312026/`, 32 px) có hai màu: ô vuông màu nhóm và glyph trắng.
- Gói **không có** icon cho Security Group, Key Pair và Availability Zone. Theo quy ước sơ đồ AWS, AZ và SG là đường viền nhóm chứ không có icon riêng.
- Gói **gần như không có biến thể nền tối** cho các icon cần dùng; chỉ có `AWS-Cloud*_Dark` và `Res_Internet*_Dark`. Biến thể tối sẽ tự chỉnh màu, việc này được phép theo quyết định ở trên.
- `aws-icon-pkg/` (khoảng 4.150 file) đang chưa được git theo dõi.

## Goals

| # | Mục tiêu | Ưu tiên |
|---|---|---|
| 1 | Mỗi loại tài nguyên trong F2.4 có một 3D object dựng từ icon AWS. Loại nào không có icon thì có phương án thay thế được ghi rõ | P1 |
| 2 | Có biến thể sáng và tối dùng chung hình khối, chỉ khác bộ màu (F3.9) | P1 |
| 3 | Cảnh 200 node dùng thư viện này vẫn đạt p95 ≤ 20 ms trên Safari ở DPR 2, và số draw call không vượt mức `full` của M0 (680) | P1 |
| 4 | Có pipeline tái lập được: từ file SVG trong gói ra hình khối, không chỉnh tay từng file | P2 |
| 5 | PRD và ghi chú giấy phép phản ánh quyết định mới, kèm rủi ro pháp lý | P1 |

## Non-goals

- Không làm icon cho dịch vụ ngoài F2.4 (S3, Lambda, DynamoDB…). Những loại này để sang M7; pipeline phải mở rộng được nhưng không làm sẵn.
- Không làm builder kéo-thả (M3) và không làm resource graph/collector (cũng thuộc M2, nhưng ở plan khác).
- Không đưa toàn bộ `aws-icon-pkg/` vào repo.

## Phases

| # | Phase | Phụ thuộc | Effort | Status |
|---|---|---|---|---|
| 1 | [Manifest icon và quy tắc tài sản](./phase-01-icon-manifest-and-asset-rules.md) | — | 1.5h | Completed |
| 2 | [Chuyển SVG thành hình khối 3D](./phase-02-svg-to-3d-geometry.md) | 1 | 4h | Completed |
| 3 | [Thiết kế object và token sáng/tối](./phase-03-object-design-and-theme-tokens.md) | 2 | 3h | Completed |
| 4 | [Component R3F, instancing và trang gallery](./phase-04-r3f-components-instancing-gallery.md) | 3 | 4h | Completed |
| 5 | [Đo hiệu năng và kiểm thử hình ảnh](./phase-05-performance-and-visual-verification.md) | 4 | 2h | Completed |
| 6 | [Cập nhật PRD, roadmap và ghi chú giấy phép](./phase-06-prd-and-license-docs.md) | 1 (có thể làm sớm) | 1h | Completed |

Phase 1–5 chạy tuần tự. Phase 6 chỉ cần kết quả Phase 1 nên có thể làm song song.

## Kiến trúc

```text
aws-icon-pkg/ (không commit)
   │  scripts/import-aws-icons  (đọc manifest, chép đúng các SVG đã chọn)
   ▼
web/src/scene/aws-objects/icons/*.svg   (bản sao đã chọn, commit, có NOTICE)
   │  SVGLoader → Shape[] → ExtrudeGeometry  (lúc chạy, một lần cho mỗi loại, có cache)
   ▼
geometry-cache  ──►  <AwsObjectLayer>  (một InstancedMesh cho mỗi loại × phần: đế + glyph)
                        ├─ token màu theo chủ đề (sáng/tối)
                        └─ lớp phủ highlight cho node đang hover/chọn (Outlines)
```

`web/` là thư mục web app của M2. Nếu lúc thực hiện plan web app chưa được tạo, Phase 4 sẽ tạo khung tối thiểu với đúng các phiên bản đã ghim ở M0.

## Success Criteria

- [ ] `manifest.ts` ánh xạ đủ mọi loại tài nguyên F2.4 tới một file SVG có thật, hoặc tới một phương án thay thế đã ghi rõ. Có test kiểm điều này.
- [ ] Mọi object hiển thị đúng ở cả hai chủ đề. Có ảnh chụp trang gallery trong `plans/261028-0230-m2-aws-icon-3d-object-library/notes/`.
- [ ] Cảnh 200 node dùng thư viện đạt p95 ≤ 20 ms trên Safari 26 ở DPR 2 và trên Chrome, với draw call ≤ 680, đo bằng cùng phương pháp M0.
- [ ] Glyph đọc được ở góc isometric 35° và ở mức zoom mặc định. Glyph không bị vỡ tam giác, mặt không bị đảo chiều, lỗ (evenodd) không bị lấp.
- [ ] `aws-icon-pkg/` nằm trong `.gitignore`. Repo chỉ chứa các SVG đã chọn, kèm file ghi nguồn và bản phát hành.
- [ ] PRD F3.8, A5 và mục giấy phép đã cập nhật theo quyết định ngày 2026-10-28.

## Rủi ro

- **Pháp lý.** Hướng dẫn của AWS cấm sửa icon, và việc AWS cho phép phân phối icon trong sản phẩm thương mại vẫn chưa rõ (A5). Ép đùn và đổi màu đi ngược hướng dẫn đó. Người dùng đã chấp nhận rủi ro này; plan chỉ ghi lại để người dùng xem lại trước bản phát hành công khai, không chặn công việc. Giảm thiểu: giữ icon sau một interface "bộ icon" có thể thay thế (F3.8), để nếu cần thì đổi sang bộ tự vẽ mà không phải sửa cảnh.
- **Số tam giác.** Một số glyph có nhiều đường cong (ví dụ path Route Table nặng 14 KB). Ép đùn với nhiều đoạn cong có thể đẩy số tam giác của 179 instance lên cao. Giảm thiểu: chỉnh `curveSegments` riêng cho từng icon, giới hạn số tam giác mỗi loại (Phase 2), và có phương án dự phòng là dán icon phẳng làm texture khi zoom xa.
- **Instancing và tương tác.** `Outlines` của drei làm việc trên một mesh, không theo từng instance. Giảm thiểu: dùng một mesh phủ riêng cho node đang hover/chọn.
- **Lỗi hình học từ SVG.** `SVGLoader.createShapes` có thể đảo chiều lỗ với `evenodd`. Phase 2 kiểm từng icon bằng mắt và bằng test.

## Chuyển sang plan sau

Người dùng chốt ngày 2026-10-28: các việc dưới đây đưa vào plan của phần collector, tức plan đầu tiên đẩy placement thay đổi vào cảnh lúc đang chạy.

- Nếu danh sách placement đổi trong lúc object còn đang chạy hoạt ảnh xuất hiện, object đó hiện chạy lại từ đầu. Cần giữ tiến độ hoạt ảnh của nó, ví dụ lưu thời điểm bắt đầu theo id trong `entrance.ts` thay vì chỉ lưu tập id đã hiện xong.
- Chưa kiểm tận mắt trên trình duyệt hành vi "chỉ id mới chạy hoạt ảnh", vì hiện chưa có màn hình nào đổi placement lúc chạy. Plan collector cần có bước kiểm tra này.
- Bench chưa đo lại sau các sửa đổi từ code review. Đo lại khi có cảnh lấy dữ liệu thật.
