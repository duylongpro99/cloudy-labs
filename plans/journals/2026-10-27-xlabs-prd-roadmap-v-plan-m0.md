---
title: "XLabs: PRD, roadmap và plan M0"
date: 2026-10-27
summary: "Chốt hướng lớp 3D trên emulator AWS, viết PRD v0.4, roadmap M0–M7 và plan spike M0"
---

# XLabs: PRD, roadmap và plan M0

## What happened
- Người dùng thấy portal của Floci nhàm chán, nên đề xuất xây một lớp trực quan hoá 3D phía trên emulator.
- Đã brainstorm, rồi viết `docs/product-requirements.md` (v0.4) và `docs/roadmap.md` (M0–M7).
- Agent nghiên cứu kỹ thuật dựng cảnh đã ghi báo cáo vào `plans/reports/researcher-261027-1616-3d-architecture-rendering-techniques.md`.

## Decision
- **Thứ tự tính năng:** builder kéo-thả trước, rồi chat gợi ý lệnh, cuối cùng là twin.
  - Hạ tầng đồng bộ trạng thái (resource graph) phải có trước builder, vì builder vẽ cảnh dựa trên trạng thái thật của emulator.
- **Builder:** hiện lệnh CLI và chỉ chạy khi người học bấm Run.
- **Chat:** dùng provider của người dùng, hỗ trợ cả định dạng API `openai` và `anthropic`.
- **Stack:** React/TS + React Three Fiber cho frontend, Python/FastAPI cho backend.
- **Phong cách hình ảnh:** sơ đồ AWS dựng thành 3D, camera trực giao isometric. Ghim three 0.186.1 vì postprocessing yêu cầu three dưới 0.187.
- **Sản phẩm:** tên là XLabs, mã nguồn mở MIT, thương mại hoá dưới dạng bản chạy trên máy người dùng.
  - Bộ icon mặc định tự vẽ, vì điều khoản dùng icon AWS trong sản phẩm thương mại chưa rõ.
  - Có cả chủ đề sáng và tối.

## Next steps
- Thực thi plan `plans/261027-1353-m0-spike-emulator-and-render-validation/`:
  - Ma trận trường `describe-*` cho Lab 6 + 7 trên Floci và MiniStack.
  - Kiểm tra api-tap.
  - moto cho Lab 3.
  - Đo cảnh 200 node trên Chrome và Safari.
  - Kiểm tra giấy phép các phụ thuộc.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
