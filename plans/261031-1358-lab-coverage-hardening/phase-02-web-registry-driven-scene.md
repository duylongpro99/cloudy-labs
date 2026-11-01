---
phase: 2
title: "Web đọc registry, node dự phòng"
status: completed
priority: P1
effort: "28h"
dependencies: [1]
---

# Phase 2: web đọc registry, node dự phòng

## Goal

Cảnh 3D, palette, nhãn và hiệu ứng "lệnh bay" lấy thông tin loại tài nguyên từ registry của server. Kind lạ hoặc thiếu icon hiện thành node dự phòng; parser không bao giờ ném lỗi.

## Hiện trạng

- Bảng cứng trong web:
  - `scene/aws-objects/manifest.ts` (`AwsKind`, `MANIFEST`);
  - `object-specs.ts` (`BLOCK_HEIGHT`);
  - `object-theme.ts` (theo `IconCategory`);
  - `layout.ts` (`isGroup`, `KIND_ORDER`);
  - `graph-to-scene.ts` (`HOST_KINDS`, attachment);
  - `graph/fly-target.ts` (`ACTION_KINDS`);
  - `builder/drop-targets.ts` (`KIND_LABEL`).
- **[Red team] Các chỗ khác ném lỗi hoặc giả định danh sách kind/edge cố định:**
  - `web/src/graph/types.ts`: `REQUIRED_KINDS` và `EDGE_KINDS`. `parseGraph` và `parseTwin` ném lỗi với kind hoặc edge lạ (dòng 5, 10, 31, 82, 94, 111);
  - `edge-layer.tsx:27-31` (style theo edge kind);
  - `label-layer.tsx`, `aws-objects/aws-object-layer.tsx`;
  - `scene/fixture.ts`, `aws-objects/index.ts`;
  - `object-specs.ts:35` và `geometry-cache.ts:14-17` ném lỗi với kind lạ.
- **[Red team] Icon được bundle lúc build** bằng `import.meta.glob` trong `web/src/scene/aws-objects/geometry-cache.ts:11-19`, từ `web/src/scene/aws-objects/icons/` (có `NOTICE.md`). Không tồn tại `web/public/icons`.
- `scripts/import-aws-icons.mjs` đọc `MANIFEST` để chép icon.

## Thiết kế

- Server có `GET /api/registry`, trả:
  - `kinds`: mỗi kind gồm `kind`, `service`, `label`, `role` (`group` | `block` | `tray-badge` | `attach-badge` | `outline-only`), `category`, `icon`, `order`, `host`, `attachTo`, và `actions` (danh từ của action API cho fly-target, ví dụ `DBInstance` cho `CreateDBInstance`);
  - **[Red team]** `edgeKinds`: mỗi edge kind có `style` (`contain` | `attach` | `route` | `reference` | `replica`), để `edge-layer` vẽ theo vai trò thay vì theo tên.
- Registry có golden `fixtures/graph/registry.json`; web test đọc nó như golden graph.
- Web nạp registry trước khi vẽ. Các bảng cứng ở trên thành hàm tra registry. Giá trị riêng của 12 kind cũ chuyển vào YAML (`view.height`, `view.role`...).
- **[Red team] Parser chịu lỗi:**
  - `parseGraph` và `parseTwin` nhận mọi chuỗi kind và edge kind;
  - kind không có trong registry thì dùng view dự phòng;
  - edge kind lạ thì vẽ style `reference`;
  - chỉ ném lỗi khi JSON sai cấu trúc (thiếu `id`, `parent` trỏ node không có).
- **Node dự phòng** dùng cho kind không có trong registry của web, hoặc có nhưng thiếu icon:
  - khối dùng `generic-resource.svg`;
  - nhãn ghi tên service và id;
  - viền vàng báo "chưa hỗ trợ đầy đủ".
