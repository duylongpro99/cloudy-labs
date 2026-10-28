---
phase: 2
title: "moto enforcement IAM cho Lab 3"
status: completed
priority: P2
effort: "1.5h"
dependencies: []
---

# Phase 2: moto enforcement IAM cho Lab 3

## Goal

Xác nhận moto server, khi bật `INITIAL_NO_AUTH_ACTION_COUNT`, thực sự đánh giá IAM policy. Cụ thể, với key của `alice`, lệnh `PutObject` vào prefix `alice/` phải thành công, còn vào `bob/` phải trả `AccessDenied`.

## Files to Create / Modify

- Create: `spikes/m0-moto/pyproject.toml`. Ghim `moto[server]`, tra phiên bản mới nhất lúc làm (báo cáo nghiên cứu ghi 5.2.4).
- Create: `spikes/m0-moto/lab-03.sh`. Kịch bản: dùng credential admin để tạo bucket, user `alice`, policy chỉ cho phép `s3:PutObject` trên `arn:aws:s3:::lab03/alice/*`, và access key. Sau đó dùng profile của alice để thử ghi vào hai prefix.
- Create: `spikes/m0-moto/out/` (output và exit code)

## Tasks & Steps

1. `uv run --project spikes/m0-moto moto_server -p 5000` chạy nền, với `INITIAL_NO_AUTH_ACTION_COUNT` đặt bằng đúng số lệnh setup cần chạy bằng admin. Kiểm tra cổng 5000 trước khi chạy.
2. Chạy `lab-03.sh` và lưu output.
3. Thử thêm hai trường hợp sửa policy: thêm `Deny` tường minh, và dùng `Condition`. Ghi lại trường hợp nào moto đánh giá đúng, trường hợp nào không.
4. Thử `aws iam simulate-principal-policy` trên moto, và cả trên Floci nếu Phase 1 còn chạy. Nếu lệnh này dùng được, checker IAM sẽ tốt hơn (câu hỏi mở số 5 trong báo cáo nghiên cứu).
5. Gọi API reset của moto (`/moto-api/reset`) và xác nhận trạng thái về sạch.
6. Dừng moto_server.

## Verification

- `out/` có bằng chứng: `alice/x` có exit code 0, còn `bob/x` có stderr chứa `AccessDenied`.
- Có bảng các trường hợp policy được đánh giá đúng hoặc sai.
- `lsof -i :5000` không trả về gì.

## Rủi ro và rollback

- Nếu đếm sai `INITIAL_NO_AUTH_ACTION_COUNT`, các lệnh setup sẽ bị chặn. Khi đó tăng giá trị lên và ghi lại con số đúng.
- Rollback: xoá `spikes/m0-moto/`.
