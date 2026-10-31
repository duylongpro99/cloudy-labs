---
title: "M6: twin và ghost kiến trúc mục tiêu"
description: "Người học làm lab ở terminal và thấy kiến trúc mục tiêu dạng ghost trên cảnh 3D; lab-server tự chạy check khi trạng thái đổi, ghost gắn vào tài nguyên thật qua resource_ids của check đã qua, panel check tô sáng node liên quan."
status: completed
priority: P1
effort: 30h
branch: master
tags: [feature, backend, frontend, api, m6]
blockedBy: [261030-1336-m5-chat-command-suggestions]
blocks: []
created: 2026-10-31
---

# M6: twin và ghost kiến trúc mục tiêu

## Overview

Mốc M6 trong [roadmap](../../docs/roadmap.md), phạm vi PRD F6.1–F6.4. Contract (outcome, constraints, non-goals, acceptance) đã chốt ở [báo cáo brainstorm](../reports/brainstorm-261031-0830-m6-twin-ghost.md). Hai quyết định của người dùng ngày 2026-10-31: check **chạy tự động**, ghost **gắn với tài nguyên thật qua check**.

`blockedBy` M5 chỉ theo thứ tự roadmap. M6 không dùng code chat; phần còn dở của M5 (chạy bộ câu hỏi với LLM thật) không chặn việc làm M6.

Lab 6 và 7 thật chưa có, nên M6 làm trên `fixture-lab-06` và `fixture-lab-07`. Khi có lab thật, tác giả lab viết `target` theo schema của plan này.

## Hiện trạng đã kiểm

- Hub publish graph khi `content_hash` đổi; debounce 0,15 giây sau sự kiện ghi của api-tap, poll 5 giây (`server/src/cloudy_labs/server/hub.py`). Tin nhắn `/ws` hiện có: `graph`, `api-event`.
- `run_checks(loaded, CheckContext)` trả `CheckResult(passed, message, resource_ids, check_id)` (`checks.py`). `Engine.check` luôn ghi progress (`engine.py`).
- `current_lab()` trong `server/app.py` đọc attempt mới nhất theo từng request, nên `labctl start` hay `reset` ở terminal khác có hiệu lực ngay.
- Id node trong graph: `vpc-…`, AZ là `{vpc_id}/{az}`, subnet có kind `subnet-public` hoặc `subnet-private`, NAT nằm trong subnet, IGW và route table nằm trong VPC, key pair và Elastic IP nằm trong region, SG nằm trong VPC, instance nằm trong subnet (`graph/collector.py`). SG và EIP đã gắn thì web vẽ thành badge trên host (`graph-to-scene.ts`).
- Checker fixture: `nat_in_public_subnet` của Lab 6 không trả allocation id của EIP. Lab 7 không có check nào trả id của VPC và subnet do `setup` dựng sẵn.
- Web tính layout từ cây `Fixture` (`scene/layout.ts`); `LiveScene` nhận `SceneGraph`.

## Quyết định thiết kế

- **Schema `target`** (thay `dict[str, Any]` trong `labs/schema.py`):
  ```yaml
  target:
    nodes:
      - {id: vpc, kind: vpc, label: VPC 10.66.0.0/16, checks: [vpc-exists]}
      - {id: az-1, kind: az, parent: vpc, label: AZ thứ nhất}
      - {id: public-1, kind: subnet-public, parent: az-1, label: Public 1, checks: [subnets-two-azs]}
  ```
  Validate: id duy nhất (slug), `kind` thuộc `graph.schema.Kind` trừ `region`, `parent` trỏ node khác trong target (thiếu nghĩa là region), cặp cha–con đúng như collector đặt (bảng `PARENT_KINDS`), `checks` trỏ check id có thật, node không phải `az` phải có ít nhất một check, `az` không được có check. Không có vòng.
- **Gắn ghost** (hàm thuần `bind_target(target, results, graph)` trong module mới `cloudy_labs/twin.py`):
  1. Duyệt node target theo thứ tự khai báo. Node có check được gắn khi mọi check của nó đã qua.
  2. Ứng viên là các id trong hợp `resource_ids` của các check đó, có trong graph, đúng `kind`, chưa bị ghost khác lấy, và nếu cha (target) đã gắn thì cha trong graph phải khớp. Với cha là `az` chưa gắn, ứng viên được sắp theo (cha trong graph, id) để ghost con của AZ thứ nhất lấy subnet ở AZ đứng đầu theo thứ tự chữ cái.
  3. Lấy ứng viên đầu tiên. Không còn ứng viên thì ghost chưa gắn, dù check đã qua (cảnh vẫn đúng, chỉ thiếu dấu đạt).
  4. Node `az` được gắn vào cha trong graph của con đầu tiên đã gắn, nếu mọi con đã gắn cùng một AZ.
  5. Đầu ra: `ghosts` (node chưa gắn, kèm cha đã giải thành ghost id hoặc id thật) và `bound` (target id → id thật).
