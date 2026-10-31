---
phase: 4
title: "Web: panel check và tô sáng"
status: completed
priority: P1
effort: "4h"
dependencies: [3]
---

# Phase 4: web, panel check và tô sáng

## Goal

Panel check hiện trạng thái từng check theo task; bấm một check thì tô sáng các node liên quan trong cảnh.

## Files to Create / Modify

- Create: `web/src/twin/check-panel.tsx`, `web/src/twin/check-panel.test.tsx`.
- Create: `web/src/twin/highlight.ts`, `web/src/twin/highlight.test.ts` — tập node cần tô sáng cho một check.
- Modify: `web/src/scene/live-scene.tsx` — prop `highlighted: ReadonlySet<string>`; vẽ viền sáng cho node và tray có trong tập, làm mờ phần còn lại.
- Modify: `web/src/app.tsx` — đặt panel cạnh panel builder và chat, state check đang chọn.

## Tasks & Steps

1. Panel nhóm check theo task (thứ tự task trong lab), mỗi check hiện trạng thái (đạt, chưa đạt, đang chờ), `description` và `message` mới nhất. Không có lab mở thì panel nói chạy `labctl start`.
2. `highlightFor(checkId, twin, scene)`: `resourceIds` của check có trong scene (kể cả id badge `id@host` qua `resourceId`), cộng ghost có check đó.
3. Bấm check thì chọn, bấm lại hoặc Esc thì bỏ. Đổi attempt (sau reset) thì bỏ chọn.
4. Panel dùng được bằng bàn phím: mỗi check là một button có `aria-pressed`.

## Verification

- `cd web && npx vitest run src/twin`
- Test tối thiểu: nhóm theo task đúng thứ tự; trạng thái hiển thị đúng ba loại; bấm và bấm lại; tập tô sáng gồm id badge và ghost; đổi attempt bỏ chọn.
- `npm run typecheck` xanh.
