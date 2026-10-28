# Ghi chú cảnh 3D và đo hiệu năng (Phase 3), 2026-10-27

Ghi chú thô cho báo cáo spike. Code: `spikes/m0-render/`. Kết quả: `spikes/m0-render/results/` (24 JSON đo, 2 JSON idle, 4 ảnh chụp, `summary.md`).

## Phiên bản đã ghim (`spikes/m0-render/package.json`, `pnpm-lock.yaml`)

three 0.186.1, @react-three/fiber 9.8.2, @react-three/drei 10.7.9, @react-three/postprocessing 3.2.2, postprocessing 6.39.5, n8ao 2.0.1, @react-spring/three 10.1.2, react/react-dom 19.3.1 (R3F 9.8.2 yêu cầu react `>=19 <19.4`), vite 8.3.5, @vitejs/plugin-react 6.1.2, typescript 7.0.2, playwright-core 1.64.1.

Font: Be Vietnam Pro Medium (OFL-1.1). Tải TTF từ `google/fonts`, đổi sang `.woff` bằng fontTools. Đã kiểm đủ 74 ký tự có dấu tiếng Việt (chữ thường và hoa đặc trưng, cùng mọi tổ hợp thanh điệu của chữ thường). Giấy phép: `spikes/m0-render/public/fonts/BeVietnamPro-OFL.txt`.

## Môi trường đo

Apple M1 Pro, màn hình tích hợp Liquid Retina XDR (ProMotion 120 Hz). Chrome 156.0.8078.48 chạy qua Playwright `channel: 'chrome'` ở chế độ có giao diện; GPU báo cáo là ANGLE Metal, Apple M1 Pro. Safari 26.6.2 chạy bằng Safari thật; GPU báo cáo là "Apple GPU". Canvas cố định 1280×800 CSS px, nên DPR 2 tương đương 2560×1600 pixel. Cảnh có 200 node, 60 cạnh và 60 hạt xung, một node được chọn (có `Outlines`). Camera xoay 30°/s.

## Kết quả

Bảng đầy đủ: `spikes/m0-render/results/summary.md`.

| Trình duyệt | Mức | p50 | p95 (xấu nhất trong 4 cấu hình chủ đề × DPR) | FPS TB | Draw call | Program |
|---|---|---|---|---|---|---|
| Chrome | full | 8,3 ms | 9,3 ms | ~120 | 680 | 24 |
| Chrome | lite | 8,3 ms | 9,3 ms | ~120 | 448 | 16 |
| Chrome | flat | 8,3 ms | 9,3 ms | ~120 | 445 | 12 |
| Safari | full | 17 ms | 17 ms (p99 21 ms ở dark DPR 2) | 59,6–60 | 680 | 24 |
| Safari | lite | 17 ms | 17 ms | 59,7–60 | 448 | 16 |
| Safari | flat | 17 ms | 17 ms | 59,8–60 | 445 | 12 |

- **A6 đạt:** mức `full` trên Safari ở DPR 2 có p95 17 ms ở cả hai chủ đề, dưới ngưỡng 20 ms.
- Mọi cấu hình đều chạm trần vsync: 120 Hz trên Chrome, 60 Hz trên Safari. Safari mặc định giới hạn rAF ở 60 fps, và `performance.now()` của Safari làm tròn tới 1 ms nên số đo là 17 thay vì 16,7. Vì vậy bài đo này **không đo được dư địa** giữa các mức hậu kỳ, chỉ xác nhận cả ba đều đạt ngưỡng. Muốn đo dư địa cần GPU timer query; Safari không hỗ trợ `EXT_disjoint_timer_query_webgl2`.
- Chủ đề sáng và tối không khác nhau về chi phí (cùng draw call, cùng frame time).
- N8AO thêm khoảng 232 draw call và 8 program so với `lite`, vì nó dựng lại depth/normal của cảnh.
- **Idle:** ở chế độ `demand`, khi cảnh đứng yên, cả Chrome và Safari đều render 0 khung hình trong 10 s. Điều kiện: đo sau khi hoạt ảnh xuất hiện và lần cập nhật bóng một lần (1,8 s) đã xong. Lần đầu đo với 2 s làm nóng ra 196 khung, chính là đuôi của hoạt ảnh.
- Draw call cao (445–680) chủ yếu vì mỗi node là một mesh riêng (khối + icon), cộng nhãn troika. Hiện chưa thành vấn đề, nhưng là chỗ đầu tiên cần gộp (instancing) nếu số node vượt 200.

