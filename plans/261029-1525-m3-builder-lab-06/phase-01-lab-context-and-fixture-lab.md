---
phase: 1
title: "Ngữ cảnh lab và lab fixture Lab 6"
status: completed
priority: P1
effort: "4h"
dependencies: []
---

# Phase 1: Ngữ cảnh lab và lab fixture Lab 6

## Goal

Lab tự khai báo palette builder (F4.1) và tag mặc định trong YAML; có một lab fixture mô phỏng Lab 6 với checker thật; web đọc được lab đang mở qua `GET /api/lab`.

## Files to Create / Modify

- Modify: `server/src/cloudy_labs/labs/schema.py` (thêm `Builder`: `palette: list[str]`, `tags: dict[str, str]`)
- Create: `server/tests/fixtures/labs/fixture-lab-06/lab.yaml`, `server/tests/fixtures/labs/fixture-lab-06/checks.py`
- Modify: `server/src/cloudy_labs/server/app.py` (route `GET /api/lab`), `server/src/cloudy_labs/cli.py` (truyền `Engine` vào `create_app`)
- Modify: `server/tests/test_schema.py`, `server/tests/test_app.py`, `server/tests/test_loader.py`
- Modify: `web/src/graph/types.ts` (type `LabInfo`)

## Tasks & Steps

- [x] `Builder` trong `schema.py`: `palette` là tập con của các kind builder hỗ trợ (`vpc`, `subnet`, `igw`, `elastic-ip`, `nat`, `route-table`); kind lạ là lỗi load. `tags` là tag gắn thêm vào mọi tài nguyên builder tạo. Lab không có `builder` thì palette rỗng và web báo "lab này chưa hỗ trợ builder".
- [x] `fixture-lab-06/lab.yaml`: ghi rõ là fixture kiểm thử, không phải nội dung lab. VPC `10.66.0.0/16` có `enableDnsHostnames`; 2 subnet public và 2 private trên 2 AZ, public bật `MapPublicIpOnLaunch`; IGW đã attach; NAT có EIP trong một subnet public; route table public có `0.0.0.0/0 → IGW` và gắn 2 subnet public; route table private có `0.0.0.0/0 → NAT` và gắn 2 subnet private. `cidrs: [10.66.0.0/16]` để preflight cảnh báo trùng mạng Docker. `builder.tags: {lab: fixture-lab-06}`.
- [x] `checks.py`: một check cho mỗi điều trên, lọc theo tag `lab=fixture-lab-06`, message nói rõ thiếu gì. Dùng `CheckContext.client("ec2")` như `fixture-vpc`.
- [x] `GET /api/lab`: trả `{id, title, tasks, palette, tags, attempt}` của `progress.current_attempt()`; không có attempt thì `{id: null}`. Lab đọc lại từ đĩa mỗi lần gọi (engine cache theo id, nên đổi lab giữa chừng vẫn đúng). `create_app` nhận `engine` tuỳ chọn để test truyền engine giả.
- [x] Cập nhật `LabInfo` trong `types.ts`, kèm hàm parse tối thiểu như `parseGraph`.

## Verification

- `cd server && uv run pytest tests/test_schema.py tests/test_loader.py tests/test_app.py`
- Test checker trên `server/tests/fixtures/graph/floci-describe/` không dùng được vì thiếu tag; checker được kiểm đầu-cuối ở Phase 6. Ở đây chỉ kiểm lab load được và mọi `fn` resolve được.

## Ghi chú triển khai

- `create_app` nhận `lab: CurrentLab` (callable trả lab đang làm) thay vì `engine`, để test truyền lab giả mà không dựng engine.
