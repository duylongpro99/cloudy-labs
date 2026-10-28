---
phase: 3
title: "Cảnh mẫu 200 node và đo hiệu năng"
status: completed
priority: P1
effort: "5h"
dependencies: []
---

# Phase 3: Cảnh mẫu 200 node và đo hiệu năng

## Goal

Dựng cảnh theo đúng công thức PRD F3.7 với 200 node tổng hợp, ở cả chủ đề sáng và tối, rồi đo p50/p95 frame time trên Chrome và Safari để chốt mức hậu kỳ mặc định (giả định A6).

## Files to Create / Modify

- Create: `spikes/m0-render/` là project Vite + React + TypeScript, quản lý bằng pnpm. Phiên bản ghim chính xác:
  - `three@0.186.1`
  - `@react-three/fiber@9.8.2`
  - `@react-three/drei@10.7.9`
  - `@react-three/postprocessing@3.2.2`
  - `postprocessing@6.39.5`
  - `n8ao`, `@react-spring/three`: tra phiên bản lúc làm
- Create: `spikes/m0-render/src/fixture.ts`. Sinh cây tài nguyên tổng hợp, xác định theo seed, tổng cộng 200 node: 1 region, 2 VPC, mỗi VPC 3 AZ, mỗi AZ 2 subnet, phần còn lại là instance, NAT và IGW, kèm khoảng 60 cạnh.
- Create: `spikes/m0-render/src/scene/`. Gồm khay lồng nhau với màu viền nhóm AWS, khối dịch vụ có icon placeholder tự vẽ (SVG đơn giản), nhãn troika, cạnh dạng Bezier, xung hạt instanced và theme tokens sáng/tối.
- Create: `spikes/m0-render/src/bench.ts`. Chạy kịch bản đo tự động và xuất kết quả JSON.
- Create: `spikes/m0-render/public/fonts/`. Một font `.woff` có giấy phép OFL và đủ dấu tiếng Việt, ví dụ Be Vietnam Pro hoặc Inter. Ghi lại giấy phép.
- Create: `spikes/m0-render/results/`. Lưu JSON kết quả của từng lần chạy.

## Công thức cần dựng (PRD F3.7)

- **Renderer:** WebGL2, `dpr={[1,2]}`, `frameloop="demand"`, `gl={{ antialias: false }}`.
- **Camera:** `OrthographicCamera` kết hợp `CameraControls`, azimuth 45°, góc nâng khoảng 35°, giới hạn polar từ 15° đến 80°.
- **Ánh sáng:** hemisphere, một đèn directional chính có bóng (chỉ cập nhật bóng khi bố cục đổi), một đèn fill, và `Environment` dựng từ `Lightformer` với `frames={1}`.
- **Vật liệu:** `MeshStandardMaterial` nhám. Khay dùng `opacity` và `renderOrder` cố định.
- **Hậu kỳ:** `EffectComposer multisampling={0}`, sau đó `N8AO` (halfRes, quality medium, khay đặt `treatAsOpaque`), `SMAA`, rồi `ToneMapping` Neutral.
- **Nhãn:** troika `Text` có viền chữ. Nhãn khay nằm phẳng, nhãn node dạng billboard và ẩn khi zoom xa.
- **Tương tác:** `Outlines` khi hover hoặc chọn. Node xuất hiện bằng react-spring.

## Kịch bản đo

Mỗi cấu hình chạy 10 giây trong lúc camera xoay theo kịch bản cố định (`invalidate` mỗi khung), bỏ qua 2 giây đầu để làm nóng. Kết quả ghi gồm p50/p95/p99 frame time, FPS trung bình, và từ `renderer.info` lấy số draw call, số triangle, số program.

| Trục | Giá trị |
|---|---|
| Hậu kỳ | `full` (N8AO + SMAA + ToneMapping), `lite` (SMAA + ToneMapping), `flat` (không hậu kỳ, không bóng) |
| Chủ đề | sáng, tối |
| DPR | 1, 2 |
| Trình duyệt | Chrome, Safari |

Tổng cộng 3 × 2 × 2 × 2 = 24 lần chạy. Ngoài ra đo thêm một lần ở chế độ idle `demand` (cảnh đứng yên) để xác nhận GPU gần như không phải làm gì.

## Tasks & Steps

1. Scaffold project bằng `pnpm create vite`, ghim đúng các phiên bản ở trên, rồi chạy `pnpm install`. Lưu lockfile để Phase 4 dùng.
2. Dựng fixture và layout xác định từ cây chứa, tính kích thước khay từ dưới lên (bottom-up).
3. Dựng cảnh theo công thức và kiểm tra bằng mắt ở cả hai chủ đề. Chụp màn hình lưu vào `results/`.
4. Làm `bench.ts`: đọc cấu hình từ query string, ví dụ `?post=full&theme=dark&dpr=2&run=1`. Khi chạy xong, hiện JSON trên trang và cho tải xuống.
5. **Chrome:** chạy tự động 12 cấu hình bằng Playwright ở chế độ có giao diện (headed, có GPU), hoặc chạy tay nếu Playwright không dùng được GPU.
6. **Safari:** chạy tay 12 cấu hình theo checklist trong `plans/261027-1353-m0-spike-emulator-and-render-validation/notes/safari-checklist.md`, tải JSON về `results/`.
7. Ghi các lỗi hiển thị nếu có: sai thứ tự khay trong suốt, nhãn bị nhoè, dấu tiếng Việt hiển thị sai, viền răng cưa.
8. Dừng Vite dev server.

## Verification

- `results/` có đủ 24 file JSON và ảnh chụp của hai chủ đề.
- Có bảng tổng hợp p95 frame time. Mức `full` đạt hay không đạt ngưỡng 20 ms (tương đương 50 fps) trên Safari ở DPR 2.
- `pnpm tsc --noEmit` không có lỗi.
- `lsof -i :5173` không trả về gì.

## Rủi ro và rollback

- Nếu `full` không đạt trên Safari, kết luận mặc định là `lite` và giữ `PerformanceMonitor` để tự nâng hoặc hạ mức. Kết quả này không chặn M0.
- Nếu `n8ao` hoặc `postprocessing` không tương thích với three 0.186.1, ghi lại lỗi và thử SSAO có sẵn của postprocessing.
- Rollback: xoá `spikes/m0-render/`.