- **[Red team] Icon vẫn được bundle.** Thêm một kind mới cần một SVG trong `web/src/scene/aws-objects/icons/` rồi build lại web. `import-aws-icons.mjs` đọc registry qua lệnh Python xuất JSON (`uv run python -m cloudy_labs.registry export`), không cần server chạy. Thiếu icon thì script báo tên kind và đường dẫn.
- Màu category theo bảng màu chính thức của AWS Architecture Icons: Compute, Storage, Database, Networking, Security, App Integration, Management, Analytics, Developer Tools và các nhóm còn lại. Bổ sung vào `OBJECT_THEMES` cho cả hai chủ đề.

## Files to Create / Modify

- Modify: `server/src/cloudy_labs/server/app.py`. Thêm `GET /api/registry`.
- Modify: `server/src/cloudy_labs/registry/__init__.py`. Thêm lệnh `export`.
- Create: `server/tests/fixtures/graph/registry.json` (golden) và test trong `server/tests/test_app.py`.
- Create: `web/src/registry/registry.ts` (kiểu, nạp, tra cứu), `web/src/registry/use-registry.ts`.
- Modify: `web/src/graph/types.ts`. Parser chịu lỗi.
- Modify: `web/src/scene/aws-objects/manifest.ts`, `object-specs.ts`, `object-theme.ts`, `geometry-cache.ts`, `aws-objects/index.ts`.
- Modify: `web/src/scene/layout.ts`, `object-placements.ts`, `edge-layer.tsx`, `label-layer.tsx`, `aws-objects/aws-object-layer.tsx`, `scene/fixture.ts`.
- Modify: `web/src/graph/graph-to-scene.ts`, `web/src/graph/fly-target.ts`, `web/src/builder/drop-targets.ts`, `web/src/builder/palette.tsx`, `web/src/gallery/aws-objects-gallery.tsx`.
- Create: `web/src/scene/aws-objects/icons/generic-resource.svg` (tự vẽ) và ghi vào `icons/NOTICE.md`.
- Modify: `scripts/import-aws-icons.mjs`.
- Modify: các test web đã thấy khi scout: `types.test.ts`, `manifest.test.ts`, `layout.test.ts`, `graph-to-scene.test.ts`, `fly-target.test.ts`, `drop-targets.test.ts`, `edge-layer` test.

## Tasks & Steps

1. Viết endpoint (kinds và edgeKinds), lệnh export và golden registry.
2. **[Red team]** Sửa `types.ts` trước: parser chịu lỗi. Test: graph có kind `mystery-thing` và edge `weird-link` thì parse được, không ném lỗi.
3. Viết `registry.ts`. Thay từng bảng cứng bằng tra cứu, giữ giá trị cũ qua YAML. Chạy test web sau mỗi bảng.
4. Viết node dự phòng: `object-specs` và `geometry-cache` không ném lỗi với kind lạ.
5. Bổ sung màu category cho toàn bộ category AWS ở hai chủ đề; kiểm độ tương phản trên nền tối.
6. Sửa script icon.
7. Gallery hiện mọi kind trong registry, kể cả node dự phòng, để soát bằng mắt.
8. Đo lại hiệu năng 200 node (`web/src/bench`) ở hai chủ đề.

## Verification

- `cd web && npm test && npm run typecheck && npm run build`
- `node web/scripts/check-scene.mjs`, `e2e-builder-lab-06.mjs` và `e2e-builder-lab-07.mjs` vẫn đạt.
- Test: graph có một kind lạ, một edge lạ và một kind trong `test-only.yaml` thiếu icon. Parser, layout, scene và palette không ném lỗi; kind lạ hiện thành node dự phòng.
- Bench: ≥ 50 fps với 200 node; ghi số đo vào `notes/perf-results.md`.

## Risk / Rollback

- Web phải chờ registry trước lần vẽ đầu tiên. Nạp song song với graph và hiện trạng thái đang tải; cảnh không bị chặn quá một lần round-trip.
