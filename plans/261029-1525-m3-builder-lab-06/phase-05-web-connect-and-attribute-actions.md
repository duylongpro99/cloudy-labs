---
phase: 5
title: "Web: thao tác nối và thuộc tính"
status: completed
priority: P1
effort: "5h"
dependencies: [4]
---

# Phase 5: Web: thao tác nối và thuộc tính

## Goal

Người học tạo quan hệ bằng cách kéo cạnh giữa hai object (F4.6): attach IGW vào VPC, thêm route từ Route Table tới IGW hay NAT, gắn Route Table vào subnet; và bật hai thuộc tính Lab 6 từ panel thuộc tính.

## Files to Create / Modify

- Create: `web/src/builder/connect-rules.ts` (+ `.test.ts`): cặp (nguồn, đích) nào cho ra op nào
- Create: `web/src/scene/connect-line.tsx`: đường tạm từ object nguồn tới con trỏ
- Modify: `web/src/scene/aws-objects/aws-object-layer.tsx` (tay cầm kéo cạnh trên object được chọn), `web/src/builder/use-builder.ts`, `web/src/builder/build-form.tsx`
- Modify: `web/src/scene/property-panel.tsx` (nút thao tác thuộc tính)
- Modify: `server/src/cloudy_labs/graph/collector.py` (prop `enableDnsHostnames` qua `describe-vpc-attribute` cho từng VPC, prop `mapPublicIpOnLaunch` từ `describe-subnets`), `server/tests/fixtures/graph/lab-06-07.graph.json`, `server/tests/test_collector.py`

## Tasks & Steps

- [x] Quy tắc nối:

  | nguồn | đích | op | form |
  |---|---|---|---|
  | igw (chưa attach) | vpc | `attach-internet-gateway` | không |
  | route-table | igw, nat | `create-route` | destination, mặc định `0.0.0.0/0`; NAT phải ở trạng thái `available` |
  | route-table | subnet-public, subnet-private | `associate-route-table` | không |

- [x] Chọn một object thì hiện tay cầm nối; kéo từ đó vẽ đường tạm, đích hợp lệ tô sáng, đích sai mờ đi. Thả lên đích hợp lệ mở form và panel lệnh như Phase 4 (dùng chung state máy, chỉ khác bước đầu).
- [x] Panel thuộc tính của VPC có nút "Bật DNS hostnames", của subnet có "Tự gán IP public"; bấm mở panel lệnh với op tương ứng. Nút ẩn khi thuộc tính đã bật (đọc từ props của node). Collector hiện chưa có hai prop này: `describe-vpcs` không trả `enableDnsHostnames`, nên phải gọi thêm `describe-vpc-attribute` cho mỗi VPC; đo lại độ trễ collector sau khi thêm.
- [x] Cạnh mới chỉ hiện khi graph mới có cạnh tương ứng (F4.5), giống Phase 4.

## Verification

- `cd web && pnpm test && pnpm typecheck`; `cd server && uv run pytest tests/test_collector.py tests/test_graph_schema.py` và cập nhật golden graph.
- Unit test `connect-rules` cho mọi cặp hợp lệ và một số cặp sai (igw → subnet, route-table → vpc).
- Kiểm trình duyệt: kéo cạnh route-table → igw mở form với destination `0.0.0.0/0` và lệnh `create-route` đúng id.

## Ghi chú triển khai

- Tay cầm và đường nối tạm nằm ở `scene/connect-line.tsx`.
