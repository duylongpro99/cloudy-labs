---
phase: 2
title: "Op và validate cho SG, Key Pair, Instance"
status: completed
priority: P1
effort: "7h"
dependencies: []
---

# Phase 2: Op và validate cho SG, Key Pair, Instance

## Goal

Danh mục op có thêm 5 thao tác EC2, mỗi thao tác là một lệnh `aws`, và validate giải thích mọi lỗi người học có thể gặp trước khi chạy (F4.3).

## Files to Create / Modify

- Modify: `server/src/cloudy_labs/builder/ops.py`
- Modify: `server/src/cloudy_labs/builder/validate.py`
- Create: `server/src/cloudy_labs/builder/ec2_choices.py` (AMI và instance type cho phép theo kiến trúc máy)
- Modify: `server/tests/test_builder_ops.py`, `server/tests/test_builder_validate.py`
- Modify: `docs/emulator-differences.md` (chỉ khi bước thử Floci thấy khác biệt mới)

## Tasks & Steps

- [x] **Thử trên Floci trước** (Docker, emulator đang chạy): `modify-instance-attribute --groups`, `create-key-pair --tag-specifications`, `create-security-group --tag-specifications`, `authorize-security-group-ingress --ip-permissions`. Ghi kết quả vào `notes/floci-ec2-ops.md`. Op nào Floci không hỗ trợ thì dừng phần đó và báo người dùng trước khi đổi phạm vi.
- [x] `ec2_choices.py`: `choices(machine=platform.machine())` trả `{"images": [...], "instanceTypes": [...]}`; arm64/aarch64 → `ami-amazonlinux2023-arm64`, `t4g.micro`, `t4g.small`; x86_64/amd64 → `ami-amazonlinux2023`, `t3.micro`, `t3.small`. Thuần, có test cho cả hai kiến trúc.
- [x] Op mới trong `ops.py`:
  - `create-security-group` (create, containers `vpc`): params `name`, `vpcId`, `description`; argv `ec2 create-security-group --group-name <name> --description <desc> --vpc-id <vpc>` + tag `security-group`; `result_id="GroupId"`.
  - `authorize-security-group-ingress` (attribute, targets `security-group`): params `groupId`, `protocol`, `port`, `cidr`; argv dùng `--ip-permissions` dạng JSON (`json.dumps`) để có `Description` rỗng và tránh shorthand; `expectation` trả `{node, prop: "ingress", includes: {protocol, from, to, source}}` khớp cách collector chuẩn hoá rule.
  - `create-key-pair` (create, containers `region`): params `name`; argv `ec2 create-key-pair --key-name <name>` + tag `key-pair`; `result_id="KeyPairId"`. Không dùng `--query` để stdout giữ `KeyMaterial` nguyên văn.
  - `run-instances` (create, containers `subnet-public`, `subnet-private`): params `name`, `subnetId`, `imageId`, `instanceType`, `securityGroupId`, `keyName`, `userData`; argv `ec2 run-instances --image-id --instance-type --subnet-id --security-group-ids --count 1`, thêm `--key-name` khi có, `--user-data` khi khác rỗng, tag `instance`; `result_id="Instances.0.InstanceId"`.
  - `modify-instance-attribute` (connect, source `security-group`, targets `instance`): params `instanceId`, `groupId`; build cần danh sách SG hiện có nên op nhận thêm `currentGroups` do server điền từ graph (không lấy từ trình duyệt); argv `ec2 modify-instance-attribute --instance-id <id> --groups <cũ...> <mới>`; expect cạnh `attached:<groupId>-><instanceId>`.
- [x] `result_id` đi được qua chỉ số mảng (`Instances.0.InstanceId`). Test với stdout mẫu của spike.
- [x] `palette_kind` không cần đổi: SG ingress và gắn SG đều thuộc `security-group`.
- [x] Validate (giọng dạy học, như M3):
  - `create-security-group`: VPC tồn tại; tên 1–255 ký tự hợp lệ, không bắt đầu bằng `sg-`, không trùng tên SG khác trong VPC; description không rỗng, ASCII.
  - `authorize-security-group-ingress`: SG tồn tại; protocol thuộc `tcp`, `udp`, `icmp`, `-1`; port là số nguyên 0–65535 (bỏ qua khi `-1`/`icmp`); CIDR hợp lệ (`_cidr(..., limits=False)`); **chặn** `0.0.0.0/0` khi rule phủ cổng 22 (tcp 22, hoặc protocol `-1`) và giải thích vì sao SSH mở cho cả Internet nguy hiểm, gợi ý dùng IP của mình `/32`; rule trùng rule đã có thì báo.
  - `create-key-pair`: tên hợp lệ, không trùng key pair có sẵn.
  - `run-instances`: subnet tồn tại; SG tồn tại và cùng VPC với subnet; key pair (khi có) tồn tại; `imageId` và `instanceType` thuộc `ec2_choices()`; `userData` ≤ 16 KB. Subnet riêng tư không bị chặn (lab sau có thể cần instance private).
  - `modify-instance-attribute`: instance tồn tại và chưa `terminated`; SG cùng VPC với instance; SG chưa gắn (cạnh `attached` đã có).
- [x] `validate` nhận thêm `choices` (danh sách AMI/type) như đã nhận `azs`; cập nhật chữ ký và chỗ gọi trong test.

## Verification

- `cd server && uv run pytest tests/test_builder_ops.py tests/test_builder_validate.py`
- Test ops: argv của từng op mới khớp từng phần tử; `display(argv)` của `run-instances` với UserData nhiều dòng, khi chạy lại qua `shlex.split`, cho đúng argv.
- Test validate: mỗi luật trong danh sách trên có một test đúng và một test sai, thông điệp gắn đúng `field`.

## Ghi chú

- `currentGroups` do server điền từ cạnh `attached` của graph ngay khi dựng argv, nên lệnh hiện ra luôn chứa danh sách SG mới nhất; nếu graph đổi giữa preview và run thì `/api/run` dựng lại argv và validate lại như M3.
