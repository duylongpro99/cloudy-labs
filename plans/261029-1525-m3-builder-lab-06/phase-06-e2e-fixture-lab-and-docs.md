---
phase: 6
title: "Kiểm thử đầu-cuối và tài liệu"
status: completed
priority: P1
effort: "5h"
dependencies: [5]
---

# Phase 6: Kiểm thử đầu-cuối và tài liệu

## Goal

Chứng minh điều kiện qua mốc M3 bằng lab fixture: hoàn thành `fixture-lab-06` chỉ bằng builder, `labctl check` báo đạt; ghi lại cách dùng builder.

## Files to Create / Modify

- Create: `web/scripts/e2e-builder-lab-06.mjs` (playwright-core, theo mẫu `web/scripts/check-live.mjs` của M2)
- Create: `server/tests/test_builder_e2e_docker.py` (đánh dấu `docker`: dựng stack, `labctl serve`, chạy script web, rồi `labctl check`)
- Create: `plans/261029-1525-m3-builder-lab-06/notes/e2e-results.md`
- Modify: `docs/labctl.md` (builder, `/api/preview`, `/api/run`, yêu cầu `aws` CLI, profile `lab` mà `labctl up` ghi vào config AWS), `README.md` (cách mở builder), `docs/roadmap.md` (trạng thái M3, link plan), `docs/emulator-differences.md` nếu gặp khác biệt mới

## Tasks & Steps

- [x] Script e2e làm đủ 20 thao tác Lab 6 qua giao diện (21 bước đầu của `lab-06-07.sh` trừ bước `wait`; trước khi thêm route tới NAT thì chờ graph báo NAT `available`): kéo-thả, nối cạnh, nút thuộc tính, Run; sau mỗi Run chờ graph có tài nguyên mới rồi mới làm bước kế. Ghi thời gian từ Run tới cảnh cập nhật cho từng bước.
- [x] Kiểm ngay trong script: trước khi bấm Run không có request `/api/run`; lệnh trên panel trùng `argv` mà runner nhận (đọc log server). Chạy lại một lệnh copy từ panel trong shell không có biến `AWS_*` để chắc profile `lab` đủ dùng.
- [x] Chạy `labctl check fixture-lab-06`: mọi check đạt. Thêm một lần chạy cố tình sai (subnet CIDR ngoài VPC) để chắc validate chặn trước khi gửi lệnh.
- [x] Ghi kết quả vào `notes/e2e-results.md`: số bước, độ trễ p95, lỗi gặp phải.
- [x] Cập nhật tài liệu. Roadmap ghi M3 "xong với lab fixture, chờ kiểm lại bằng Lab 6 thật", giống cách M1 đang ghi.

## Verification

- `cd server && uv run pytest -m docker tests/test_builder_e2e_docker.py`
- `cd server && uv run pytest`; `cd web && pnpm test && pnpm typecheck`
- `ak plan validate plans/261029-1525-m3-builder-lab-06`

## Ghi chú triển khai

- Lệnh trên panel được so với `command` trong response của `/api/run` (server dựng từ đúng argv nó chạy) thay vì đọc log server.
- Script làm route public và association trước NAT Gateway: NAT phải nằm trong subnet đã là public, nên thứ tự khác `lab-06-07.sh` ở chỗ này.
- Kết quả: [notes/e2e-results.md](./notes/e2e-results.md).
