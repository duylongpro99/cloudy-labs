---
title: "M3: builder kéo-thả cho Lab 6"
description: "Dựng VPC hoàn chỉnh (VPC, Subnet, IGW, NAT, Route Table, route) bằng kéo-thả trên cảnh 3D; mỗi thao tác hiện lệnh AWS CLI, chỉ chạy khi bấm Run, và cảnh chỉ đổi khi collector xác nhận."
status: in-review
priority: P1
effort: 35h
branch: master
tags: [feature, backend, frontend, api, 3d, m3]
blockedBy: [261029-1006-m2-resource-graph-collector-scene]
blocks: []
created: 2026-10-29
---

# M3: builder kéo-thả cho Lab 6

## Overview

Mốc M3 trong [roadmap](../../docs/roadmap.md). Người học kéo tài nguyên từ palette vào cảnh 3D, điền form tối thiểu, xem lệnh `aws ...` đầy đủ, bấm Run và đọc nguyên văn output. Cảnh vẫn chỉ vẽ theo graph mà collector trả về (F4.5), nên builder không giữ trạng thái AWS riêng.

Phạm vi PRD: F4.1–F4.6 cho VPC, Subnet, IGW, Elastic IP (cần cho NAT), NAT, Route Table, route, association, cùng hai thuộc tính Lab 6 dùng (`enableDnsHostnames`, `MapPublicIpOnLaunch`). A1: lệnh chỉ chạy khi bấm Run.

**Lab 6 thật chưa có nội dung** (M1 còn mở vì lý do này). Plan dùng một lab fixture mô phỏng Lab 6, dựng từ các bước Lab 6 (1–21) của `spikes/m0-emulators/lab-06-07.sh`. Khi Lab 6 thật xuất hiện phải chạy lại kiểm thử đầu-cuối của Phase 6 với lab đó rồi mới đóng M3.

Ngữ cảnh đã có:
- lab-server (`server/src/cloudy_labs/server/app.py`): `/api/graph`, `/ws`, chặn Origin lạ ở WebSocket, `TrustedHostMiddleware` chống DNS rebinding. Chưa có endpoint ghi nào.
- Collector chỉ sinh node AZ khi có subnet dùng AZ đó; IGW chưa attach và Elastic IP nằm trong region (`graph/collector.py:127,139,209`).
- `Engine` biết lab đang mở qua `progress.current_attempt()`; `Provider.env()` cho biến môi trường mà `labctl env` in ra.
- PRD đặt command-builder, validate và runner ở lab-server (Python); M5 (chat) dùng lại cùng bộ validate (F5.3).

## Quyết định thiết kế

- **Trình duyệt gửi thao tác có kiểu, không gửi chuỗi lệnh.** `{op: "create-subnet", params: {...}}`. Server dựng `argv` từ danh mục thao tác cố định, validate với graph hiện tại, rồi chạy `aws` bằng `subprocess` không qua shell. Chuỗi hiện trên panel cũng do server dựng từ chính `argv` đó, nên lệnh hiện ra và lệnh chạy không thể lệch nhau.
- **Một thao tác là một lệnh AWS.** Output nguyên văn (F4.4) chỉ có nghĩa khi mỗi lần Run là một lệnh. NAT cần chọn Elastic IP có sẵn; chưa có thì validate giải thích phải cấp phát trước.
- **Validate một chỗ, ở Python.** Web gọi `/api/preview` mỗi khi form đổi (debounce) để lấy lệnh và lỗi; không viết lại luật CIDR bằng TypeScript.
<!-- Updated: Validation Session 1 - profile lab do labctl ghi -->
- **Lệnh hiển thị theo đúng PRD F4.4: `aws ec2 ... --profile lab --output json`.** `labctl up` ghi một profile `lab` (endpoint api-tap 4566, credential giả) vào file config AWS của người dùng, nên lệnh dán vào bất kỳ terminal nào cũng chạy, không cần `eval "$(labctl env)"`. Runner cũng chạy với `--profile lab` và bỏ các biến `AWS_*` thừa hưởng, để lệnh hiện ra và lệnh chạy dùng cùng cấu hình.
- **Ô thả AZ**: thả Subnet lên VPC (hoặc lên khay AZ đã có), form chọn AZ trong region. AZ trống không được vẽ thành khay vì cảnh chỉ vẽ trạng thái thật.