- **Chạy check tự động** (`TwinRunner` trong module mới `cloudy_labs/server/twin_runner.py`):
  - Kích hoạt khi hub publish graph mới, và ở mỗi nhịp poll khi còn check chưa qua (để bắt check như `web-server-answers`, đổi kết quả mà graph không đổi).
  - Một lượt chạy một lúc, lượt mới đến khi đang chạy thì chạy đúng một lượt nữa sau đó, giống `GraphHub.refresh`. Chạy `run_checks` trong thread.
  - Graph đang `emulator-down` hoặc không có attempt mở thì không chạy check; trạng thái check là `pending`.
  - Ghi progress bằng `Progress.record_if_changed(attempt_id, results)`: chỉ ghi khi `(check_id, passed, message, resource_ids)` khác lần ghi cuối của attempt đó. `labctl check` vẫn luôn ghi.
  - Broadcast `{"type": "twin", "twin": {...}}` trên `/ws` khi nội dung đổi; client mới kết nối nhận tin `twin` hiện tại ngay sau `graph`.
- **Tin `twin`** (pydantic, camelCase, golden file cho web test như graph):
  `{lab, attempt, checks: [{id, task, description, status: "passed"|"failed"|"pending", message, resourceIds}], ghosts: [{id, kind, label, parent, checks}], bound: {targetId: resourceId}}`. Lab không có `target` thì `ghosts` và `bound` rỗng.
- **Web**: hàm thuần `mergeTwin(scene, twin)` thêm ghost vào `SceneGraph` dưới dạng `FixtureNode` có `ghost: true`, trước `computeLayout`. Ghost vẽ mờ, viền nét đứt, nhãn có chữ "mục tiêu", không bắt pointer cho builder. Node thật có id nằm trong `bound` có dấu đạt. Panel check liệt kê theo task; bấm một check thì tô sáng `resourceIds` của nó cùng ghost khai báo check đó. Công tắc ẩn/hiện ghost (nhớ trong `localStorage`, khoá `cloudy-labs:ghost`).
- Fixture được sửa để chạy được với cơ chế gắn qua check:
  - Lab 6: `nat_in_public_subnet` trả thêm allocation id của EIP.
  - Lab 7: thêm task `network` và check `network-ready` trả id VPC, subnet public và IGW mà `setup` dựng. Lab thật cũng phải làm như vậy cho phần hạ tầng có sẵn (ghi vào docs).

## Non-goals

- Nội dung Lab 6 và 7 thật; lab ngoài 6 và 7 (M7).
- Ghost cho cạnh (route, association, `uses-key`). Chỉ ghost cho node; xem câu hỏi mở.
- Đổi contract checker hay `labctl check`.
- Terraform trong test tự động (chỉ CLI và SDK).

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Schema `target`, hàm gắn ghost và target cho fixture](./phase-01-target-schema-and-binding.md) | Completed |
| 2 | [Chạy check tự động và tin `twin` trên /ws](./phase-02-auto-check-and-twin-message.md) | Completed |
| 3 | [Web: ghost trong cảnh](./phase-03-web-ghost-layer.md) | Completed |
| 4 | [Web: panel check và tô sáng](./phase-04-web-check-panel.md) | Completed |
| 5 | [Kiểm thử đầu-cuối và tài liệu](./phase-05-e2e-and-docs.md) | Completed |

Phase 2 cần Phase 1. Phase 3 cần golden `twin` của Phase 2. Phase 4 cần Phase 3 (dùng chung state twin trong web). Phase 5 cần tất cả.

## Luồng

```text
terminal / SDK ─► api-tap ─► Floci
                     │ sự kiện ghi
                     ▼
               GraphHub.refresh ─► graph mới ─► /ws {type: graph}
                     │ publish hoặc poll (khi còn check chưa qua)
                     ▼
               TwinRunner: current_lab() ─► run_checks ─► record_if_changed
                     │                         bind_target(target, results, graph)
                     ▼
               /ws {type: twin} ─► web: mergeTwin ─► layout ─► ghost + dấu đạt + panel check
```

## Acceptance criteria

Theo báo cáo brainstorm, mục Acceptance criteria 1–8. Bổ sung từ scout:
- Ghost `web-server-answers` của Lab 7 chuyển trạng thái khi UserData xong mà không cần graph đổi (nhờ chạy lại ở nhịp poll).
- Độ trễ từ lúc tài nguyên hiện trong cảnh đến lúc ghost liên quan đặc ≤ 3 giây trên fixture, đo và ghi ở `notes/e2e-results.md`.

## Rủi ro

- Lượt check của Lab 7 có `web-server-answers` gọi HTTP tới instance, có thể chậm. Đo ở Phase 5; nếu một lượt quá 3 giây thì ghi lại và cân nhắc timeout của checker fixture, không đổi contract.
- `record_if_changed` so cả `message`; checker trả message chứa giá trị thay đổi liên tục sẽ ghi nhiều. Checker fixture hiện chỉ dùng id và trạng thái, chấp nhận.
- Chạy check ở nhịp poll khi còn check trượt thêm vài lệnh `Describe*` mỗi 5 giây. Không ghi sự kiện tap nên không gây vòng collect.

## Validation Log

### Verification Results
- Claims checked: 14 (đường dẫn file, test, script web, id node trong collector, `resource_ids` của checker fixture)
- Verified: 11 | Failed: 3 | Unverified: 0
- Tier: Full
- Failures đã sửa: test schema là `server/tests/test_schema.py` (không phải `test_labs.py`); test chạy với emulator thật đánh dấu `docker` và đặt tên `*_docker.py`; web không có script lint, dùng `npm run typecheck`.

### Quyết định (người dùng, 2026-10-31)
- Ghost chỉ cho node, không cho cạnh.
- Lab 7 fixture thêm task `network` và check `network-ready` để hạ tầng do `setup` dựng được gắn qua check.
- Ghost bật mặc định kể cả khi dùng builder và chat, có công tắc ẩn/hiện.
