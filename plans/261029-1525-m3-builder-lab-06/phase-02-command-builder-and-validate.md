---
phase: 2
title: "Command-builder và validate"
status: completed
priority: P1
effort: "7h"
dependencies: []
---

# Phase 2: Command-builder và validate

## Goal

Một module Python thuần, không I/O: nhận thao tác có kiểu cùng graph hiện tại, trả `argv`, chuỗi lệnh hiển thị và danh sách lỗi mang tính dạy học (F4.3, F4.4). M5 dùng lại module này (F5.3).

## Files to Create / Modify

- Create: `server/src/cloudy_labs/builder/__init__.py`, `builder/ops.py`, `builder/validate.py`
- Create: `server/tests/test_builder_ops.py`, `server/tests/test_builder_validate.py`

## Tasks & Steps

- [x] `ops.py`: `Op` gồm `name`, model pydantic cho tham số (`extra="forbid"`), `container_kinds` (kind được thả vào), và `build(params, tags) -> list[str]`. Danh mục cố định:

  | op | lệnh | thả vào / nối |
  |---|---|---|
  | `create-vpc` | `ec2 create-vpc --cidr-block` | region |
  | `create-subnet` | `ec2 create-subnet --vpc-id --cidr-block --availability-zone` | vpc, az |
  | `create-internet-gateway` | `ec2 create-internet-gateway` | region |
  | `attach-internet-gateway` | `ec2 attach-internet-gateway` | cạnh igw → vpc |
  | `allocate-address` | `ec2 allocate-address --domain vpc` | region |
  | `create-nat-gateway` | `ec2 create-nat-gateway --subnet-id --allocation-id` | subnet-public |
  | `create-route-table` | `ec2 create-route-table --vpc-id` | vpc |
  | `create-route` | `ec2 create-route --route-table-id --destination-cidr-block --gateway-id/--nat-gateway-id` | cạnh route-table → igw/nat |
  | `associate-route-table` | `ec2 associate-route-table --route-table-id --subnet-id` | cạnh route-table → subnet |
  | `modify-vpc-attribute` | `ec2 modify-vpc-attribute --enable-dns-hostnames` | thuộc tính vpc |
  | `modify-subnet-attribute` | `ec2 modify-subnet-attribute --map-public-ip-on-launch` | thuộc tính subnet |

  Lệnh tạo có `--tag-specifications` với `Name` từ form cộng `tags` của lab. <!-- Updated: Validation Session 1 - profile lab do labctl ghi -->
  `--profile lab --output json` luôn có, không có `--endpoint-url`. `display(argv)` nối bằng `shlex.join` để dán vào shell được.
- [x] `validate.py`: `validate(op, params, graph) -> list[Problem]`, `Problem` có `field` và `message`. Luật:
  - CIDR đúng cú pháp, là địa chỉ mạng (bit host bằng 0, nói rõ địa chỉ đúng là gì), prefix VPC và subnet trong /16–/28.
  - CIDR subnet nằm trong CIDR VPC; không chồng subnet khác cùng VPC (nêu tên subnet bị chồng).
  - Container đúng loại: id cha phải tồn tại trong graph và có kind thuộc `container_kinds`; với AZ thì lấy VPC cha của nó.
  - AZ thuộc danh sách AZ của region (truyền vào, Phase 3 đọc từ emulator).
  - IGW chỉ attach khi chưa attach, VPC chưa có IGW khác.
  - NAT: subnet phải là `subnet-public` (giải thích vì sao NAT cần đường ra Internet), EIP chưa gắn với gì.
  - Route: route table và đích cùng VPC; destination không trùng route đã có trên bảng đó.
  - Association: route table và subnet cùng VPC.
  Message viết cho người học: nói sai gì và vì sao, không chỉ "invalid".
- [x] Đọc props từ graph đúng như collector đặt (`cidr`, `az`, cạnh `route`, `association`, `attached`); không gọi emulator.

## Verification

- `cd server && uv run pytest tests/test_builder_ops.py tests/test_builder_validate.py`
- Test dựng graph từ `server/tests/fixtures/graph/lab-06-07.graph.json` và graph nhỏ tự tạo. Bảng test CIDR phủ đủ các trường hợp ở Success Criteria của plan.
- Test `argv` của từng op khớp đúng lệnh trong `spikes/m0-emulators/lab-06-07.sh` (thay `--endpoint-url` bằng `--profile lab`), nên lệnh builder tạo ra đã từng chạy được trên Floci.