## Non-goals

- Security Group, Key Pair, Instance, UserData và chế độ luyện tập F4.7 (M4).
- Xoá hay sửa tài nguyên ngoài hai thuộc tính trên; muốn làm lại thì `labctl reset`.
- Chat (M5), ghost và `target` (M6), lab ngoài Lab 6.
- Nút check trên web. Điều kiện qua mốc dùng `labctl check`.
- Nội dung Lab 6 thật.

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Ngữ cảnh lab và lab fixture Lab 6](./phase-01-lab-context-and-fixture-lab.md) | Done |
| 2 | [Command-builder và validate](./phase-02-command-builder-and-validate.md) | Done |
| 3 | [Runner và API builder](./phase-03-runner-and-builder-api.md) | Done |
| 4 | [Web: palette, thả vào cảnh, panel lệnh](./phase-04-web-palette-drop-and-command-panel.md) | Done |
| 5 | [Web: thao tác nối và thuộc tính](./phase-05-web-connect-and-attribute-actions.md) | Done |
| 6 | [Kiểm thử đầu-cuối và tài liệu](./phase-06-e2e-fixture-lab-and-docs.md) | Done |

Phase 1 và 2 độc lập (file không chồng nhau). Phase 4 cần API của Phase 3; Phase 5 dựa trên tương tác kéo của Phase 4.

Kết quả e2e: [notes/e2e-results.md](./notes/e2e-results.md). Review: [reports/code-review-m3.md](./reports/code-review-m3.md). Plan để `in-review` vì M3 chỉ đóng sau khi chạy lại e2e với Lab 6 thật.

## Kiến trúc

```text
 trình duyệt (Vite :5174)                               labctl serve :8730
 ┌──────────────────────────────────────┐   POST /api/preview  ┌──────────────────────────────────┐
 │ Palette (lọc theo lab.builder)       │ ───────────────────► │ ops.py: OPS[op] → build(params)  │
 │  └─ kéo ─► raycast khay/object       │   {command, errors}  │   → argv + display               │
 │ BuildForm (tham số tối thiểu)        │ ◄─────────────────── │ validate.py: luật theo graph hub │
 │ CommandPanel: lệnh, Run, stdout/err  │   POST /api/run      │ runner.py: lock, subprocess aws, │
 │ LiveScene: vẫn chỉ vẽ graph (F4.5)   │ ───────────────────► │   env = provider.env(), timeout  │
 │                                      │ ◄── {exitCode,out,err}│ GET /api/lab: id, tasks, palette│
 │       ▲ /ws graph mới                │                      └───────────┬──────────────────────┘
 └───────┴──────────────────────────────┘                                  │ aws → api-tap :4566
                                                        api-tap phát sự kiện ghi → hub refresh → /ws
```

## Success Criteria

- [x] Chạy `labctl start fixture-lab-06`, hoàn thành mọi task chỉ bằng builder trong trình duyệt, rồi `labctl check fixture-lab-06` báo đạt hết (kiểm thử tự động ở Phase 6).
- [x] Mỗi thao tác hiện lệnh `aws ... --profile lab` đầy đủ trước khi chạy; dán lệnh đó vào một terminal mới cho cùng kết quả.
- [x] `labctl up` ghi profile `lab` mà không làm hỏng phần còn lại của file config AWS: có bản sao lưu, chạy lại không đổi gì, `labctl down` không xoá profile.
- [x] Không có lệnh nào chạy nếu chưa bấm Run; cảnh không đổi trước khi graph mới tới.
- [x] Test validate CIDR phủ: ngoài VPC, chồng lấn subnet khác, prefix ngoài /16–/28, CIDR không chuẩn (bit host khác 0), container sai loại.
- [x] `/api/run` và `/api/preview` từ chối Origin lạ và body không phải JSON; chỉ chạy thao tác trong danh mục.
- [x] `uv run pytest`, `pnpm test`, `pnpm typecheck` xanh; `uv run pytest -m docker` xanh.

