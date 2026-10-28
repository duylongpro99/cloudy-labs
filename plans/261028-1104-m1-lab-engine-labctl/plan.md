---
title: "M1: nền tảng lab và labctl"
description: "Dựng lab engine `labctl` chạy cục bộ trên Floci và moto: định nghĩa lab bằng YAML, chạy checker, reset sạch emulator và lưu tiến độ."
status: completed
priority: P1
effort: 17h
tags: [backend, cli, emulator, m1]
blockedBy: []
blocks: []
created: 2026-10-28
---

# M1: nền tảng lab và `labctl`

## Overview

Đây là mốc M1 trong [roadmap](../../docs/roadmap.md). Người dùng chốt ngày 2026-10-28: làm M1 ngay, trước phần collector còn lại của M2.

Kết quả mong muốn: một lệnh `labctl up` dựng emulator, rồi `labctl start <lab>`, người học tự gõ AWS CLI, `labctl check <lab>` chấm bài, và `labctl reset <lab>` đưa emulator về trạng thái sạch. Phạm vi PRD: F1.1–F1.5, NFR1, NFR5–NFR7.

Ràng buộc:
- **Chưa có nội dung lab.** Lab sẽ lấy từ nguồn trên mạng sau. Plan này chỉ làm khung: schema YAML, bộ nạp lab, bộ chạy checker và một **lab fixture dùng cho test**, không viết Lab 6/7.
- Backend Python 3.12, quản lý bằng uv (PRD A3). Chỉ dùng phụ thuộc có giấy phép cho phép thương mại (A8).
- Emulator ghim theo digest (NFR5), chỉ lắng nghe trên `127.0.0.1` (NFR7), credential giả (NFR6).
- Dùng các kết luận của [báo cáo spike M0](../reports/spike-261027-2248-m0-validation.md) và [ghi chú emulator](../261027-1353-m0-spike-emulator-and-render-validation/notes/emulator-notes.md).

## Goals

- `labctl up | down | env | start <lab> | check <lab> | reset <lab> | status` chạy được trên macOS với Docker Desktop.
- Schema YAML của lab có đủ các trường F1.1 (`id, provider, title, setup, tasks, checks, hints`, cộng `target`), được kiểm bằng pydantic và có thông báo lỗi rõ.
- Checker là hàm Python dùng boto3. Mỗi check trả về `pass/fail`, thông điệp và ID tài nguyên liên quan (F1.3).
- Interface `Provider` có `client(service)`, `env()`, `reset(lab)`, `health()`, bản đầu là `AwsProvider` (F1.4).
- Tiến độ lưu trong SQLite cục bộ, ngoài repo (F1.5).
- Áp dụng các kết luận M0: preflight cảnh báo CIDR trùng mạng Docker, dọn container/network/volume mồ côi của Floci theo label `io.floci.owner`, pull sẵn `alpine/socat:latest`, moto ở cổng 5050 và reset bằng `reset` + `reset-auth`.

## Non-goals

- Nội dung Lab 6, Lab 7 hay bất kỳ lab thật nào. Ghi chú "UserData của Lab 7 phải bind vào IP private" chỉ được ghi vào tài liệu sai khác của emulator để người soạn lab dùng sau.
- `lab-server` (FastAPI), collector, api-tap, WebSocket: thuộc M2 trở đi.
- MiniStack: giữ vai trò dự phòng như kết luận M0, không đưa vào compose của M1.
- Đóng gói phát hành (PyPI, Homebrew).

## Phases

| # | Phase | Trạng thái | Ước lượng | Phụ thuộc |
|---|---|---|---|---|
| 1 | [Package Python và schema lab](./phase-01-python-package-and-lab-schema.md) | Completed | 3h | — |
| 2 | [Stack emulator: compose, up/down, dọn mồ côi](./phase-02-emulator-stack.md) | Completed | 4h | 1 |
| 3 | [Provider và reset](./phase-03-provider-and-reset.md) | Completed | 3h | 2 |
| 4 | [Lab engine: start, check, status, tiến độ](./phase-04-lab-engine-and-progress.md) | Completed | 4h | 1, 3 |
| 5 | [Kiểm thử tích hợp và tài liệu](./phase-05-integration-test-and-docs.md) | Completed | 3h | 4 |

## Kiến trúc

