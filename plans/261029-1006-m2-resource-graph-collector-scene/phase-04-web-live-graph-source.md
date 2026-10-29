---
phase: 4
title: "Web: nguồn dữ liệu trực tiếp và bố cục xác định"
status: completed
priority: P1
effort: "4h"
dependencies: [2, 3]
---

# Phase 4: Web: nguồn dữ liệu trực tiếp và bố cục xác định

## Goal

Màn hình mặc định của web vẽ cảnh từ graph mà lab-server đẩy qua WebSocket, chỉ phụ thuộc graph (NFR4), với bố cục chỉ phụ thuộc trạng thái chứ không phụ thuộc thứ tự dữ liệu (F3.3).

## Files to Create / Modify

- Create: `web/src/graph/types.ts` (type TS của resource graph, khớp schema pydantic)
- Create: `web/src/graph/graph-client.ts` (hook `useResourceGraph`: WS, reconnect, trạng thái kết nối)
- Create: `web/src/graph/graph-to-scene.ts` (graph → `Fixture`: node, edge, attachment)
- Create: `web/src/graph/graph-to-scene.test.ts`, `web/src/scene/layout.test.ts`
- Create: `web/src/scene/live-scene.tsx` (cảnh trực tiếp, tách khỏi `ArchitectureScene` của bench)
- Modify: `web/src/scene/layout.ts` (sắp xếp con xác định, bố cục cho cây rỗng), `web/src/scene/fixture.ts` (nới `kind` nếu cần), `web/src/scene/edge-layer.tsx` (nhận kiểu cạnh)
- Modify: `web/src/app.tsx` (màn hình `live` mặc định, bench ở `?view=bench`, gallery giữ nguyên), `web/scripts/run-chrome-bench.mjs`, `web/scripts/check-scene.mjs` (thêm `view=bench` vào URL)
- Modify: `web/vite.config.ts` (proxy `/api` và `/ws` → `http://127.0.0.1:8730`, `ws: true`)

## Tasks & Steps

1. **types.ts:** chép đúng tên trường của schema Phase 2. Thêm hàm `parseGraph(json): ResourceGraph` kiểm tối thiểu (có `nodes/contains/edges`, `kind` thuộc tập biết trước) và ném lỗi rõ.
2. **graph-to-scene.ts:**
   - `contains` → `parent` của `FixtureNode`.
   - `security-group` và `elastic-ip` có cạnh `attached` → `FixtureAttachment` gắn lên host (đúng cách thư viện object vẽ badge). SG chưa gắn vào gì: manifest cho SG vai trò `attach-badge`, nên kiểm `AwsObjectLayer` có vẽ được nó như node lá không; nếu không thì gắn badge lên khay VPC của nó.
   - Cạnh `route`, `association`, `uses-key` → `FixtureEdge` kèm `kind` để `EdgeLayer` tô khác nhau.
   - Giữ `props` theo id để Phase 5 mở panel.
   - Graph rỗng hoặc `emulator-down` → chỉ còn node Region.
3. **layout.ts:** sắp xếp con của mỗi nhóm theo `(thứ tự kind cố định, id)` trước khi đo và đặt. Thêm test: hai graph cùng nội dung nhưng thứ tự khác cho layout giống hệt; thêm một subnet không làm đổi vị trí tương đối của các subnet đã có trong cùng AZ (chỉ dịch chuyển phía sau nó).
4. **graph-client.ts:** `new WebSocket(`${location.origin.replace('http','ws')}/ws`)`; nhận `graph` thì thay state (chỉ khi `version` lớn hơn), nhận `api-event` thì đẩy vào một hàng đợi ngắn cho Phase 5. Mất kết nối thì thử lại 0,5 → 5 s. Trạng thái: `connecting | live | emulator-down | disconnected`.
5. **live-scene.tsx:** dùng lại `PostFx`, ánh sáng, `TrayLayer`, `AwsObjectLayer`, `LabelLayer`, `EdgeLayer` của `architecture-scene.tsx`. Tách phần dựng ánh sáng + camera dùng chung vào một component nhỏ nếu cả hai cảnh đều cần, để không chép code. Camera tự khớp ở lần đầu có graph không rỗng và khi bấm nút "Vừa khung"; các lần cập nhật sau giữ nguyên camera người học đang xem.
6. **app.tsx:** không có `view` thì vào màn hình live; `?view=bench` là màn hình bench cũ (giữ nguyên tham số khác); `?view=gallery` giữ nguyên. Panel trên cùng hiện trạng thái kết nối, `version`, số node, cảnh báo của graph (ví dụ IP ngoài CIDR), và nút chủ đề. Chủ đề mặc định theo `prefers-color-scheme` và đổi theo khi hệ thống đổi, trừ khi người học đã bấm chọn tay (F3.9).
7. **Test hợp đồng:** `graph-to-scene.test.ts` đọc `../../server/tests/fixtures/graph/lab-06-07.graph.json`, chạy `parseGraph` → adapter → `computeLayout` → `scenePlacements` không lỗi; kiểm instance nằm trong đúng subnet, SG là badge trên instance, có cạnh route tới IGW và NAT.

## Verification

- `cd web && pnpm typecheck && pnpm test`
- `grep -rnE ':456[67]' web/src` không có kết quả (NFR4).
- Thủ công: `labctl up`, `labctl serve`, `pnpm dev`, mở `http://127.0.0.1:5174`; chạy `lab-06-07.sh` và thấy cảnh dựng dần; `?view=bench` và `?view=gallery` vẫn chạy như trước.

## Risk & Rollback

Đổi màn hình mặc định làm script bench cũ mở nhầm màn hình; bước 6 sửa luôn hai script. Rollback: `app.tsx` trả về mặc định cũ; các module mới trong `web/src/graph/` không ảnh hưởng gì khác.
