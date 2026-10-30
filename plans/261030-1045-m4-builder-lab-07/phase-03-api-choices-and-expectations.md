---
phase: 3
title: "API: lựa chọn EC2, expect mới, practiceExpect"
status: completed
priority: P1
effort: "4h"
dependencies: [2]
---

# Phase 3: API: lựa chọn EC2, expect mới, practiceExpect

## Goal

lab-server phục vụ các op EC2: `/api/lab` cho biết AMI, instance type và UserData mặc định; `/api/preview` trả thêm `practiceExpect`; `/api/run` trả `expect` dạng `includes` cho rule SG. Runner không đổi.

## Files to Create / Modify

- Modify: `server/src/cloudy_labs/server/app.py`
- Modify: `server/src/cloudy_labs/builder/ops.py` (`practice_expectation`, điền `currentGroups` từ graph)
- Modify: `server/tests/test_app.py`, `server/tests/test_builder_ops.py`
- Modify: `server/tests/test_builder_e2e_docker.py` (một ca `run-instances` thật)

## Tasks & Steps

- [x] `/api/lab` thêm `images`, `instanceTypes` (từ `ec2_choices()`), `userData` (từ `builder.user_data`).
- [x] `checked()` truyền `choices` vào `validate`; với `modify-instance-attribute`, điền `currentGroups` từ `hub.graph` trước khi dựng argv (trình duyệt gửi field này thì 422 như mọi field lạ).
- [x] `practice_expectation(op, params)` trong `ops.py`: op create → `{kind, label: params.name}` (với subnet thì `kind` là `subnet`, web khớp cả hai kind subnet); op connect/attribute → chính `expectation(...)` không cần stdout. `/api/preview` trả `practiceExpect`.
- [x] `/api/run` không đổi luồng; `expectation` mới cho `authorize-security-group-ingress` và `modify-instance-attribute` đi qua như các op khác.
- [x] Đảm bảo không log stdout của runner ở bất kỳ đâu (key pair). Thêm test: logger của app không nhận `KeyMaterial` khi chạy `create-key-pair` bằng runner giả.

## Verification

- `cd server && uv run pytest tests/test_app.py tests/test_builder_ops.py`
- Test app: `/api/lab` có `images`, `instanceTypes`, `userData`; preview `create-security-group` có `practiceExpect = {kind: "security-group", label: ...}`; preview `modify-instance-attribute` hiện `--groups` gồm SG cũ và mới; gửi `currentGroups` từ trình duyệt → 422.
- `uv run pytest -m docker -k run_instances`: `/api/run` với `run-instances` trên Floci trả exit 0 và graph có instance mới trong vòng 5 giây.
