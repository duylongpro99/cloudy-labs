---
title: "M4: builder kéo-thả cho Lab 7 và chế độ luyện tập"
description: "Chạy EC2 trong VPC bằng builder: Security Group và rule inbound, Key Pair, Instance kèm UserData, gắn SG vào instance; thêm chế độ luyện tập chỉ hiện lệnh để người học tự gõ ở terminal."
status: completed
priority: P1
effort: 32h
branch: master
tags: [feature, backend, frontend, api, 3d, m4]
blockedBy: [261029-1525-m3-builder-lab-06]
blocks: []
created: 2026-10-30
---

# M4: builder kéo-thả cho Lab 7 và chế độ luyện tập

## Overview

Mốc M4 trong [roadmap](../../docs/roadmap.md). Người học dựng một web server EC2 trong VPC có sẵn chỉ bằng builder: tạo Security Group, thêm rule inbound, tạo Key Pair, kéo Instance vào subnet công khai kèm UserData, và gắn thêm SG vào instance bằng cách kéo cạnh. Chế độ luyện tập (F4.7) dùng cùng form và cùng lệnh, nhưng ẩn nút Run: người học dán lệnh vào terminal, api-tap báo ghi, collector cập nhật cảnh, và panel tự báo xong khi graph có đúng thứ lệnh đó tạo ra.

Phạm vi PRD: F4.1–F4.6 cho Security Group, Key Pair, Instance và UserData; F4.7 (P1). A1 giữ nguyên: ở chế độ thường, lệnh chỉ chạy khi bấm Run; ở chế độ luyện tập, builder không chạy gì.

**Lab 7 thật chưa có nội dung.** Plan dùng `fixture-lab-07`, dựng từ phần Lab 7 của `spikes/m0-emulators/lab-06-07.sh`. Vì `labctl start` reset emulator, lab fixture có bước `setup` dựng sẵn mạng của Lab 6 (VPC, subnet công khai có route tới IGW). Khi Lab 7 thật xuất hiện phải chạy lại kiểm thử đầu-cuối của Phase 6 với lab đó rồi mới đóng M4.

Ngữ cảnh đã có (M3):
- Danh mục op cố định `builder/ops.py` (`Op`, `catalog`, `expectation`, `result_id`), validate theo graph `builder/validate.py`, runner không qua shell `builder/runner.py`, các route `/api/lab`, `/api/preview`, `/api/run` trong `server/app.py`.
- Collector đã đọc Security Group (`ingress` gồm `protocol`, `from`, `to`, `sources`), Key Pair (id là `KeyPairId`, nhãn là `KeyName`), Instance (trong subnet, `state`, `keyName`, `hostPorts`), cạnh `attached` SG→instance và `uses-key` instance→key pair (`graph/collector.py:162-205`).
- Web: máy trạng thái `use-builder.ts` (idle → dragging/connecting → form → running → waiting → done/failed), `form-model.ts`, `connect-rules.ts`, `drop-targets.ts`, `build-form.tsx`, `command-panel.tsx`; sự kiện api-tap đã tới trình duyệt qua `/ws` (`type: "api-event"`).
- `Lab.setup` chạy các hàm `module:function` với `ctx` sau mỗi lần reset (`engine.py:66-80`).

## Quyết định thiết kế

- **Giữ nguyên mô hình M3.** Trình duyệt gửi `{op, params}`; server dựng argv, validate, chạy. Một thao tác là một lệnh AWS. Thêm 5 op: `create-security-group`, `authorize-security-group-ingress`, `create-key-pair`, `run-instances`, `modify-instance-attribute` (gắn SG).
- **Cử chỉ:**
  - Security Group: kéo vào VPC (create). Thêm rule inbound: nút trên panel thuộc tính của SG (attribute), form có protocol, port, CIDR nguồn.
  - Key Pair: kéo vào region (create).
  - Instance: kéo vào subnet (create). Form chọn AMI, instance type, một SG cùng VPC, key pair, UserData.
  - Gắn SG vào instance: kéo cạnh từ SG tới instance (connect). Argv là `modify-instance-attribute --groups <SG hiện có> <SG mới>`, vì `--groups` thay cả danh sách.
