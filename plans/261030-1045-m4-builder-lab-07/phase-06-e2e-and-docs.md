---
phase: 6
title: "Kiểm thử đầu-cuối và tài liệu"
status: completed
priority: P1
effort: "5h"
dependencies: [1, 2, 3, 4, 5]
---

# Phase 6: Kiểm thử đầu-cuối và tài liệu

## Goal

Chứng minh điều kiện qua mốc M4 bằng `fixture-lab-07` trên Docker, ở cả chế độ thường và chế độ luyện tập, rồi cập nhật tài liệu.

## Files to Create / Modify

- Create: `web/scripts/e2e-builder-lab-07.mjs` (theo mẫu `e2e-builder-lab-06.mjs`)
- Modify: `server/tests/test_builder_e2e_docker.py` (luồng Lab 7 qua API, không trình duyệt)
- Create: `plans/261030-1045-m4-builder-lab-07/notes/e2e-results.md`
- Modify: `docs/labctl.md` (mục Builder kéo-thả: op EC2, rule SG, gắn SG, .pem, chế độ luyện tập; bảng endpoint thêm trường mới)
- Modify: `docs/roadmap.md` (trạng thái M4, link plan và e2e)
- Modify: `docs/emulator-differences.md` (khác biệt mới tìm thấy, gồm câu hỏi còn mở từ M3)

## Tasks & Steps

- [x] E2E chế độ thường trong trình duyệt: `labctl start fixture-lab-07` → kéo SG `web` vào VPC → thêm rule 80 từ `0.0.0.0/0` → thử rule 22 từ `0.0.0.0/0` và khẳng định Run bị khoá kèm thông điệp → thêm rule 22 từ `203.0.113.10/32` → tạo key pair, bấm Tải .pem → kéo Instance vào subnet công khai với UserData mặc định → tạo SG `admin`, kéo cạnh SG → instance → `labctl check fixture-lab-07` đạt hết (chờ `web-server-answers` tới 60 giây). Ghi số lần `/api/run` bằng đúng số lần bấm Run, và thời gian Run → cảnh.
- [x] E2E chế độ luyện tập: reset, bật Luyện tập, làm cùng các bước nhưng lấy lệnh từ nút Chép rồi chạy bằng `bash -c` trong script (giả lập người học gõ ở terminal). Khẳng định không có `/api/run` nào, panel chuyển `done` mỗi bước, và `labctl check` đạt.
- [x] Kiểm câu hỏi còn mở từ M3: Floci có từ chối subnet CIDR chồng lấn không (`create-subnet` trùng block qua `aws` thẳng). Ghi kết quả vào `docs/emulator-differences.md`.
- [x] Ghi `notes/e2e-results.md`: các bước, số đo, lỗi gặp và cách sửa.
- [x] Cập nhật tài liệu như danh sách file ở trên; roadmap ghi M4 "Xong với lab fixture, chờ kiểm lại bằng Lab 7 thật".
- [x] Toàn bộ: `uv run pytest`, `uv run pytest -m docker`, `ruff check`, `pnpm test`, `pnpm typecheck`, `node scripts/check-builder.mjs`.

## Verification

- `cd server && uv run pytest && uv run pytest -m docker`
- `cd web && pnpm test && pnpm typecheck && node scripts/e2e-builder-lab-07.mjs`
- `ak plan validate` (nếu có) và kiểm mọi link trong `docs/` vừa sửa.
