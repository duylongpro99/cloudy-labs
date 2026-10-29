# Kết quả đo hiệu năng: 200 node qua đường graph

Ngày đo: 2026-10-29. Máy: MacBook Pro M1 Pro. Chrome qua Playwright (`channel: 'chrome'`, ANGLE Metal), Safari là Safari của máy, điều khiển bằng AppleScript từng cấu hình một và giữ ở trước.

Phương pháp giống M0 và [plan thư viện object](../../261028-0230-m2-aws-icon-3d-object-library/notes/perf-results.md): canvas 1280×800, làm nóng 2 s (lượt idle 4 s), đo 10 s, camera xoay 30°/s.

Khác plan trước ở chỗ cảnh **không còn dựng thẳng từ fixture**. `web/src/graph/synthetic-graph.ts` biểu diễn fixture 200 node / 60 cạnh của M0 thành `ResourceGraph` (SG và EIP thành node có cạnh `attached`, 60 cạnh thành route `0.0.0.0/0`). Bench vẽ graph đó qua `graphToScene` → `computeLayout` → `scenePlacements`, tức đúng đường của màn hình live. Cảnh cũng có thêm các thay đổi của plan này: cạnh theo kiểu (route tô màu theo đích, có nhãn CIDR), hoạt ảnh xuất hiện theo id, khay mờ dần.

Bảng đầy đủ: [bench/summary.md](./bench/summary.md). JSON từng lượt: [bench/](./bench/).

## Kết luận

- **Đạt NFR2 và NFR8.** Chrome: mọi cấu hình có p95 9,1–9,4 ms. Safari, mức `full` DPR 2 (điều kiện bắt buộc): p95 17 ms ở cả hai chủ đề.
- Idle: 0 khung hình trong 10 s trên cả hai trình duyệt.
- Draw call ở mức `full` tăng từ 166 lên 189. Phần tăng đến từ cạnh tách thành một `Line` cho mỗi kiểu và từ nhãn CIDR của route. Program giảm từ 24 xuống 23.
- Cả hai trình duyệt vẫn chạm trần vsync (Chrome 120 Hz, Safari 60 Hz), nên bài đo không cho biết còn dư bao nhiêu.
- Safari chỉ đo ba lượt bắt buộc: `full` sáng, `full` tối, idle. Cả ba hợp lệ (max 22 ms và 32 ms, không có khung trên 1 s), không cần đo lại. Mức `lite` và `flat` chỉ đo trên Chrome.

## So với plan thư viện object

| Chỉ số | Plan thư viện object (fixture trực tiếp) | Plan này (graph → adapter → layout) |
|---|---|---|
| Draw call `full` / `lite` / `flat` | 166 / 113 / 110 | 189 / 114 / 111 |
| Triangle `full` / `lite`, `flat` | 211.913 / 203.579 | 212.369 / 203.555 |
| Program `full` / `lite` / `flat` | 24 / 16 / 12 | 23 / 15 / 11 |
| Chrome p95 (mọi cấu hình) | 9,1–10,2 ms | 9,1–9,4 ms |
| Safari p95, `full` DPR 2 | 18 ms | 17 ms |