- **Params vẫn là chuỗi.** Port, protocol, UserData đều là `str`; validate giải thích khi sai, giống CIDR ở M3. Không thêm kiểu list vào form: `run-instances` nhận một SG, SG thứ hai gắn bằng cạnh.
- **AMI và instance type theo kiến trúc máy.** Server khai báo danh sách cho phép (arm64: `ami-amazonlinux2023-arm64`, `t4g.micro`/`t4g.small`; x86_64: `ami-amazonlinux2023`, `t3.micro`/`t3.small`), chọn theo `platform.machine()` và trả trong `/api/lab`. Chỉ AMI có trong catalog mới dùng image dựng sẵn (`docs/emulator-differences.md`).
- **Kết quả có kiểu `includes`.** Rule inbound không tạo node hay cạnh mới, nên `expect` thêm dạng `{node, prop: "ingress", includes: {...}}`; web `expectMet` hiểu dạng này. `result_id` hỗ trợ chỉ số mảng (`Instances.0.InstanceId`).
- **Chế độ luyện tập không cần server biết.** `/api/preview` trả thêm `practiceExpect`: với op create là `{kind, label}` (Name tag trong form), với op connect/attribute là đúng `expect` đã có (cạnh, thuộc tính, `includes`). Web ở chế độ luyện tập ẩn Run, giữ nút Chép, và chờ graph khớp `practiceExpect`, không giới hạn thời gian. Chế độ lưu trong `localStorage` của trình duyệt.

## Non-goals

- Xoá, dừng hay terminate instance, xoá rule SG. Muốn làm lại thì `labctl reset`.
- Rule outbound, rule tham chiếu SG khác, IPv6.
- SSH vào instance từ web, hay terminal nhúng trong web.
- Chat (M5), ghost và `target` (M6), lab ngoài Lab 7.
- Nội dung Lab 7 thật.

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Lab fixture Lab 7 và schema builder](./phase-01-fixture-lab-07-and-schema.md) | Completed |
| 2 | [Op và validate cho SG, Key Pair, Instance](./phase-02-ops-and-validate.md) | Completed |
| 3 | [API: lựa chọn EC2, expect mới, practiceExpect](./phase-03-api-choices-and-expectations.md) | Completed |
| 4 | [Web: form EC2, rule SG, gắn SG, tải .pem](./phase-04-web-ec2-forms-and-actions.md) | Completed |
| 5 | [Web: chế độ luyện tập](./phase-05-web-practice-mode.md) | Completed |
| 6 | [Kiểm thử đầu-cuối và tài liệu](./phase-06-e2e-and-docs.md) | Completed |

Phase 1 và 2 độc lập (file không chồng nhau). Phase 3 cần op của Phase 2. Phase 4 và 5 cần API của Phase 3; Phase 5 sửa `use-builder.ts` sau Phase 4 nên làm tuần tự. Phase 6 cần tất cả.

## Kiến trúc

```text
 trình duyệt (Vite :5174)                                 labctl serve :8730
 ┌────────────────────────────────────────┐ POST /api/preview ┌───────────────────────────────────────┐
 │ Palette: SG, Key Pair, Instance        │ ────────────────► │ ops.py: 5 op mới → argv               │
 │ BuildForm: select SG/key/AMI/type,     │ {command, problems│ validate.py: SG cùng VPC, port, cổng  │
 │   textarea UserData (mặc định của lab) │  practiceExpect}  │   22 mở 0.0.0.0/0 bị chặn, ...        │
 │ Nút "Thêm rule inbound" trên SG        │ ◄──────────────── │ ec2_choices: AMI + type theo kiến trúc│
 │ Cạnh SG → Instance                     │ POST /api/run     │ runner.py (không đổi)                 │
 │ CommandPanel: Run | (luyện tập) Chép   │ ────────────────► │ expect: node | edge | prop | includes │
 │   + nút tải .pem sau create-key-pair   │                   └──────────────────┬────────────────────┘
 │       ▲ /ws: graph mới + api-event     │                                      │ aws → api-tap :4566
 └───────┴────────────────────────────────┘                                      │
   terminal người học (luyện tập): aws ... --profile lab ──► api-tap ──► sự kiện ghi ──► hub refresh
```

## Success Criteria

