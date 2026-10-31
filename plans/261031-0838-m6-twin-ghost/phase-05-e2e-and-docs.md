---
phase: 5
title: "Kiểm thử đầu-cuối và tài liệu"
status: completed
priority: P1
effort: "5h"
dependencies: [1, 2, 3, 4]
---

# Phase 5: kiểm thử đầu-cuối và tài liệu

## Goal

Chứng minh các tiêu chí của M6 trên emulator thật với hai fixture, và cập nhật tài liệu.

## Files to Create / Modify

- Create: `server/tests/test_twin_docker.py` — đánh dấu `docker` như `test_builder_e2e_docker.py` và `test_latency_docker.py` (cần stack đã `labctl up`).
- Create: `plans/261031-0838-m6-twin-ghost/notes/e2e-results.md`.
- Modify: `docs/labctl.md` — mục mới "Twin và ghost"; mục "Viết một lab" thêm schema `target`, quy tắc gắn ghost, và việc phần hạ tầng do `setup` dựng cần một check trả id của nó.
- Modify: `docs/roadmap.md` — dòng M6: link plan, kết quả, "xong với lab fixture, chờ kiểm lại bằng Lab 6 + 7 thật"; cập nhật ngày ở đầu file.

## Tasks & Steps

1. `test_twin_docker.py` với `labctl serve` chạy trong test (cùng cách `test_builder_e2e_docker.py`), một client `/ws`:
   - `fixture-lab-06`: start → tin `twin` có đủ ghost, mọi check chưa đạt.
   - Tạo VPC bằng `aws --profile lab` → node VPC trong graph ≤ 2 giây; ghost VPC biến mất ≤ 3 giây sau đó.
   - Tạo subnet bằng boto3 qua profile `lab` → node trong graph ≤ 2 giây (F6.1 cho SDK).
   - Làm hết lab bằng CLI → `labctl check` đạt, tin `twin` không còn ghost.
   - `labctl reset fixture-lab-06` → tin `twin` có attempt mới, đủ ghost, không check nào đạt.
   - `fixture-lab-07`: start → `network-ready` đạt ngay sau setup, ghost VPC và subnet đã gắn; làm hết lab → `web-server-answers` đạt mà không cần graph đổi.
2. Đo và ghi vào `notes/e2e-results.md`: độ trễ graph và độ trễ ghost (trung vị của 5 lần), thời gian một lượt check của mỗi fixture, số dòng `check_runs` ghi thêm trong một lượt làm lab.
3. Kiểm tay trên trình duyệt: ghost, dấu đạt, panel, tô sáng, công tắc ghost, reset khi trang đang mở; chụp màn hình sáng và tối vào `notes/`.
4. Cập nhật docs như trên. Không chép chi tiết schema sang roadmap; roadmap chỉ link.

## Verification

- `cd server && uv run pytest -q` và `uv run pytest -m docker tests/test_twin_docker.py -v` (stack đã `labctl up`).
- `cd web && npm test && npm run typecheck`.
- Đối chiếu từng tiêu chí 1–8 của báo cáo brainstorm và hai tiêu chí bổ sung trong `plan.md`; ghi đạt hay chưa vào `notes/e2e-results.md`.
- Link trong `docs/labctl.md` và `docs/roadmap.md` trỏ đúng file.
