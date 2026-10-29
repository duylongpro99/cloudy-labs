---
phase: 5
title: "Hành vi cảnh: hoạt ảnh, lệnh bay, panel, cạnh"
status: completed
priority: P1
effort: "5h"
dependencies: [4]
---

# Phase 5: Hành vi cảnh: hoạt ảnh, lệnh bay, panel, cạnh

## Goal

Cảnh phản ứng đúng khi graph đổi lúc đang chạy: object mới hiện dần mà object đang hiện dở không chạy lại, object bị xoá biến mất có hoạt ảnh, lệnh API "bay" tới dịch vụ, bấm node mở panel thuộc tính (F3.4–F3.6). Đóng hai việc chuyển sang từ plan thư viện object.

## Files to Create / Modify

- Modify: `web/src/scene/aws-objects/entrance.ts`, `entrance.test.ts`, `aws-object-layer.tsx` (lưu thời điểm bắt đầu theo id; hoạt ảnh thoát)
- Modify: `web/src/scene/tray-layer.tsx` (khay mới hiện dần, khay bị xoá mờ dần)
- Modify: `web/src/scene/edge-layer.tsx` (kiểu cạnh `route`, `association`, `attached`, `uses-key`; nhãn CIDR cho `route`)
- Create: `web/src/scene/api-fly-layer.tsx` (hạt bay từ mép cảnh tới node đích)
- Create: `web/src/scene/property-panel.tsx` (panel HTML ngoài canvas)
- Create: `web/scripts/check-live.mjs` (kiểm tra trình duyệt với WebSocket giả qua `page.routeWebSocket` của playwright-core)
- Modify: `web/src/scene/live-scene.tsx`

## Tasks & Steps

1. **Giữ tiến độ hoạt ảnh (việc chuyển sang 1).** Thay tập `shown` bằng `Map<id, startMs>`. `entranceDelays` trở thành `entranceStarts(ids, starts, now)`: id đã có giữ nguyên `startMs`, id mới nhận `now + stagger`. Tiến độ = `(now - startMs) / ENTRANCE_MS`. Test: placement đổi ở giữa hoạt ảnh (t = 200 ms) thì object đó ở t = 250 ms có scale bằng `entranceScale(250/450)`, không quay về 0.
2. **Hoạt ảnh thoát (F3.6).** Id biến mất khỏi placement được giữ lại trong một danh sách "đang thoát" trong `EXIT_MS = 300`, scale về 0 rồi bỏ hẳn. Id quay lại trong lúc đang thoát thì hiện lại từ scale hiện tại. Khay làm tương tự bằng độ trong suốt. Sau khi mọi hoạt ảnh xong thì gọi `onSettled` để cập nhật bóng một lần, như hiện tại.
3. **Lệnh bay (F3.6).** Với mỗi `api-event` có `write`, chọn node đích theo service + action: `CreateVpc` → VPC mới nhất trong lần graph kế tiếp, `RunInstances` → instance mới, các action khác → node cùng loại vừa đổi; không tìm được thì bay tới khay Region. Hạt bay theo đường cong 600 ms từ mép trên trái, kèm nhãn action ngắn. Tối đa 8 hạt cùng lúc; vượt thì bỏ hạt cũ nhất. Ở chế độ `frameloop="demand"`, chỉ gọi `invalidate()` khi còn hạt.
4. **Panel thuộc tính (F3.4).** Bấm node (đã có `onSelect`) mở panel bên phải: tên, kind, id (có nút chép), các `props` dạng bảng, danh sách cạnh vào/ra, và cảnh báo của node nếu có (`privateIpOutOfCidr`, `note` về UserData, `hostPorts` hiển thị thay IP công khai). Bấm nền hoặc Esc thì đóng. Node bị xoá trong lúc panel mở thì panel ghi "Tài nguyên đã bị xoá" thay vì đóng đột ngột.
5. **Cạnh (F3.5).** `route` liền, màu theo đích (IGW/NAT), có nhãn CIDR; `association` nét đứt mảnh; `uses-key` nét chấm. `attached` vẽ bằng badge nên không vẽ đường. Màu lấy từ token chủ đề, đủ tương phản ở cả hai chủ đề.
6. **Kiểm tra trình duyệt (việc chuyển sang 2)** `check-live.mjs`: mở `http://127.0.0.1:5174/` với Chrome qua playwright-core, chặn `/ws` bằng `routeWebSocket` và tự gửi các graph:
   - Gửi graph A rồi graph A + 1 instance: chỉ id mới có scale < 1 ở khung hình kế tiếp (đọc qua `window.__scene`, mở rộng probe để trả scale theo id).
   - Gửi graph B khi object của A đang hiện dở: scale của object đó không giảm.
   - Gửi graph bỏ một instance: instance có scale giảm dần rồi mất khỏi probe.
   - Gửi `api-event`: probe báo có hạt bay.
   - Bấm vào instance (toạ độ từ `screenPoint`): panel hiện đúng id.
   - Chụp ảnh sáng và tối vào `plans/261029-1006-m2-resource-graph-collector-scene/notes/`.

## Verification

- `cd web && pnpm typecheck && pnpm test`
- `cd web && pnpm dev` (một tiến trình, cổng 5174) rồi `node scripts/check-live.mjs`; dừng dev server khi xong.
- Xem ảnh chụp bằng mắt: nhãn đọc được, cạnh không đè nhãn ở mức zoom mặc định.

## Risk & Rollback

Hạt bay và hoạt ảnh thoát làm canvas vẽ liên tục, có thể ảnh hưởng hiệu năng khi rảnh. Kiểm bằng probe số khung hình: rảnh 10 giây phải là 0 khung hình như ở M0. Rollback từng phần được: mỗi hành vi nằm ở layer riêng.