## Lỗi hiển thị và cạm bẫy đã gặp

1. **`CameraControls` điều khiển nhầm camera.** Với `<OrthographicCamera makeDefault>` của drei, `CameraControls` đã gắn vào camera phối cảnh mặc định của R3F trước khi camera trực giao được đặt làm mặc định. Hệ quả: xoay và zoom không có tác dụng, và kịch bản đo lúc đầu không xoay camera thật. Sửa bằng `<Canvas orthographic camera={...}>`. M1 phải dùng cách này.
2. **`fitToBox` với camera trực giao** tự xoay camera về mặt hộp gần nhất (azimuth 90°, polar chạm giới hạn) và để zoom bằng 1. Thay bằng zoom tính từ kích thước hình chiếu của bố cục. Nếu M1 cần `fitToBox` khi chọn node (F3.7), phải đặt lại góc sau khi gọi, và thử lại riêng với camera trực giao.
3. **`Outlines screenspace`** dưới camera trực giao tạo ra một mảng màu lớn sai hình. Dùng độ dày theo đơn vị thế giới (0,06–0,09) thì đúng.
4. **Chế độ `demand`:** thay đổi của CameraControls không được vẽ nếu không có khung tiếp theo. Cần `controls.update(0)` và `invalidate()` sau khi đặt camera bằng code.
5. three 0.186 báo `PCFSoftShadowMap has been removed. Using PCFShadowMap instead` (R3F 9.8.2 mặc định `shadows` dùng soft), và `THREE.Clock` đã bị deprecate (R3F dùng nội bộ). Bóng vẫn đúng; M1 nên đặt `shadows="basic"` hoặc kiểu tường minh để tránh cảnh báo.
6. `Line2` (drei `Line`) không có nét gạch chấm. Viền Region đang dùng gạch dài thay cho "gạch chấm" của quy ước AWS; M1 cần shader riêng nếu muốn đúng.
7. Không thấy lỗi thứ tự khay trong suốt (`renderOrder` theo cấp lồng + `depthWrite={false}`). Nhãn troika rõ, dấu tiếng Việt hiển thị đúng ở cả hai chủ đề (`results/screenshot-*-zoom40.png`).
8. Mức `flat` không có khử răng cưa (`antialias: false` và không có SMAA), nên cạnh có răng cưa. Đây là suy luận từ cấu hình, chưa chụp ảnh riêng để kiểm. Nếu `PerformanceMonitor` hạ về `flat`, nên giữ SMAA (chi phí thấp, `lite` gần như bằng `flat`).

## Quy trình đo và sự cố

- Chrome: `node scripts/run-chrome-bench.mjs suite` chạy 13 trang liên tiếp, kết quả POST về dev server (`vite.config.ts`).
- Safari: xem `notes/safari-checklist.md`. Có hai lần Safari mất focus (Teams, Chrome nhảy lên trước), làm hỏng 2 lần đo, và lần đầu có một khung chững 2,7 s. Ba file đó nằm trong `results/invalid/` kèm lý do. Các cấu hình này đã được đo lại khi Safari ở trước, và số liệu khớp với các cấu hình khác.

## Đề xuất cho F3.7

Giữ `full` (N8AO + SMAA + ToneMapping) làm mặc định, giữ `PerformanceMonitor` làm lưới an toàn, và đổi mức hạ cấp từ `flat` sang `lite`. Lý do:
- Trên M1 Pro, mọi mức đều đạt trần vsync, nên chưa có số liệu nào buộc phải hạ.
- Bài đo không đo được dư địa, và M1 Pro là cận dưới của NFR2. Ở `flat` không còn khử răng cưa, nên `lite` là mức hạ hợp lý hơn.
