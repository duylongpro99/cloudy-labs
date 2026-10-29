---
phase: 3
title: "lab-server và labctl serve"
status: completed
priority: P1
effort: "4h"
dependencies: [1, 2]
---

# Phase 3: lab-server và `labctl serve`

## Goal

`labctl serve` chạy lab-server foreground trên `127.0.0.1:8730`; mỗi lệnh ghi qua api-tap làm graph mới tới mọi trình duyệt qua WebSocket trong ≤ 2 giây (F2.2, F2.3, NFR3, NFR7).

## Files to Create / Modify

- Create: `server/src/cloudy_labs/server/__init__.py`, `server/app.py` (FastAPI), `server/hub.py` (GraphHub), `server/tap_listener.py`
- Create: `server/tests/test_hub.py`, `server/tests/test_app.py`, `server/tests/test_latency_docker.py`
- Modify: `server/pyproject.toml` (thêm `fastapi`, `uvicorn`, `websockets`, `httpx`; `httpx` vừa đọc SSE vừa phục vụ `TestClient`), `server/uv.lock`
- Modify: `server/src/cloudy_labs/cli.py` (lệnh `serve`), `server/src/cloudy_labs/config.py` (`SERVER_PORT = 8730`)
- Modify: `plans/261027-1353-m0-spike-emulator-and-render-validation/notes/license-summary.md` hoặc tài liệu giấy phép hiện hành (thêm các gói mới)

## Tasks & Steps

1. **GraphHub** (`hub.py`), chạy trong event loop asyncio:
   - `refresh(reason)`: gọi `collect()` trong thread (`asyncio.to_thread`), tính hash JSON của graph bỏ `version/takenAt`; chỉ khi hash đổi mới tăng `version` và phát `{"type": "graph", "graph": …}`.
   - Debounce: sự kiện ghi đặt lịch refresh sau 150 ms; nhiều sự kiện trong cửa sổ đó gộp thành một lần. Đang refresh mà có sự kiện mới thì chạy thêm đúng một lần sau đó.
   - Poll an toàn mỗi 5 giây (F2.2). Floci down thì poll mỗi 1 giây để bắt lúc trở lại sau `labctl reset`.
   - Danh sách client WebSocket; gửi lỗi thì bỏ client đó.
2. **TapListener** (`tap_listener.py`): đọc SSE `http://127.0.0.1:4568/events` bằng `httpx` stream. Mỗi sự kiện chuyển thành `{"type": "api-event", "service", "action", "seq"}` cho client để làm hiệu ứng F3.6; M2 không suy id tài nguyên từ body phản hồi. Nếu `write` thì gọi `hub.refresh("tap")`. Mất kết nối thì thử lại với backoff 0,5 → 5 s; trong lúc đó poll vẫn chạy.
3. **app.py:**
   - `GET /api/health`: `{floci, tap, version}`.
   - `GET /api/graph`: graph hiện tại.
   - `WS /ws`: khi kết nối gửi ngay `graph` hiện tại, sau đó nhận `graph` và `api-event`. Server không nhận lệnh nào từ client trong M2.
   - Kiểm `Origin` của WebSocket: chỉ chấp nhận `http://127.0.0.1:5174`, `http://localhost:5174` và không có Origin (công cụ CLI). Tránh trang web lạ đọc trạng thái lab qua `ws://127.0.0.1:8730`.
   - Lifespan: khởi động hub + listener, dừng gọn khi Ctrl-C.
4. **`labctl serve`:** chạy uvicorn trên `127.0.0.1:8730`, không có tuỳ chọn bind host khác (NFR7). Trước khi chạy: emulator chưa `up` thì báo và thoát mã 1; cổng 8730 bận thì in PID chiếm cổng (`lsof -i :8730 -t`) và thoát, không đổi cổng. In URL của web (`http://127.0.0.1:5174`) và nhắc chạy `pnpm dev` trong `web/`.
5. **Giấy phép:** kiểm giấy phép của `fastapi`, `starlette`, `uvicorn`, `websockets`, `httpx`, `anyio`, `h11` và image `python:3.12-slim`; ghi vào bảng giấy phép hiện có.
6. **Test:**
   - `test_hub.py` (không Docker): collector giả đếm số lần gọi; 10 sự kiện ghi trong 100 ms gây đúng 1–2 lần collect; graph không đổi thì không phát; collector lỗi thì phát `emulator-down` một lần rồi trở lại `ok`.
   - `test_app.py`: `TestClient` mở `/ws`, nhận graph đầu tiên; hub phát graph mới thì client nhận; Origin lạ bị từ chối.
   - `test_latency_docker.py` (`-m docker`): `up` + chạy app trong thread, mở WS; 20 lần tạo một subnet qua 4566 rồi đo từ lúc boto3 trả về tới lúc WS nhận graph chứa subnet đó; p95 ≤ 2 s. In p50/p95 để ghi vào báo cáo Phase 6.

## Verification

- `cd server && uv run pytest tests/test_hub.py tests/test_app.py`
- `cd server && uv run pytest -m docker tests/test_latency_docker.py`
- Thủ công: `labctl up && labctl serve`, ở terminal khác `websocat ws://127.0.0.1:8730/ws` (hoặc script Python nhỏ), `aws ec2 create-vpc …` thấy graph mới; `labctl reset` thấy `emulator-down` rồi graph rỗng.
- `lsof -i :8730` chỉ thấy `127.0.0.1`.

## Risk & Rollback

Nếu collect tuần tự quá chậm để đạt p95 ≤ 2 s, gọi các `describe_*` song song bằng `ThreadPoolExecutor` (boto3 client dùng chung được giữa các thread). Rollback: bỏ lệnh `serve` và package `server/`; `labctl` CLI không phụ thuộc phần này.
