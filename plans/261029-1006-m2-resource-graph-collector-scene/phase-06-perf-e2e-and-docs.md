---
phase: 6
title: "Đo hiệu năng, kiểm thử đầu-cuối và tài liệu"
status: completed
priority: P1
effort: "4h"
dependencies: [5]
---

# Phase 6: Đo hiệu năng, kiểm thử đầu-cuối và tài liệu

## Goal

Chứng minh bằng số đo rằng M2 đạt điều kiện qua mốc (NFR2, NFR3, NFR8), đóng việc chuyển sang thứ ba (đo lại bench), và cập nhật tài liệu cho các lệnh, cổng và kiến trúc mới.

## Files to Create / Modify

- Modify: `web/src/scene/architecture-scene.tsx` hoặc `web/src/bench/bench.ts` (bench dựng 200 node qua đường graph → adapter)
- Create: `web/src/graph/synthetic-graph.ts` (graph 200 node có seed, dùng cho bench, thay việc gọi thẳng `buildFixture`)
- Create: `plans/261029-1006-m2-resource-graph-collector-scene/notes/perf-results.md`, `notes/e2e-results.md`
- Modify: `docs/labctl.md` (`serve`, bảng cổng 4566/4567/4568/5050/8730, cách mở web)
- Modify: `docs/emulator-differences.md` (cổng host của Floci đổi, `PublicIpAddress` hiển thị bằng cổng host)
- Modify: `docs/product-requirements.md` (ghi chú ở F2.2 rằng api-tap là service compose ở 4566; F1.2 thêm `serve`)
- Modify: `docs/roadmap.md` (dòng M2: trạng thái và link plan)
- Modify: `README.md` (luồng dùng: `labctl up` → `labctl serve` → `pnpm dev`)

## Tasks & Steps

1. **Bench qua đường thật.** `synthetic-graph.ts` sinh `ResourceGraph` 200 node cùng phân bố với fixture M0 (2 VPC, 6 AZ, 12 subnet, NAT, instance, SG, EIP). Bench dùng `graph-to-scene` + layout như màn hình live. Chạy `pnpm bench:chrome` cho cả hai chủ đề, mức `full`, DPR 2; chạy thủ công trên Safari theo checklist Safari của M0. Ghi p50/p95/p99, draw call, program vào `notes/perf-results.md` và so với số đo của plan thư viện object.
2. **Kiểm thử đầu-cuối có Docker**, ghi vào `notes/e2e-results.md`:
   - `labctl up`, `labctl serve`, `pnpm dev` (mỗi tiến trình một lần, ghi PID và cổng).
   - `eval "$(labctl env)"`, chạy `spikes/m0-emulators/lab-06-07.sh`; chụp cảnh cuối ở hai chủ đề; đối chiếu bằng mắt với sơ đồ Lab 6 + 7.
   - Số đo độ trễ từ `test_latency_docker.py` (p50, p95).
   - `labctl reset`: cảnh qua trạng thái `emulator-down` rồi về Region trống, không cần tải lại trang.
   - Tắt `serve` khi web đang mở: web báo `disconnected`, bật lại thì tự nối.
   - Dừng hết tiến trình đã khởi động, `labctl down`, kiểm `docker ps` và `lsof -i :5174 -i :8730` sạch.
3. **Tài liệu:** cập nhật các file ở trên, chỉ ở phần bị ảnh hưởng. Link tới `compose.yaml` và `config.py` thay vì chép lại số cổng ở nhiều nơi nếu có thể.
4. **Đối chiếu Success Criteria** của `plan.md` từng dòng; dòng nào chưa đạt thì ghi rõ lý do vào `notes/e2e-results.md` thay vì đánh dấu đạt.

## Verification

- `cd server && uv run pytest && uv run pytest -m docker`
- `cd web && pnpm typecheck && pnpm test && pnpm build`
- `notes/perf-results.md` có p95 ≤ 20 ms cho Chrome và Safari, cả hai chủ đề.
- `notes/e2e-results.md` có p95 độ trễ ≤ 2 s.
- Link trong các tài liệu đã sửa đều mở được.

## Risk & Rollback

Safari phải đo thủ công; nếu không làm được trong phiên thì ghi rõ "chưa đo Safari" và để mốc M2 ở trạng thái chưa đóng thay vì suy ra từ Chrome. Phase này chỉ thêm số đo và tài liệu, không có rollback mã.
