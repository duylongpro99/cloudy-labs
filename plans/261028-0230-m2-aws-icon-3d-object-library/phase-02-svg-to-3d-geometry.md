---
phase: 2
title: "Chuyển SVG thành hình khối 3D"
status: completed
priority: P1
effort: "4h"
dependencies: [1]
---

# Phase 2: Chuyển SVG thành hình khối 3D

## Goal

Từ mỗi SVG trong manifest, tạo ra một `BufferGeometry` ép đùn, đã chuẩn hoá kích thước và có số tam giác trong ngân sách. Kết quả được cache cho mỗi loại.

## Files to Create / Modify

- Create: `web/src/scene/aws-objects/svg-to-geometry.ts`. Dùng `SVGLoader` để parse, `SVGLoader.createShapes(path)` để ra Shape (đúng với `evenodd`), rồi `ExtrudeGeometry` để ép đùn. Sau đó gộp bằng `mergeGeometries`, căn tâm, đặt cạnh lớn nhất bằng 1, xoay để mặt phẳng icon nằm ngang (trục Y hướng lên), đảo trục Y của SVG.
- Create: `web/src/scene/aws-objects/geometry-cache.ts`. Cache theo `kind`; nạp SVG bằng `?raw` import của Vite để không phải gọi mạng lúc chạy.
- Create: `web/src/scene/aws-objects/svg-to-geometry.test.ts`.

## Thông số mặc định

| Tham số | Giá trị khởi đầu | Ghi chú |
|---|---|---|
| `depth` | 0,12 (so với cạnh 1) | Glyph nổi lên vừa đủ để thấy ở góc 35° |
| `bevelEnabled` | false | Bevel nhân số tam giác lên nhiều lần. Chỉ bật nếu Phase 5 còn dư ngân sách |
| `curveSegments` | 4, chỉnh riêng cho từng icon | Route Table có thể cần 2–3 |
| Ngân sách | ≤ 2.000 tam giác cho mỗi glyph | Với 179 instance là khoảng 360k tam giác cho phần glyph |

Với icon nhóm có hai màu, chỉ ép đùn phần glyph trắng. Ô vuông màu nhóm được thay bằng đế (Phase 3).

## Tasks & Steps

1. Viết `svgToGeometry(svgText, opts)` theo mô tả ở trên. Bỏ qua các path có `fill="none"` và bỏ khung trong suốt bao quanh, nếu có.
2. Chạy cho mọi mục trong manifest. Ghi lại số tam giác và kích thước gốc vào `plans/261028-0230-m2-aws-icon-3d-object-library/notes/geometry-stats.md`.
3. Chọn icon cho Route Table giữa hai ứng viên dựa trên số tam giác và độ dễ đọc, rồi cập nhật manifest.
4. Kiểm tra lỗ: các vòng tròn và vòng trong của glyph (Internet Gateway, NAT) phải rỗng, không bị lấp.

## Verification

- Test: mỗi geometry có `index` hoặc `position` khác rỗng; bounding box sau chuẩn hoá có cạnh lớn nhất trong khoảng 1 ± 0,001; số tam giác ≤ ngân sách.
- Test: đáy và đỉnh của khối ép đùn có pháp tuyến hướng đúng (y < 0 ở đáy, y > 0 ở đỉnh), tức không bị đảo mặt.
- Xem bằng mắt ở trang gallery (Phase 4); trong phase này có thể xem tạm bằng một trang Vite tối giản.

## Rủi ro và rollback

- Nếu `createShapes` cho ra lỗ sai với một icon, thử `SVGLoader.createShapes` với `path.userData.style.fillRule`, hoặc tự tách vòng theo chiều quay (`ShapeUtils.isClockWise`). Ghi lại icon nào cần xử lý riêng.
- Nếu một icon vượt ngân sách dù đã giảm `curveSegments`, đánh dấu nó dùng phương án phẳng (glyph làm texture trên đế) và ghi vào manifest.
- Rollback: xoá hai file mã và test.