## Rủi ro

- **CSRF tới endpoint ghi.** Trang lạ có thể POST `text/plain` tới `127.0.0.1:8730` mà không cần preflight. Bắt buộc Origin thuộc `ALLOWED_ORIGINS` và `Content-Type: application/json` ở mọi route ghi; có test.
- **Kéo-thả trong cảnh orthographic** có thể khó trúng khay khi các khay lồng sát nhau. Chọn khay sâu nhất dưới con trỏ, và tô sáng ô hợp lệ trong lúc kéo.
- **Graph tới chậm sau Run** làm người học tưởng lệnh hỏng. Panel hiện "đang chờ cảnh cập nhật" cho tới khi graph chứa id mà output trả về, hoặc quá 5 giây.
- **Floci khác AWS** ở chỗ validate dựa vào (ví dụ AZ hợp lệ, trạng thái NAT). Validate đọc AZ từ emulator; khác biệt mới ghi vào `docs/emulator-differences.md`.
- **Ghi vào `~/.aws/config` của người dùng.** Đây là file thật, có thể chứa profile công việc. Chỉ thay đúng khối `[profile lab]` bằng thao tác văn bản (không dùng `configparser` vì nó bỏ comment), sao lưu trước lần ghi đầu, tôn trọng `AWS_CONFIG_FILE`, và dừng kèm cảnh báo nếu đã có `[profile lab]` không do labctl tạo.
- **Lab 6 thật khác fixture** (tag bắt buộc, CIDR, số AZ). Thiết kế `builder` trong YAML để lab tự khai báo tag mặc định và palette; kiểm lại khi có lab thật.

## Validation Log

### Phiên 1 (2026-10-29)

- **Lệnh hiển thị**: người dùng chọn `--profile lab` do labctl ghi vào config AWS, thay cho phương án đề xuất (bỏ `--profile`). Thêm việc ghi profile vào Phase 3 và rủi ro về file config của người dùng.
- **Thả Subnet**: thả lên VPC hoặc khay AZ có sẵn, chọn AZ trong form (đề xuất). Không vẽ khay AZ giả.
- **Sửa sai**: không có thao tác xoá trong M3; dùng `labctl reset` (đề xuất).
- **Tag**: lab khai báo `builder.tags` trong YAML, cộng tag Name từ form (đề xuất).

### Verification Results

- Claims checked: 12. Verified: 10. Failed: 2 (đã sửa). Unverified: 0. Tier: Full.
- Đã sửa: hub không có `refresh_soon`, dùng `GraphHub.notify` có sẵn (`server/hub.py:92`). Collector chưa có `enableDnsHostnames`/`mapPublicIpOnLaunch` (`graph/collector.py`), Phase 5 thêm vào collector.
- Đã kiểm: AZ chỉ sinh khi có subnet (`collector.py:127`); IGW chưa attach và EIP nằm trong region (`collector.py:139,209`); `Engine.check` cần attempt đang mở; `ALLOWED_ORIGINS` và `TrustedHostMiddleware` có trong `app.py`; `aws-cli/2.36.31` có trên máy; mẫu kiểm trình duyệt `web/scripts/check-live.mjs` có sẵn; `ak plan validate` OK.

### Whole-Plan Consistency Sweep

- Đã tìm `labctl env` và `--profile` trong mọi file plan: lệnh hiển thị, runner, kiểm thử e2e và tài liệu đều theo `--profile lab`. Không còn mâu thuẫn.
