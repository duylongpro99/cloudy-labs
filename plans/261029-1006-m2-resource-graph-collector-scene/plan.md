---
title: "M2: resource graph, collector và cảnh 3D trực tiếp"
description: "Đọc trạng thái Floci thành resource graph, đẩy qua WebSocket tới trình duyệt và vẽ thành cảnh kiến trúc 3D chỉ xem, cập nhật trong ≤ 2 giây sau mỗi lệnh CLI."
status: completed
priority: P1
effort: 27h
branch: master
tags: [feature, backend, frontend, api, 3d, m2]
blockedBy: []
blocks: []
created: 2026-10-29
---

# M2: resource graph, collector và cảnh 3D trực tiếp

## Overview

Đây là nửa còn lại của mốc M2 trong [roadmap](../../docs/roadmap.md). Nửa đầu, [thư viện 3D object](../261028-0230-m2-aws-icon-3d-object-library/plan.md), đã xong. Plan này nối thư viện đó với trạng thái thật của emulator: người học gõ AWS CLI, và cảnh 3D tự hiện đúng cấu trúc trong ≤ 2 giây.

Phạm vi PRD: F2.1–F2.4, F3.1–F3.9 (phần còn thiếu: F3.3 với dữ liệu thật, F3.4 panel thuộc tính, F3.5 cạnh từ quan hệ thật, F3.6 hoạt ảnh xoá và hiệu ứng "lệnh bay tới dịch vụ", F3.9 theo cài đặt hệ thống), NFR2–NFR4, NFR7, NFR8.

Quyết định của người dùng ngày 2026-10-29:
- **`labctl serve` là lệnh riêng, chạy foreground.** `labctl up` vẫn chỉ dựng emulator; làm lab chỉ bằng CLI không cần server.
- **api-tap chiếm cổng 4566** mà người học đang dùng; Floci lùi sang cổng host nội bộ. `labctl env` và checker giữ nguyên endpoint 4566.
- **Web chạy bằng Vite dev server** (5174), proxy `/api` và `/ws` sang lab-server. Việc lab-server phục vụ bản build để sau.

Hệ quả của hai quyết định đầu: api-tap phải sống cùng emulator chứ không nằm trong `serve`, nếu không thì tắt server là CLI mất kết nối. Vì vậy **api-tap là một service trong compose**, đặt trước Floci, và phát sự kiện ghi qua một kênh SSE riêng. lab-server đăng ký kênh đó khi chạy; không có ai nghe thì sự kiện bị bỏ.

