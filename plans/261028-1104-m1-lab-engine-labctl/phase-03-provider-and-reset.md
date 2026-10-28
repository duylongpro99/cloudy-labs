---
phase: 3
title: "Provider và reset"
status: completed
priority: P1
effort: "3h"
dependencies: [2]
---

# Phase 3: Provider và reset

## Goal

Có interface `Provider` (F1.4) và `AwsProvider` trỏ đúng emulator của lab, với `reset` đưa emulator về trạng thái sạch trong vài giây.

## Files to Create / Modify

- Create: `server/src/cloudy_labs/providers/__init__.py` (registry `get_provider(lab)`), `base.py`, `aws.py`
- Create: `server/tests/test_provider_env.py`
- Modify: `server/src/cloudy_labs/cli.py` (lệnh `env`, `reset`)

## Tasks & Steps

1. `base.py`: `Protocol` `Provider` với `client(service)`, `env() -> dict[str, str]`, `reset(lab) -> None`, `health() -> dict[str, bool]`.
2. `aws.py`, `AwsProvider(emulator: "floci" | "moto")`:
   - `endpoint`: `http://127.0.0.1:4566` hoặc `http://127.0.0.1:5050`.
   - `client(service)`: `boto3.client(service, endpoint_url=…, region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test")`. Lab moto sau bước bootstrap dùng key IAM thật do lab tạo; chừa tham số `credentials` để checker truyền vào.
   - `env()`: `AWS_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID=test`, `AWS_SECRET_ACCESS_KEY=test`, `AWS_DEFAULT_REGION=us-east-1`, `AWS_PAGER=""`.
   - `health()`: Floci gọi `sts get-caller-identity` (hoặc endpoint health nếu có, xác minh lúc làm); moto gọi `GET /moto-api/`. Timeout ngắn.
   - `reset(lab)`:
     - Floci: `docker compose -p cloudy-labs restart floci` → chờ healthy → `remove_orphans()` (restart ở chế độ memory không dừng container EC2, theo ghi chú M0).
     - moto: `POST /moto-api/reset` rồi `POST /moto-api/reset-auth` với body là số trần `3` và `Content-Type: text/plain` (body JSON gây HTTP 500, theo spike).
   - Chỉ reset emulator mà lab dùng, để không xoá trạng thái của emulator kia.
3. CLI:
   - `labctl env [lab]` in các dòng `export KEY=value` để dùng với `eval "$(labctl env)"`. Không có lab thì dùng Floci.
   - `labctl reset <lab>` gọi `provider.reset` và in thời gian. Phase 4 nối thêm bước chạy lại `setup` của lab, dùng chung hàm với `start`.
4. Test đơn vị: `env()` và endpoint cho từng emulator; registry báo lỗi rõ khi `provider` không phải `aws`.

## Verification

- `cd server && uv run pytest` qua.
- Thủ công với stack đang chạy: `eval "$(uv run labctl env)" && aws ec2 create-vpc --cidr-block 10.77.0.0/16` → `uv run labctl reset fixture-vpc` → `aws ec2 describe-vpcs` không còn VPC đó; thời gian reset in ra cỡ 1–3 s.
