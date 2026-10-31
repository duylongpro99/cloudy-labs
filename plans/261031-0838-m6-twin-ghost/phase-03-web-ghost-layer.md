---
phase: 3
title: "Web: ghost trong cảnh"
status: completed
priority: P1
effort: "7h"
dependencies: [2]
---

# Phase 3: web, ghost trong cảnh

## Goal

Cảnh 3D vẽ ghost của kiến trúc mục tiêu đúng chỗ lồng nhau, đánh dấu node thật đã đạt, và có công tắc ẩn/hiện ghost.

## Files to Create / Modify

- Modify: `web/src/graph/types.ts` — kiểu `TwinState`, `ServerMessage` thêm `{type: 'twin'}`, `parseTwin`.
- Modify: `web/src/graph/graph-client.ts` — nhận tin `twin`, expose trong `useResourceGraph`.
- Create: `web/src/graph/merge-twin.ts`, `web/src/graph/merge-twin.test.ts`.
- Modify: `web/src/scene/fixture.ts` — `FixtureNode.ghost?: boolean`.
- Modify: `web/src/scene/layout.ts` (chỉ nếu cần) — ghost là node bình thường đối với layout; kiểm `layout.test.ts` vẫn xanh.
- Modify: lớp vẽ object và tray (`scene/aws-objects`, `scene/tray-layer.tsx`, `scene/label-layer.tsx`) — kiểu ghost: vật liệu mờ, viền nét đứt, không đổ bóng, nhãn "mục tiêu"; dấu đạt cho node thật trong `bound`.
- Modify: `web/src/scene/live-scene.tsx` — ghost không nhận hover, select, drop hay connect của builder.
- Create: `web/src/scene/use-ghost-toggle.ts` (khoá `cloudy-labs:ghost`, try/catch quanh `localStorage` như `use-practice.ts`).
- Modify: `web/src/app.tsx` — nối twin vào `graphToScene` → `mergeTwin` → `LiveScene`; công tắc ghost cạnh các điều khiển hiện có.

## Tasks & Steps

1. Types và `parseTwin` mirror `TwinState` của server; test đọc golden `twin` của Phase 2 (giống cách test đọc golden graph).
2. `mergeTwin(scene, twin, showGhosts)`: thêm ghost thành `FixtureNode` (`ghost: true`, `parent` là ghost id hoặc id thật); ghost SG và EIP luôn là node (không thành badge); trả thêm `achieved: Set<string>` từ `bound`. Cha là id thật không còn trong graph (vừa bị xoá) thì ghost treo ở cha ghost hoặc region, không ném lỗi.
3. Kiểu vẽ ghost theo cả chủ đề sáng và tối (`scene/theme.ts`); ghost phải phân biệt rõ với node thật ở cả hai chủ đề.
4. Builder: drop vào tray ghost không được chấp nhận (`accepts` trả false cho ghost), probe bỏ qua ghost.
5. Không làm tụt hiệu năng: đo lại bench 200 node có thêm ~20 ghost, vẫn ≥ 50 fps (NFR).

## Verification

- `cd web && npx vitest run src/graph src/scene`
- Test `merge-twin.test.ts` tối thiểu: twin rỗng không đổi scene; ghost con của id thật nằm đúng cha; ghost con của ghost; `showGhosts=false` bỏ mọi ghost nhưng vẫn giữ `achieved`; cha thật biến mất không ném lỗi.
- `npm run typecheck` xanh (web không có script lint).
- Kiểm bằng mắt trên `labctl serve` với `fixture-lab-06` mới start: thấy đủ ghost, chụp màn hình sáng và tối vào `notes/`.
