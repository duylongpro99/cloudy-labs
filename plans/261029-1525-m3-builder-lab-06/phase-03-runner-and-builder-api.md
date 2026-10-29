---
phase: 3
title: "Runner và API builder"
status: completed
priority: P1
effort: "6h"
dependencies: [1, 2]
---

# Phase 3: Runner và API builder

## Goal

lab-server có `POST /api/preview` và `POST /api/run`. Run chạy đúng `argv` đã validate bằng `aws` CLI qua api-tap, trả nguyên văn stdout/stderr, và chỉ nhận yêu cầu từ web app (F4.4, NFR7).

## Files to Create / Modify

- Create: `server/src/cloudy_labs/builder/runner.py`
- Create: `server/src/cloudy_labs/emulator/aws_profile.py`, `server/tests/test_aws_profile.py`
- Modify: `server/src/cloudy_labs/emulator/stack.py` hoặc `cli.py` (`labctl up` gọi ghi profile)
- Modify: `server/src/cloudy_labs/server/app.py` (hai route, kiểm Origin và Content-Type dùng chung với `/ws`)
- Create: `server/tests/test_runner.py`; Modify: `server/tests/test_app.py`
- Modify: `server/src/cloudy_labs/emulator/preflight.py` hoặc `cli.py` (`serve` báo lỗi rõ khi không có `aws` trên PATH)

## Tasks & Steps

- [x] `POST /api/preview` body `{op, params}`: op lạ hoặc params sai schema thì 422; còn lại luôn 200 với `{command, argv, problems}`. Dùng graph hiện tại của hub; AZ của region đọc một lần từ emulator (`describe-availability-zones`) và cache theo phiên server.
- [x] `POST /api/run` cùng body: validate lại phía server (không tin preview cũ); có problem thì 409 kèm problems, không chạy. Hợp lệ thì chạy.
- [x] `runner.py`: `asyncio.Lock` để mỗi lúc một lệnh; `asyncio.create_subprocess_exec("aws", *argv)` (không shell), `argv` đã có `--profile lab`; `env` = môi trường hiện tại bỏ mọi biến `AWS_*` (để không biến nào đè profile), chỉ đặt lại `AWS_CONFIG_FILE` nếu người dùng có đặt; timeout 60 giây thì kill và báo. Trả `{command, exitCode, stdout, stderr, durationMs}`.
- [x] Sau Run, gọi `hub.notify("builder")` (đã có, debounce 150 ms) để không phụ thuộc hoàn toàn vào sự kiện api-tap.
- [x] Bảo vệ route ghi: Origin phải có và thuộc `ALLOWED_ORIGINS`; `Content-Type` phải là `application/json`; nếu không thì 403/415. Chưa có attempt nào đang mở thì 409 "chạy `labctl start <lab>` trước".
<!-- Updated: Validation Session 1 - profile lab do labctl ghi -->
- [x] `aws_profile.py`: `ensure_lab_profile()` ghi khối `[profile lab]` với `endpoint_url = http://127.0.0.1:4566`, `region = us-east-1`, `aws_access_key_id`/`aws_secret_access_key` giả (`config.py`), và dòng đánh dấu `# managed by labctl`. Đường dẫn: `AWS_CONFIG_FILE` hoặc `~/.aws/config`. Chỉ thay khối có dấu đó; nếu có `[profile lab]` không có dấu thì dừng, in hướng dẫn, không ghi. Sao lưu `config.cloudy-labs.bak` trước lần ghi đầu; nội dung đã đúng thì không ghi lại. `labctl up` gọi hàm này; `labctl serve` kiểm và cảnh báo nếu profile thiếu.
- [x] `labctl serve` kiểm `shutil.which("aws")` lúc khởi động; thiếu thì in hướng dẫn cài và vẫn chạy chế độ chỉ xem (preview vẫn dùng được, run trả 503).

## Verification

- `cd server && uv run pytest tests/test_runner.py tests/test_app.py`
- `test_aws_profile.py` trên file tạm: tạo mới, chạy lại không đổi byte, giữ nguyên comment và profile khác, từ chối `[profile lab]` lạ, có bản sao lưu.
- Test runner dùng một script giả thay cho `aws` (đặt PATH trong test) để kiểm argv có `--profile lab`, env không còn `AWS_*`, timeout, lock tuần tự; không cần Docker.
- Test app: Origin lạ → 403, thiếu Origin → 403, `text/plain` → 415, op lạ → 422, problem → 409 và runner không được gọi.
- `uv run pytest -m docker`: thêm một test chạy `create-vpc` qua `/api/run` thật và chờ graph có VPC mới.

## Ghi chú triển khai

- Lệnh tới khi runner đang bận trả `409` thay vì chờ tới lượt, để hai tab không chạy cùng một thao tác hai lần.
- Run bị khoá (`503`, `runBlocker` trong `/api/lab`) không chỉ khi thiếu `aws` mà cả khi AWS CLI cũ hơn 2.13 (bỏ qua `endpoint_url`) hoặc file credentials có `[lab]`, vì hai trường hợp này có thể đưa lệnh tới AWS thật.
- Runner kill cả process group khi timeout hoặc bị huỷ và vẫn trả output đã có. `ensure_lab_profile` ghi qua symlink và không nuốt comment của section kế tiếp. AZ không đọc được thì `create-subnet` bị từ chối.
- Không đọc được id từ stdout thì `expect` là `{after: version}`: web chờ graph mới hơn graph trước khi chạy.
