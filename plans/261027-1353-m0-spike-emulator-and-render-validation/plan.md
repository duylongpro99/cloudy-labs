---
title: "M0 Spike: kiểm chứng emulator, hiệu năng cảnh 3D và giấy phép"
description: "Kiểm chứng bằng thực nghiệm các giả định A4, A6 và giấy phép thương mại trước khi xây Cloudy Labs, đầu ra là một báo cáo spike."
status: completed
priority: P1
effort: 14h
tags: [infra, frontend, experimental]
blockedBy: []
blocks: []
created: 2026-10-27
---

# M0 Spike: kiểm chứng emulator, hiệu năng cảnh 3D và giấy phép

## Overview

M0 là mốc đầu tiên trong [roadmap](../../docs/roadmap.md). Spike này kiểm chứng bằng thực nghiệm ba giả định trong [PRD](../../docs/product-requirements.md) mà M1–M2 đang dựa vào:

- **A4.** Floci (hoặc MiniStack) trả về đủ thuộc tính VPC/EC2 cho resource graph.
- **A6.** Công thức hình ảnh F3.7 đạt ≥ 50 fps với 200 node trên Safari.
- **A8.** Mọi phụ thuộc dự kiến đều cho phép phân phối thương mại cùng một sản phẩm MIT.

Đầu ra của M0 là **một báo cáo spike** và các bản cập nhật PRD/roadmap, **không phải code sản phẩm**. Code spike nằm trong `spikes/` và được coi là dùng một lần. Ghi chú markdown trong quá trình làm nằm trong `notes/` của plan này. M1 không kế thừa code này, chỉ kế thừa các kết luận.

Ngữ cảnh đã có:
- [Nghiên cứu emulator](../reports/research-261027-1027-cloud-simulator-for-hands-on-labs.md)
- [Brainstorm lớp 3D](../reports/brainstorm-261027-1423-3d-architecture-visual-layer.md)
- [Kỹ thuật dựng cảnh](../reports/researcher-261027-1616-3d-architecture-rendering-techniques.md)

## Goals

| # | Mục tiêu | Ưu tiên |
|---|---|---|
| 1 | Chọn backend chính (Floci hoặc MiniStack) dựa trên output `describe-*` thật của Lab 6 + 7 | P1 |
| 2 | Xác nhận proxy `api-tap` chuyển tiếp được lệnh của AWS CLI mà không làm hỏng chữ ký hay response | P1 |
| 3 | Xác nhận moto trả `AccessDenied` thật cho Lab 3 | P2 |
| 4 | Chốt mức hậu kỳ mặc định từ số đo FPS và frame time trên Chrome và Safari, ở cả chủ đề sáng và tối | P1 |
| 5 | Có danh sách giấy phép của mọi phụ thuộc dự kiến, không có giấy phép nào chặn phân phối thương mại | P1 |

## Phases

| # | Phase | Phụ thuộc | Effort | Status |
|---|---|---|---|---|
| 1 | [Emulator Lab 6 + 7 và api-tap](./phase-01-emulator-lab-6-7-and-api-tap.md) | — | 5h | Completed |
| 2 | [moto enforcement IAM cho Lab 3](./phase-02-moto-iam-enforcement.md) | — | 1.5h | Completed |
| 3 | [Cảnh mẫu 200 node và đo hiệu năng](./phase-03-render-benchmark.md) | — | 5h | Completed |
| 4 | [Kiểm tra giấy phép phụ thuộc](./phase-04-license-audit.md) | Phase 3 (cần lockfile npm) | 1h | Completed |
| 5 | [Báo cáo spike và cập nhật PRD/roadmap](./phase-05-spike-report-and-doc-updates.md) | Phase 1–4 | 1.5h | Completed |

Phase 1, 2 và 3 độc lập nên có thể chạy song song. Mỗi phase sở hữu một thư mục riêng trong `spikes/`.

## Tài nguyên cục bộ (theo quy tắc quản lý tiến trình)

| Tiến trình | Cổng | Phase | Dừng bằng |
|---|---|---|---|
| Floci | 4566 | 1 | `docker compose -f spikes/m0-emulators/docker-compose.yml down -v` |
| MiniStack | 4567 | 1 | như trên |
| api-tap | 4580 | 1 | Ctrl+C hoặc dừng background task |
| moto_server | 5000 | 2 | dừng background task |
| Vite dev server | 5173 | 3 | dừng background task |

Trước khi khởi động, kiểm tra cổng bằng `lsof -i :PORT`. Nếu cổng đang bận bởi tiến trình của spike trước thì dừng tiến trình đó, không đổi sang cổng khác. Phase kết thúc nào thì dừng tiến trình của phase đó.

## Môi trường đã kiểm tra (2026-10-27)

Apple M1 Pro, 16 GB RAM, macOS (Darwin 25.6), Docker 29.7.2, aws-cli 2.36.31, Node 24.18.0, pnpm 10.6.2, Python 3.12.10, uv 0.12.6, Chrome và Safari.

Lưu ý: M1 Pro là máy Apple Silicon đời đầu, nên kết quả đo ở đây là cận dưới cho NFR2.

## Success Criteria

- [x] Có báo cáo `plans/reports/spike-<ts>-m0-validation.md` trả lời A4, A6 và A8 bằng số liệu hoặc output thật, mỗi kết luận có đường dẫn tới bằng chứng.
- [x] Đã chọn backend chính và ghi rõ lý do. Có danh sách những trường bị thiếu hoặc sai mà collector ở M2 phải xử lý.
- [x] Có kết luận api-tap: chạy được nguyên trạng, hay cần cách khác.
- [x] Mức hậu kỳ mặc định được chốt bằng số đo p50 và p95 frame time trên Chrome và Safari, ở DPR 2, với cả hai chủ đề.
- [x] Không còn phụ thuộc nào có giấy phép không rõ hoặc không tương thích. Nếu có, đã có phương án thay thế.
- [x] PRD và roadmap đã được cập nhật: A4 và A6 chuyển sang "đã kiểm chứng" hoặc "sai, kèm hướng xử lý", và M0 được đánh dấu hoàn thành.
- [x] Không còn container hay tiến trình nào của spike đang chạy.

## Kết quả

Hoàn thành 2026-10-27. Báo cáo: [spike-261027-2248-m0-validation](../reports/spike-261027-2248-m0-validation.md). Lệch so với plan: moto chạy ở cổng 5050 (cổng 5000 bị AirPlay Receiver của macOS chiếm); instance Lab 7 dùng `t4g.micro` vì AMI arm64; Safari được điều khiển bằng trang đo tự lưu kết quả thay vì chép tay. A5 vẫn chờ pháp lý nhưng không chặn.

## Rủi ro

- Floci hoặc MiniStack có thể không có image ổn định cho arm64. Khi đó ghi nhận lại và dùng image amd64 qua Rosetta, nhưng đánh dấu kết quả hiệu năng emulator là không đại diện.
- Đo FPS trên Safari phải làm tay vì Playwright WebKit không phải Safari thật. Trang đo cần tự xuất kết quả để giảm sai số khi chép tay.
- Cảnh 200 node dùng dữ liệu tổng hợp. Đây là fixture để đo hiệu năng, không phải dữ liệu hiển thị cho người học, nên không vi phạm nguyên tắc "không dữ liệu giả".

<!-- slug: m0-spike-emulator-and-render-validation -->