```text
labctl (argparse)
  ├── up / down ───────► emulator/stack.py ──► docker compose (cloudy-labs) ─► floci :4566, moto :5050 (127.0.0.1)
  │                         └── orphans.py ──► docker rm/network rm/volume rm theo label io.floci.owner
  ├── env / reset ─────► providers/aws.py (AwsProvider: client, env, reset, health)
  ├── start ───────────► engine.py: nạp lab ─► preflight CIDR ─► reset ─► mở attempt ─► setup
  ├── check ───────────► engine.py: chạy checker ─► CheckResult(pass/fail, message, resource_ids) ─► SQLite
  └── status ──────────► health + lab đang làm + kết quả check gần nhất
```

Bố cục mã:

```text
server/
  pyproject.toml                  # package cloudy-labs, entry point labctl
  src/cloudy_labs/
    cli.py                        # argparse, in kết quả
    config.py                     # đường dẫn home, thư mục lab, cổng
    labs/schema.py, loader.py     # pydantic model + nạp lab.yaml và checks.py
    checks.py                     # CheckResult, CheckContext, bộ chạy checker
    emulator/compose.yaml         # floci + moto, ghim digest
    emulator/stack.py, docker.py, orphans.py, preflight.py
    providers/base.py, aws.py
    engine.py                     # start / check / status
    progress.py                   # SQLite
  tests/
    fixtures/labs/fixture-vpc/    # lab giả chỉ dùng cho test
labs/                             # nơi chứa lab thật sau này, hiện trống
```

## Success Criteria

- `uv run pytest` trong `server/` qua toàn bộ test đơn vị, không cần Docker.
- `uv run pytest -m docker` qua với Docker đang chạy: `up`, `start fixture-vpc`, tạo VPC bằng boto3 như người học, `check` báo đạt, `reset` rồi `check` báo trượt, sau `down` không còn container/network/volume nào mang label `io.floci.owner` của stack.
- `labctl up` lần hai không tạo container trùng, và báo lỗi rõ khi cổng 4566 hoặc 5050 đang bị tiến trình khác chiếm.
- `labctl start` in cảnh báo khi CIDR của lab trùng một mạng Docker trên máy.
- `docker compose ps` cho thấy cả hai cổng chỉ bind vào `127.0.0.1`.
- Không có secret trong repo; credential là `test`/`test`.
- Điều kiện qua mốc trong roadmap ("làm Lab 6 bằng CLI rồi check đạt") được chứng minh bằng lab fixture. Phần dành cho Lab 6/7 thật sẽ kiểm lại khi có nội dung lab.

## Rủi ro

- **Giá trị label `io.floci.owner`.** Tên network mồ côi (`floci-aws-vpc-4566-…`) gợi ý giá trị là cổng 4566 nhưng chưa xác minh. Phase 2 kiểm bằng `docker inspect` trước khi viết bộ lọc. Chỉ xoá đúng giá trị của stack này, không dùng bộ lọc rộng có thể đụng Floci khác trên máy.
- **Reset bằng restart xoá toàn bộ trạng thái**, không chỉ của một lab. Chấp nhận được vì mỗi máy chỉ có một người học và một lab đang làm.
- **Checker là mã Python nạp từ thư mục lab**, tức là chạy mã tuỳ ý. Lab đi kèm repo nên được tin cậy; tài liệu ghi rõ không nạp lab từ nguồn lạ.
- **Floci cần Docker socket và chạy `user: root`** (theo spike). Đây là yêu cầu của Floci để tạo container EC2; ghi rõ trong tài liệu.

## Validation Log

### Phiên 1 (2026-10-28)

Người dùng chọn cả bốn phương án đề xuất:
- Mã nằm ở `server/`, package `cloudy_labs` dùng chung cho `labctl` và `lab-server` sau này; lab thật ở `labs/` gốc repo.
- moto chạy bằng container `motoserver/moto:5.2.4` trong cùng compose với Floci.
- Thêm lệnh `labctl down` ngoài danh sách F1.2, vì `docker compose down` để lại tài nguyên mồ côi của Floci. PRD F1.2 cập nhật ở Phase 5.
- `reset` dùng restart container + dọn mồ côi (khoảng 1 s), chấp nhận xoá toàn bộ trạng thái emulator của lab đó.

### Verification Results

