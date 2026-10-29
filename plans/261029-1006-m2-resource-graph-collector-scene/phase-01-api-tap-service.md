---
phase: 1
title: "api-tap trong compose, Floci lùi cổng"
status: completed
priority: P1
effort: "5h"
dependencies: []
---

# Phase 1: api-tap trong compose, Floci lùi cổng

## Goal

Mọi lệnh AWS CLI của người học đi qua api-tap ở `127.0.0.1:4566`, được chuyển tiếp nguyên vẹn tới Floci, và mỗi lệnh ghi phát một sự kiện trên `127.0.0.1:4568/events` (F2.2).

## Files to Create / Modify

- Create: `server/src/cloudy_labs/tap/__init__.py`, `server/src/cloudy_labs/tap/api_tap.py` (chỉ stdlib, để chạy trong image Python trần)
- Create: `server/tests/test_api_tap.py`
- Modify: `server/src/cloudy_labs/emulator/compose.yaml` (service `api-tap`, đổi cổng host của Floci)
- Modify: `server/src/cloudy_labs/config.py` (`API_PORT = 4566`, `FLOCI_PORT = 4567`, `TAP_EVENTS_PORT = 4568`)
- Modify: `server/src/cloudy_labs/providers/aws.py` (endpoint của người học và checker là `API_PORT`; thêm `direct_endpoint` cho collector), `server/src/cloudy_labs/emulator/stack.py` (`reachable`, `endpoints`, kiểm cổng bận khi `up`), `server/src/cloudy_labs/emulator/orphans.py` (giá trị owner nếu đổi)
- Modify: `server/tests/test_stack.py`, `server/tests/test_providers.py`, `server/tests/test_lifecycle_docker.py`

## Tasks & Steps

1. **Kiểm rủi ro trước.** Trên compose tạm với Floci publish `127.0.0.1:4567:4566`: tạo VPC, subnet, instance có UserData (bước 1–36 của `spikes/m0-emulators/lab-06-07.sh` với `AWS_ENDPOINT_URL=http://127.0.0.1:4567`), rồi `docker inspect` container EC2 và network VPC. Ghi vào `notes/floci-port-move.md`: giá trị `io.floci.owner`, instance có lên `running` và có IMDS không. Nếu owner đổi theo cổng host thì cập nhật hằng số trong `orphans.py`; nếu instance hỏng thì dùng phương án dự phòng ở mục Rủi ro của plan.
2. **`api_tap.py`** dựa trên `spikes/m0-emulators/api-tap.py`:
   - `ThreadingHTTPServer` nghe `0.0.0.0:4566` trong container (compose chỉ publish ra `127.0.0.1`), upstream lấy từ biến `TAP_UPSTREAM=http://floci:4566`.
   - Chuyển tiếp method, path, query, mọi header trừ hop-by-hop, và body, không đổi `Host`. Hỗ trợ `Transfer-Encoding: chunked` từ phía request (S3 upload của CLI) bằng cách đọc chunk rồi gửi `Content-Length`; nếu vậy làm sai chữ ký thì chuyển tiếp nguyên dạng chunk.
   - `describe(headers, body, method, path)` trả `(service, action)`: scope SigV4, `X-Amz-Target`, form `Action`, và với S3 REST suy từ method + path (spike mục 2.5), ví dụ `PUT /bucket` → `CreateBucket`, `PUT /bucket/key` → `PutObject`.
   - `is_write(action, method)`: tiền tố `Create Delete Modify Put Attach Detach Associate Disassociate Allocate Release Run Terminate Start Stop Reboot Authorize Revoke Replace Update Import Enable Disable Assign Unassign Tag Untag`, hoặc method S3 khác `GET/HEAD`.
   - Kênh sự kiện: server thứ hai trên `0.0.0.0:4568`, `GET /events` là SSE. Mỗi sự kiện: `{"seq", "ts", "service", "action", "status", "write", "ms"}`. Sự kiện phát **sau** khi upstream trả lời, chỉ khi `status < 400`. Hàng đợi mỗi client có giới hạn (256); client chậm bị cắt kết nối thay vì làm chậm proxy. `GET /health` trả 200 khi upstream health OK.
   - Mỗi request ghi một dòng log ra stdout như spike.
3. **compose:** service `api-tap` dùng `python:3.12-slim` ghim digest (tra Docker Hub lúc làm, ghi ngày kiểm), mount `../tap/api_tap.py` read-only, `command: python -u /app/api_tap.py`, ports `127.0.0.1:4566:4566` và `127.0.0.1:4568:4568`, `depends_on: floci (healthy)`, healthcheck gọi `/health` bằng `python -c`. Floci đổi thành `127.0.0.1:4567:4566`.
4. **config và provider:** `AwsProvider("floci").endpoint` = `http://127.0.0.1:4566` (qua tap), `direct_endpoint` = `http://127.0.0.1:4567`. `health()` và `reset()` dùng đường trực tiếp. `labctl status` báo cả trạng thái api-tap. `up` báo lỗi rõ nếu 4566, 4567 hoặc 4568 bị tiến trình khác chiếm (theo quy tắc không đổi sang cổng khác).
5. **Test đơn vị** (`test_api_tap.py`, không Docker): chạy tap trong thread trỏ tới một upstream giả bằng `http.server`; kiểm header và body tới upstream giống hệt (gồm `Authorization`, `Host`); bảng `describe` cho EC2 query, JSON target, S3 REST; `is_write`; client SSE nhận đúng sự kiện ghi và không nhận lệnh đọc hay lệnh lỗi; client chậm bị cắt mà request vẫn qua.
6. **Test docker:** mở rộng `test_lifecycle_docker.py`: `up`, gọi `ec2 create-vpc` bằng boto3 qua 4566, nhận sự kiện `CreateVpc` trên SSE trong 1 giây, `describe-vpcs` qua 4566 và qua 4567 trả cùng kết quả, `down` không để lại mồ côi.

## Verification

- `cd server && uv run pytest tests/test_api_tap.py tests/test_stack.py tests/test_providers.py`
- `cd server && uv run pytest -m docker`
- `docker compose -p cloudy-labs ps` cho thấy 4566, 4567, 4568, 5050 đều bind `127.0.0.1`.
- Chạy `lab-06-07.sh` sau `eval "$(labctl env)"`: 36 bước không lỗi, output giống bản chạy trực tiếp trong `spikes/m0-emulators/out/floci/` (bỏ qua id và `ReservationId`).

## Risk & Rollback

Rủi ro chính là bước 1. Rollback: trả `compose.yaml` về một service Floci ở 4566 và `config.py` về giá trị cũ; mọi thứ khác của M1 không phụ thuộc api-tap.