- [ ] `labctl start fixture-lab-07`, hoàn thành mọi task chỉ bằng builder, rồi `labctl check fixture-lab-07` báo đạt hết, kể cả check "web server trả lời qua cổng host" (kiểm thử tự động ở Phase 6).
- [ ] Rule `tcp 22` từ `0.0.0.0/0` bị validate chặn kèm giải thích; check `ssh-not-open-to-world` đạt.
- [ ] Mỗi thao tác hiện lệnh `aws ... --profile lab --output json` đầy đủ, kể cả UserData nhiều dòng; dán lệnh vào terminal mới cho cùng kết quả.
- [ ] Sau `create-key-pair`, panel hiện stdout nguyên văn và nút tải `<tên>.pem`; server không ghi private key ra đĩa hay log.
- [ ] Chế độ luyện tập: không có `/api/run` nào được gọi; người học chạy lệnh đã chép ở terminal và panel báo xong khi graph khớp `practiceExpect`. Làm hết fixture-lab-07 bằng chế độ này cũng qua `labctl check`.
- [ ] Test validate phủ: SG khác VPC với subnet, port ngoài 0–65535 hoặc không phải số, protocol lạ, cổng 22 mở cho `0.0.0.0/0`, rule trùng, tên SG trùng trong VPC, tên SG bắt đầu bằng `sg-`, key pair trùng tên, AMI/type không thuộc danh sách, UserData quá 16 KB, SG đã gắn vào instance.
- [ ] `uv run pytest`, `pnpm test`, `pnpm typecheck` xanh; `uv run pytest -m docker` xanh.

## Rủi ro

- **Floci có thể chưa hỗ trợ `modify-instance-attribute --groups`** hoặc tag trên key pair. [UNVERIFIED] Phase 2 thử trên Floci trước khi viết op; nếu không hỗ trợ thì bỏ cạnh SG→instance khỏi M4, ghi vào `docs/emulator-differences.md`, và báo lại người dùng.
- **Private key đi qua HTTP tới trình duyệt.** Chỉ là key của emulator, server chỉ nghe loopback và route đã chặn Origin lạ. Không log stdout của runner; nút .pem dựng file trong trình duyệt bằng `Blob`.
- **UserData nhiều dòng trong lệnh hiển thị.** `shlex.join` cho chuỗi trích dẫn đơn chạy được trong bash/zsh nhưng dài. Panel lệnh phải cuộn được và nút Chép chép đúng chuỗi đó; e2e kiểm dán vào `bash -c`.
- **Instance `running` trước khi UserData xong.** Check web server phải nói người học có thể phải chờ (theo `docs/emulator-differences.md`); e2e chờ tới 60 giây.
- **Chế độ luyện tập khớp nhầm.** Khớp theo `kind` + Name tag có thể trùng nếu người học tạo hai tài nguyên cùng tên; `suggestName` đã tránh trùng, và validate từ chối tên SG trùng trong VPC và key pair trùng tên.
- **Lab 7 thật khác fixture** (AMI, cổng, UserData dùng `dnf install httpd`). `builder.userData` để lab tự khai báo; kiểm lại khi có lab thật.

## Validation Log

### Phiên 1 (2026-10-30)

- **Key Pair**: giữ stdout nguyên văn (có `KeyMaterial`) và thêm nút tải `<tên>.pem` trong trình duyệt; server không ghi key ra đĩa (đề xuất).
- **Cổng 22 mở cho `0.0.0.0/0`**: validate chặn, Run bị khoá, kèm giải thích; không thêm kênh cảnh báo mới (đề xuất).
- **UserData**: textarea tự do, điền sẵn từ `builder.userData` của lab; giới hạn 16 KB; gợi ý không chặn khi script bind `0.0.0.0:80` hoặc chạy `http.server 80` không có `--bind` (đề xuất).
- **Chế độ luyện tập**: panel chờ graph khớp kind + Name tag (create) hoặc cạnh/thuộc tính (connect, attribute), không giới hạn thời gian (đề xuất).

### Verification Results

- Claims checked: 12. Verified: 11. Failed: 0. Unverified: 1. Tier: Full.
- Đã kiểm: collector đọc SG/key pair/instance và cạnh `attached`, `uses-key` (`collector.py:162-205`); `Lab.setup` chạy sau reset (`engine.py:72`); `result_id` hiện chỉ đi qua dict, chưa hỗ trợ chỉ số mảng (`ops.py:183`); `fixedDraft` khoá mọi trường trừ `destination` (`form-model.ts:97`); `BuilderKind` chưa có `security-group`, `key-pair`, `instance` (`labs/schema.py:40`); `KIND_LABEL` web chưa có ba kind này (`drop-targets.ts:8`); `expectMet` chỉ có `after`, `edge`, `node`/`prop` (`use-builder.ts:40`); máy hiện tại là `arm64`; catalog có `ami-amazonlinux2023-arm64` và alias `ami-amazonlinux2023`.
- Chưa kiểm: Floci hỗ trợ `modify-instance-attribute --groups` (Phase 2 thử trước).

### Whole-Plan Consistency Sweep

- Đã rà `practiceExpect`, `includes`, `builder.userData`, `ec2_choices` trong mọi file phase: tên và hình dạng thống nhất giữa Phase 2, 3, 4, 5. Không còn mâu thuẫn.
