---
phase: 4
title: "Component R3F, instancing và trang gallery"
status: completed
priority: P1
effort: "4h"
dependencies: [3]
---

# Phase 4: Component R3F, instancing và trang gallery

## Goal

Đóng gói thư viện thành component R3F vẽ được hàng trăm object với ít draw call, hỗ trợ hover/chọn, và có một trang gallery để kiểm bằng mắt mọi object ở cả hai chủ đề.

## Files to Create / Modify

- Create: `web/src/scene/aws-objects/aws-object-layer.tsx`. Nhận danh sách `{ id, kind, position }`, gom theo `kind`, và vẽ mỗi `kind × phần` (đế, glyph) bằng một `InstancedMesh`.
- Create: `web/src/scene/aws-objects/highlight-overlay.tsx`. Một mesh thường đặt trùng vị trí node đang hover/chọn, có `Outlines` với độ dày theo đơn vị thế giới. M0 cho thấy `screenspace` vỡ dưới camera trực giao.
- Create: `web/src/scene/aws-objects/index.ts`. Export công khai: `AwsObjectLayer`, `manifest`, kiểu `AwsKind`.
- Create: `web/src/gallery/aws-objects-gallery.tsx`, cùng route hoặc query `?view=gallery`. Lưới mọi object kèm nhãn tên loại, có nút chuyển chủ đề.
- Nếu `web/` chưa tồn tại: tạo khung Vite + React + TS bằng pnpm, ghim đúng phiên bản của `spikes/m0-render/package.json`, và dùng `<Canvas orthographic>` (cạm bẫy số 1 trong báo cáo M0).

## Tasks & Steps

1. Viết `AwsObjectLayer`: mỗi lần dữ liệu đổi thì cập nhật `instanceMatrix`; raycast theo `instanceId` để biết node đang hover.
2. Hoạt ảnh xuất hiện: dùng một thuộc tính scale cho từng instance, cập nhật trong `useFrame` khi còn hoạt ảnh và gọi `invalidate()`. Không dùng react-spring cho từng node nữa, vì cần giữ 1 draw call cho mỗi loại.
3. Viết `highlight-overlay`.
4. Viết trang gallery, có chế độ chụp ảnh tự động như `?mode=idle` của M0.
5. Gắn `AwsObjectLayer` vào cảnh mẫu 200 node, thay cho khối và icon phẳng của M0. Đây là cảnh phục vụ Phase 5.

## Verification

- `pnpm tsc --noEmit` không lỗi.
- Trang gallery hiển thị đủ mọi `kind` trong manifest ở cả hai chủ đề. Chụp ảnh lưu vào `plans/261028-0230-m2-aws-icon-3d-object-library/notes/`.
- Hover và chọn một instance thì đúng node đó được viền, kiểm bằng Playwright: di chuột tới toạ độ đã biết rồi đọc id đang được chọn.

## Rủi ro và rollback

- Nếu raycast theo instance chậm khi có 179 instance, bật BVH (drei `Bvh`) hoặc chỉ raycast khi chuột di chuyển (mặc định của R3F).
- Rollback: cảnh quay về khối và icon phẳng của M0.
