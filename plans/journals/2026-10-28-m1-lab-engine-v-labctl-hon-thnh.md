---
title: M1 lab engine và labctl hoàn thành
date: 2026-10-28
summary: "labctl up/down/env/start/check/reset/status trên Floci + moto; 58 test đơn vị, 3 test Docker; đã sửa 6 lỗi review"
---

# M1 lab engine và labctl hoàn thành

## What happened
- Hoàn thành plan `plans/261028-1104-m1-lab-engine-labctl`: package `cloudy_labs` trong `server/`, compose Floci + moto (ghim digest, chỉ bind 127.0.0.1), schema lab bằng pydantic, bộ chạy checker, `AwsProvider`, tiến độ SQLite, CLI `labctl`.
- Floci gắn label `io.floci.owner=4566` và `io.floci=aws` lên container EC2, network VPC, volume; container `floci` của compose thì không. Container EC2 còn tham gia network `cloudy-labs_default`, nên `down` phải là stop → dọn mồ côi → compose down → dọn lần nữa.
- Image Floci không có curl/wget/grep: healthcheck dùng bash `/dev/tcp`.
- Review tìm ra kiểm cổng bằng `bind` + `SO_REUSEADDR` bỏ sót listener `0.0.0.0` trên macOS; chuyển sang `connect`.

## Decision
- `start`/`reset` mở attempt trước khi chạy `setup`, vì emulator đã bị xoá thì attempt cũ không còn chấm được.
- `check` trả 0/1/2 (đạt / có check trượt / không chấm được hoặc lỗi bất ngờ).
- Dọn mồ côi không dừng ở lỗi đầu tiên; `down` luôn chạy `compose down` rồi mới báo lỗi.

## Next steps
- Viết Lab 6/7 thật khi có nguồn nội dung, kiểm lại điều kiện qua mốc M1 bằng lab thật.
- Quyết định checker cho moto dùng credential nào khi hết 3 lệnh không xác thực.
- Số lệnh không xác thực của moto đang khai báo ở hai nơi (compose và `providers/aws.py`).

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