- Claims checked: 8 (digest Floci trong báo cáo M0 mục 7, image `motoserver/moto:5.2.4` tồn tại trên Docker Hub, `uv` 0.12.6 và Python 3.12.10 có trên máy, Docker 29.7.2 đang chạy, cổng 4566/5050 đang trống, `.gitignore` gốc tồn tại, tên network mồ côi `floci-aws-vpc-4566-…` trong `out/floci/orphans-after-compose-down.txt`, `ak plan validate` OK)
- Verified: 8 | Failed: 0 | Unverified: 1 (giá trị label `io.floci.owner`, để Phase 2 bước 3 kiểm)
- Tier: Full (5 phase)

### Whole-Plan Consistency Sweep

- `down` có mặt ở Goals, Kiến trúc, Phase 2, Phase 5 và Success Criteria.
- Bước chạy lại `setup` khi reset chuyển hẳn sang Phase 4; Phase 3 chỉ còn `provider.reset`.
- Không còn mâu thuẫn chưa giải quyết.

## Kết quả thực hiện (2026-10-28)

- `uv run pytest`: 58 test đơn vị đạt, không cần Docker. `uv run ruff check`: sạch.
- `uv run pytest -m docker`: 3/3 đạt (vòng đời Floci có ghi SQLite, reset moto khôi phục 3 lệnh không xác thực, `down` không để lại gì). Sau khi chạy không còn container, network hay volume nào mang label `io.floci.owner=4566` hoặc thuộc project `cloudy-labs`.
- Label của Floci đã xác minh: xem [ghi chú](./notes/floci-labels.md).

### Sai khác so với plan

- `Provider.reset()` không nhận tham số lab: mỗi provider gắn với một emulator, còn việc chạy lại `setup` thuộc engine.
- `labctl status [lab]` nhận lab tuỳ chọn; lab không tồn tại là lỗi.
- `labctl check` trả mã `2` khi không chấm được, để phân biệt với `1` (có check trượt).
- `start`/`reset` mở attempt **trước** khi chạy `setup`: emulator đã bị xoá nên attempt cũ không còn chấm được nữa.

### Review mã

[Báo cáo review](./reports/code-review.md). Đã sửa:

- **H1** kiểm cổng bằng `connect` thay vì `bind`: trên macOS `bind` 127.0.0.1 vẫn thành công khi có tiến trình nghe ở `0.0.0.0`.
- **H2** bộ chạy checker kiểm kiểu từng trường của `CheckResult`; `main` bắt mọi lỗi bất ngờ và trả `2` cho `check`.
- **M1** `up` chỉ dọn mồ côi khi Floci không chạy, để không xoá instance của Floci đang sống.
- **M2** thứ tự reset → mở attempt → setup; lỗi `setup` gợi ý `labctl reset`.
- **M3** module checker được đăng ký vào `sys.modules` (dataclass trong `checks.py` chạy được).
- **M4** `remove_orphans` xoá tiếp khi một tài nguyên lỗi và gom lỗi lại; `down` vẫn chạy `compose down` rồi mới báo lỗi, `up` chỉ cảnh báo, `reset` báo lỗi.
- `status <lab lạ>` báo lỗi thay vì trả kết quả rỗng.

Đã kiểm và không sửa: reviewer lo `reset` không xoá được network VPC vì Floci tự gắn container của nó vào. Chạy thử với một instance đang sống: `reset` xong trong 4,6 s, không còn network nào mang label.

### Theo sau quyết định của người dùng (2026-10-28)

- **Kiểm lại mốc bằng lab thật:** ghi vào hàng M1 của [roadmap](../../docs/roadmap.md); làm khi có nội dung Lab 6 + 7.
- **Checker trên moto dùng credential IAM:** sau `reset-auth`, provider dùng đúng 3 lượt không xác thực để tạo user `cloudy-labs-admin` (CreateUser, PutUserPolicy `*`, CreateAccessKey) và lưu key ở `CLOUDY_LABS_HOME/moto-credentials.json` (`0600`). `labctl env` và checker ký bằng key này; `test`/`test` bị từ chối. Đã thử trên moto 5.2.4 thật: user không có policy bị `AccessDenied`.
- **Một nguồn cho số lượt không xác thực:** bỏ `INITIAL_NO_AUTH_ACTION_COUNT` khỏi `compose.yaml`, chỉ còn `MOTO_NO_AUTH_ACTIONS` trong `providers/aws.py`; test khẳng định số lệnh bootstrap bằng đúng con số này.
- Test: 59 test đơn vị, 3/3 test Docker (test moto mới: `test`/`test` bị `AuthFailure`, check đạt bằng key admin, sau `reset` key cũ mất hiệu lực và check trượt). Không còn tài nguyên sót lại.
