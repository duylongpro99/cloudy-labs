---
phase: 11
title: "Nghiệm thu với lab-001 RDS và cập nhật tài liệu"
status: completed
priority: P1
effort: "8h"
dependencies: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
---

# Phase 11: nghiệm thu với lab-001 RDS và cập nhật tài liệu

## Goal

Chứng minh toàn bộ chuỗi trên một lab thật, `lab-001 (labaws RDS, Aurora or self-managed)`. Sau đó cập nhật roadmap, PRD và docs.

## Điều kiện

Người dùng dán nội dung lab (bản đã đăng nhập) vào `labs/lab-001/content/lab.md` qua `labctl content import`. File này không được commit.

## Tasks & Steps

1. Chạy `labctl coverage lab-001` **trước khi** viết YAML.
   - **[Red team]** Kỳ vọng là kết luận nháp `ready-with-caveats`, kèm danh sách đề cập chưa nhận diện (heading và số dòng).
   - Caveat lấy từ registry: `MultiAZ` `flag-only`; Aurora chạy trên engine thường.
   - Xem danh sách đó một lượt, rồi chạy `coverage <lab> --accept` để có kết luận cuối.
   - Nếu kết luận khác `ready-with-caveats`, đó là lỗi của Phase 6–10: sửa, rồi ghi lại.
2. **[Red team]** Phần self-managed DB trên EC2 cần cài package trong container instance. Phase 11 kiểm xem lệnh cài có chạy được trên Floci không:
   - được thì làm theo lab;
   - không được thì ghi caveat `self-managed-install` vào `ec2.yaml`, và task đó chỉ chấm theo cấu hình (instance, SG, cổng).
3. Soạn `lab.yaml` gồm `region: ap-southeast-2`, palette, task và `target`. Soạn `checks.py`; nếu lab có đường app → DB thì dùng `reachable`, kết quả ghi nhãn "đã phân tích". Hint đặt trong `content/hints.yaml`, không đặt trong `lab.yaml`.
4. Làm trọn lab ba lần:
   - bằng builder;
   - bằng terminal, quan sát twin;
   - bằng chat, nếu người dùng có provider. Kiểm prompt không chứa nội dung lab.

   Mỗi lần `labctl check` đều đạt, và `reset` làm sạch.
5. Chạy `check-content-leak.py`; kết quả phải là 0 trùng.
6. Chạy lại e2e Lab 6/7 fixture và bench 200 node.
7. Cập nhật tài liệu:
   - `docs/roadmap.md`: M7 đổi thành "Phủ danh mục lab", link plan này và `docs/coverage.md`.
   - `docs/product-requirements.md`: F7 viết lại theo registry và coverage; §5 đã đổi ở Phase 7; F2.4 trỏ sang `docs/coverage.md`.
   - `docs/labctl.md`: `coverage`, `content import`, `credentials moto`, region, registry. Thêm mục "Thêm một loại tài nguyên": một mục YAML, một SVG trong `web/src/scene/aws-objects/icons/`, build lại web, contract test.
   - `docs/emulator-differences.md`: tổng hợp caveat.
8. Ghi kết quả vào `notes/e2e-results.md`. **[Red team]** File này chỉ ghi lệnh, kết luận và số đo; không trích nội dung lab.

## Files to Create / Modify

- Create: `labs/lab-001/lab.yaml`, `checks.py`.
- Modify: `server/src/cloudy_labs/registry/ec2.yaml` (caveat `self-managed-install`, nếu cần).
- Modify: `docs/roadmap.md`, `docs/product-requirements.md`, `docs/labctl.md`, `docs/emulator-differences.md`.
- Create: `plans/261031-1358-lab-coverage-hardening/notes/e2e-results.md`.

## Verification

- `uv run labctl coverage lab-001` ra `ready-with-caveats` sau `--accept`.
- `uv run labctl check lab-001` đạt sau mỗi cách làm.
- `git status --ignored labs/` cho thấy `content/` bị ignore và không có trong index.
- `cd server && uv run python scripts/check-content-leak.py` thoát 0.
- Toàn bộ test server và web xanh; e2e Lab 6/7 fixture đạt; bench ≥ 50 fps.

## Kết quả

Đã xong. Lab-001 cho `ready-with-caveats` và qua `labctl check` 12/12 (cộng 1 INFO) bằng builder và bằng terminal. Reset làm sạch. Twin bind đủ 13/13 node. Lần làm bằng chat chạy ngày 2026-11-01 với provider của người dùng: 12/12 đạt, và prompt không chứa văn bản của trang lab. Bước 2 không áp dụng vì lab không cài DB trên EC2. Hint không có: trang lab không có phần hint riêng. Chi tiết ở [notes/e2e-results.md](./notes/e2e-results.md#lab-001-rds-phase-11-bước-14).
