---
phase: 1
title: "Lab fixture Lab 7 và schema builder"
status: completed
priority: P1
effort: "4h"
dependencies: []
---

# Phase 1: Lab fixture Lab 7 và schema builder

## Goal

Có `fixture-lab-07` chạy được bằng `labctl start`: bước `setup` dựng sẵn mạng Lab 6, các check chấm Lab 7, và schema lab cho phép palette EC2 cùng UserData mặc định.

## Files to Create / Modify

- Modify: `server/src/cloudy_labs/labs/schema.py` (`BuilderKind` thêm `security-group`, `key-pair`, `instance`; `Builder.user_data: str = ""` với alias YAML `userData`, tối đa 16 KB)
- Create: `server/tests/fixtures/labs/fixture-lab-07/lab.yaml`
- Create: `server/tests/fixtures/labs/fixture-lab-07/checks.py` (gồm hàm `setup_network` và các check)
- Modify: `server/tests/test_schema.py`, `server/tests/test_loader.py`
- Create: `server/tests/test_fixture_lab_07.py` (check chạy trên client giả, không Docker)

## Tasks & Steps

- [x] `schema.py`: mở rộng `BuilderKind`; thêm `user_data` vào `Builder` (chuỗi, ≤ 16 384 byte UTF-8, mặc định rỗng). Test: YAML có `userData` quá dài bị từ chối; kind lạ bị từ chối.
- [x] `lab.yaml` của `fixture-lab-07`: `cidrs: [10.67.0.0/16]`, `setup: [checks:setup_network]`, `builder.palette: [security-group, key-pair, instance]`, `builder.tags: {lab: fixture-lab-07}`, `builder.userData` là script của spike (lấy IP private từ IMDS rồi `python3 -m http.server 80 --bind $IP`).
- [x] Tasks: `security-group` (tạo SG `web` trong VPC, mở 80 từ mọi nơi, 22 chỉ từ một /32), `key-pair` (tạo key pair), `instance` (chạy instance trong subnet công khai với SG và key pair, UserData dựng web server), `extra-sg` (tạo SG thứ hai `admin` và gắn vào instance).
- [x] `setup_network(ctx)`: bằng boto3 qua `ctx.client("ec2")`, tạo VPC 10.67.0.0/16 (tag `lab=fixture-lab-07`, bật DNS hostnames), một subnet công khai 10.67.1.0/24 với `MapPublicIpOnLaunch`, IGW gắn vào VPC, route table `0.0.0.0/0 → IGW` gắn vào subnet. Đặt Name tag để cảnh dễ đọc.
- [x] Check (theo lab tag, tìm VPC trước như `fixture-lab-06/checks.py`):
  - `sg-web-80`: có SG trong VPC mở `tcp 80` từ `0.0.0.0/0`.
  - `ssh-not-open-to-world`: không SG nào trong VPC mở cổng 22 (hoặc dải chứa 22, hoặc protocol `-1`) cho `0.0.0.0/0`.
  - `key-pair-exists`: có ít nhất một key pair.
  - `instance-running`: instance `running` trong subnet công khai, có key pair và SG mở 80.
  - `web-server-answers`: HTTP GET qua cổng host của cổng 80 (Floci publish qua socat; đọc như `graph/host_ports.py`) trả 200; thông điệp trượt nói rõ UserData có thể chạy thêm vài phút.
  - `instance-has-two-sgs`: instance có ít nhất hai SG.
- [x] Test check bằng client giả trả các response mẫu (đúng, thiếu, cổng 22 mở cho mọi nơi, protocol `-1`).

## Verification

- `cd server && uv run pytest tests/test_schema.py tests/test_loader.py tests/test_fixture_lab_07.py`
- `labctl start fixture-lab-07` trên Docker: cảnh hiện VPC, subnet công khai, IGW, route table; `labctl check fixture-lab-07` báo trượt mọi check Lab 7 với thông điệp có hướng dẫn.

## Ghi chú

- `web-server-answers` cần cổng host. Nếu đọc cổng từ Docker trong checker quá rắc rối, dùng `curl` từ trong container instance qua `docker exec` là phương án dự phòng; chọn cách nào thì ghi lại ở đây khi làm.