Ngữ cảnh đã có:
- [Báo cáo spike M0](../reports/spike-261027-2248-m0-validation.md): mục 2 (5 điểm collector phải xử lý với Floci), mục 5 (cạm bẫy R3F).
- `spikes/m0-emulators/api-tap.py`: proxy stdlib đã chứng minh giữ được SigV4, thêm p95 5,3 ms. `spikes/m0-emulators/lab-06-07.sh`: 36 bước CLI của Lab 6 + 7, dùng làm kịch bản kiểm thử (không phải nội dung lab).
- [Label của Floci](../261028-1104-m1-lab-engine-labctl/notes/floci-labels.md): container EC2 mang `io.floci.resource-id`, owner là `4566`.
- Mục "Chuyển sang plan sau" của [plan thư viện object](../261028-0230-m2-aws-icon-3d-object-library/plan.md#chuyển-sang-plan-sau).

## Goals

| # | Mục tiêu | Ưu tiên |
|---|---|---|
| 1 | Collector đọc mọi loại tài nguyên F2.4 từ Floci thành resource graph (`nodes`, `contains`, `edges`) có schema, xử lý đủ 5 điểm của spike mục 2 | P1 |
| 2 | api-tap đứng ở 4566, chuyển tiếp nguyên vẹn và phát sự kiện khi gặp lệnh ghi; polling 5 giây làm lưới an toàn (F2.2) | P1 |
| 3 | `labctl serve` chạy lab-server trên `127.0.0.1:8730`, đẩy graph và sự kiện API qua WebSocket (F2.3, NFR7) | P1 |
| 4 | Web vẽ cảnh từ graph thật với bố cục xác định, chỉ phụ thuộc graph (F3.3, NFR4) | P1 |
| 5 | Hoạt ảnh xuất hiện không chạy lại khi placement đổi giữa chừng; có hoạt ảnh xoá, hiệu ứng lệnh bay, panel thuộc tính, cạnh cấu hình (F3.4–F3.6) | P1 |
| 6 | Tạo tài nguyên bằng CLI thì cảnh cập nhật ≤ 2 giây p95 (NFR3); ≥ 50 fps với 200 node ở cả hai chủ đề trên Chrome và Safari (NFR2, NFR8) | P1 |

## Non-goals

- Builder kéo-thả, command-builder, chạy lệnh từ web (M3, M4).
- Ghost và trường `target` (M6). Chat (M5).
- Tài nguyên ngoài F2.4 (IAM, S3, Lambda…) và hiển thị moto (M7). Collector chỉ đọc Floci.
- lab-server phục vụ bản build của web; đóng gói phát hành.
- Nội dung Lab 6/7 thật. Kịch bản `lab-06-07.sh` chỉ là chuỗi lệnh để tạo tài nguyên.
- Lưu lịch sử graph hay replay.

## Phases

| # | Phase | Trạng thái | Ước lượng | Phụ thuộc |
|---|---|---|---|---|
| 1 | [api-tap trong compose, Floci lùi cổng](./phase-01-api-tap-service.md) | Completed | 5h | — |
| 2 | [Schema resource graph và collector](./phase-02-graph-schema-and-collector.md) | Completed | 5h | — |
| 3 | [lab-server và `labctl serve`](./phase-03-lab-server-and-serve.md) | Completed | 4h | 1, 2 |
| 4 | [Web: nguồn dữ liệu trực tiếp và bố cục xác định](./phase-04-web-live-graph-source.md) | Completed | 4h | 2 (golden graph), 3 (giao thức WS) |
| 5 | [Hành vi cảnh: hoạt ảnh, lệnh bay, panel, cạnh](./phase-05-scene-behaviors.md) | Completed | 5h | 4 |
| 6 | [Đo hiệu năng, kiểm thử đầu-cuối và tài liệu](./phase-06-perf-e2e-and-docs.md) | Completed | 4h | 5 |

Phase 1 và 2 độc lập, làm song song được (file không chồng nhau).

## Kiến trúc

```text
 terminal (aws CLI, eval "$(labctl env)")          trình duyệt (Vite :5174)
          │ :4566                                      │ /ws, /api (proxy)
          ▼                                            ▼
 ┌─────────────────── compose cloudy-labs ───┐   ┌──────── labctl serve :8730 ─────────┐
 │ api-tap  127.0.0.1:4566 ──► floci:4566    │   │ TapListener ◄─ SSE :4568/events     │
 │          127.0.0.1:4568  /events (SSE)  ──┼──►│   └─ write event ─► debounce 150 ms │
 │ floci    127.0.0.1:4567 (host, trực tiếp) │◄──┤ Collector (boto3 → :4567 trực tiếp) │
 │ moto     127.0.0.1:5050                   │   │   + poll 5 s + docker port lookup   │
 └───────────────────────────────────────────┘   │ GraphHub: hash → version → broadcast│
                                                 │ /ws: graph | api-event   /api/graph │
                                                 └─────────────────────────────────────┘
 web/src/graph/    graph-client.ts (WS, reconnect) → graph-to-scene.ts → layout.ts (sắp xếp xác định)
 web/src/scene/    LiveScene: TrayLayer, AwsObjectLayer (entrance/exit), EdgeLayer, ApiFlyLayer, PropertyPanel
```

Hợp đồng trung tâm là resource graph (pydantic ở server, type TS ở web). Một file graph mẫu (golden) do test server sinh ra được test web đọc lại, nên hai phía không thể lệch nhau mà test vẫn xanh.

## Success Criteria

- `uv run pytest` trong `server/` xanh không cần Docker; `pnpm test` và `pnpm typecheck` trong `web/` xanh.
- `uv run pytest -m docker` xanh: chạy `lab-06-07.sh` qua 4566, graph cuối cùng khớp cấu trúc mong đợi (2 subnet public, 2 private, IGW, NAT có EIP, 2 route table, SG, key pair, instance trong đúng subnet), và `down` không để lại tài nguyên mồ côi.
- Độ trễ từ lúc lệnh CLI trả về tới lúc WebSocket nhận graph chứa tài nguyên mới: p95 ≤ 2 giây trên 20 lần đo (NFR3).
- Bench 200 node dựng qua đường graph → adapter → layout: p95 thời gian khung hình ≤ 20 ms ở cả hai chủ đề trên Chrome và Safari (NFR2).
- Kiểm tra trình duyệt tự động: chỉ id mới chạy hoạt ảnh; object đang hiện dở giữ tiến độ khi graph đổi; node bị xoá có hoạt ảnh biến mất; bấm node mở panel thuộc tính.
- Mọi cổng mới chỉ bind `127.0.0.1` (NFR7). Phụ thuộc mới (FastAPI, uvicorn, websockets, image Python cho api-tap) có giấy phép tương thích MIT, ghi vào tóm tắt giấy phép.
- Web không gọi emulator trực tiếp (NFR4): không có URL `:4566`/`:4567` trong `web/src`.

## Rủi ro

- **Floci đổi cổng host có thể làm đổi label `io.floci.owner`** và làm hỏng bộ dọn mồ côi, hoặc container EC2 có thể gọi ngược về Floci qua cổng host. Phase 1 bước 1 kiểm trước khi đổi gì khác. Nếu vỡ: giữ Floci ở cổng container 4566 nhưng không publish 4566 ra host (api-tap tới Floci qua mạng compose), và xem lại nguồn của giá trị owner.
- **api-tap làm hỏng SigV4** nếu đổi header `Host`. Spike đã chứng minh chuyển tiếp nguyên header thì đúng; Phase 1 giữ nguyên cách đó và có test so sánh output.
- **Collector chạy chậm khi có nhiều tài nguyên** làm trượt NFR3. Khoảng 10 lệnh `describe-*` tuần tự trên Floci; đo ở Phase 3 và gọi song song bằng thread pool nếu cần.
- **Reset tạo lại container Floci** làm collector mất kết nối vài giây. lab-server phải coi đó là trạng thái "emulator không sẵn sàng" chứ không crash, và đẩy graph rỗng khi Floci trở lại.
- **Bố cục nhảy khi thêm tài nguyên** vì nhóm đổi kích thước. Chấp nhận trong M2 (bố cục xác định theo trạng thái, không theo lịch sử); camera chỉ tự khớp ở lần tải đầu và khi bấm "Vừa khung".
- **Phụ thuộc vào kịch bản spike** `lab-06-07.sh` cho kiểm thử docker. Đó là chuỗi lệnh, không phải nội dung lab; khi có Lab 6/7 thật thì chạy lại kiểm thử với lab đó.

## Validation Log

### Phiên 1 (2026-10-29)

Người dùng chọn cả ba phương án đề xuất: `labctl serve` riêng; api-tap chiếm 4566; Vite dev server proxy sang lab-server. Hệ quả api-tap thành service compose được ghi ở Overview.

### Verification Results

- Đã kiểm: tập `AwsKind` trong `web/src/scene/aws-objects/manifest.ts` khớp danh sách kind của schema; `spikes/m0-emulators/out/floci/` có output `describe-*` cho VPC, AZ, subnet, IGW, NAT, route table, SG, key pair, instance; `playwright-core` 1.64.1 có `page.routeWebSocket`; cổng 4567, 4568, 8730 chưa được dùng trong code; `ak plan validate` OK.
- Chưa có: output `describe-addresses` trong spike. Phase 2 sinh lại fixture khi cần.
- Chưa kiểm: hành vi `io.floci.owner` và EC2 khi Floci đổi cổng host. Phase 1 bước 1 kiểm trước mọi thay đổi khác.
