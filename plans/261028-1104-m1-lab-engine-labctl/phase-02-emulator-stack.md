---
phase: 2
title: "Stack emulator: compose, up/down, dọn mồ côi"
status: completed
priority: P1
effort: "4h"
dependencies: [1]
---

# Phase 2: Stack emulator: compose, up/down, dọn mồ côi

## Goal

`labctl up` dựng Floci và moto bằng một lệnh, không trùng lặp, chỉ bind `127.0.0.1`; `labctl down` tắt stack và dọn sạch tài nguyên mồ côi của Floci.

## Files to Create / Modify

- Create: `server/src/cloudy_labs/emulator/__init__.py`, `compose.yaml`, `docker.py`, `stack.py`, `orphans.py`, `preflight.py`
- Create: `server/tests/test_preflight.py`, `server/tests/test_orphans.py`
- Modify: `server/src/cloudy_labs/cli.py` (lệnh `up`, `down`), `server/pyproject.toml` (đóng gói `compose.yaml`)

## Tasks & Steps

1. `compose.yaml`, project name `cloudy-labs`:
   - `floci`: `floci/floci:2.3.0@sha256:e0b292df…ea8a9` (digest đầy đủ từ báo cáo M0 mục 7), `user: root`, `127.0.0.1:4566:4566`, `FLOCI_STORAGE_MODE=memory`, `FLOCI_SERVICES_UI_ENABLED=false`, mount `/var/run/docker.sock`, healthcheck.
   - `moto`: `motoserver/moto:5.2.4`, ghim digest lấy bằng `docker buildx imagetools inspect` lúc làm (multi-arch index digest), `127.0.0.1:5050:5000`, `INITIAL_NO_AUTH_ACTION_COUNT=3`, healthcheck.
   - Ghi chú trong file: ngày kiểm tag và lý do `user: root`.
2. `docker.py`: hàm mỏng gọi `docker` qua `subprocess.run` (không thêm Docker SDK), trả về stdout, ném `DockerError` kèm stderr. Kiểm `docker info` trước để báo "Docker chưa chạy" rõ ràng.
3. Xác minh giá trị label: chạy Floci, tạo một VPC + một instance nhỏ, `docker inspect` container/network/volume để ghi lại khoá và giá trị `io.floci.owner`. Ghi kết quả vào `notes/floci-labels.md` của plan này. Bộ lọc dùng đúng giá trị đó.
4. `orphans.py`: `find_orphans()` trả về danh sách container, network, volume có `label=io.floci.owner=<giá trị của stack>`, trừ chính container `floci` của compose; `remove_orphans()` xoá container (`rm -f`), rồi network, rồi volume, theo thứ tự đó. Hàm phân tích output tách riêng để test đơn vị trên chuỗi mẫu.
5. `preflight.py`:
   - `port_owner(port)`: kiểm cổng 4566/5050 đã bị chiếm chưa (thử bind `127.0.0.1`). Nếu bị chiếm bởi chính stack `cloudy-labs` thì coi là đang chạy; nếu bởi thứ khác thì báo lỗi kèm gợi ý `lsof -i :PORT`, không đổi sang cổng khác.
   - `docker_networks()`: đọc subnet IPv4 của mọi mạng Docker (`docker network inspect` trên `docker network ls -q`), bỏ qua mạng `floci-aws-vpc-*` của chính stack.
   - `cidr_overlaps(lab_cidrs, networks)`: hàm thuần trả về các cặp trùng. Test đơn vị với các trường hợp chứa nhau, trùng một phần, không trùng.
6. `stack.py`:
   - `up()`: kiểm Docker → kiểm cổng → nếu stack đã chạy và healthy thì báo và dừng (không tạo trùng) → dọn mồ côi còn lại từ lần trước → `docker compose -p cloudy-labs -f <compose> up -d --wait` → pull sẵn `alpine/socat:latest` nếu chưa có image (in tiến trình, lý do theo spike) → in endpoint.
   - `down()`: `docker compose … down -v` → `remove_orphans()` → in số tài nguyên đã dọn.
   - `is_running()` dùng `docker compose ps --format json`.
7. CLI `up` và `down` in kết quả ngắn, mã thoát khác 0 khi lỗi.

## Verification

- `cd server && uv run pytest` qua (test đơn vị của preflight và orphans).
- Thủ công: `uv run labctl up` hai lần liên tiếp → lần hai báo đang chạy; `docker compose -p cloudy-labs ps` cho thấy `127.0.0.1:4566` và `127.0.0.1:5050`; `uv run labctl down` → `docker ps -a --filter label=io.floci.owner`, `docker network ls --filter label=…`, `docker volume ls --filter label=…` đều trống.

## Risk

- Floci đặt label khác dự đoán: bước 3 kiểm trước, không viết bộ lọc theo phỏng đoán.
- Cổng 5000 trên macOS bị AirPlay chiếm; moto chỉ public ra 5050 nên không đụng.
