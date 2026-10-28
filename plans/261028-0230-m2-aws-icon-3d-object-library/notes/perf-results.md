# Kết quả đo hiệu năng: cảnh 200 node với thư viện AWS object

Ngày đo: 2026-10-28. Máy: MacBook Pro M1 Pro. Chrome qua Playwright (`channel: 'chrome'`, ANGLE Metal), Safari là Safari của máy.

Phương pháp giống M0: canvas 1280×800, làm nóng 2 s (lượt idle 4 s), đo 10 s, camera xoay 30°/s. Cảnh là fixture 200 node / 60 cạnh của M0, cộng thêm route table, key pair, SG và EIP gắn trên khối chủ. Bộ đo: `web/src/bench/`, `web/scripts/run-chrome-bench.mjs`, `web/scripts/summarize-bench.mjs`.

Bảng đầy đủ: [bench/summary.md](./bench/summary.md). JSON từng lượt: [bench/](./bench/).

## Kết luận

- **Mọi cấu hình đạt p95 ≤ 20 ms** trên cả hai trình duyệt. Safari `full` DPR 2 (điều kiện bắt buộc): p95 18 ms ở cả hai chủ đề.
- **Draw call ở mức `full` giảm từ 680 xuống 166** nhờ instancing: hai InstancedMesh (đế và glyph) cho mỗi loại tài nguyên.
- Idle: 0 khung hình trong 10 s trên cả hai trình duyệt.
- Cả hai trình duyệt vẫn chạm trần vsync (Chrome 120 Hz, Safari 60 Hz), nên bài đo không cho biết còn dư bao nhiêu.

## So với M0

| Chỉ số | M0 (khối trơn) | M2 (khối có glyph AWS) |
|---|---|---|
| Draw call `full` / `lite` / `flat` | 680 / 448 / 445 | 166 / 113 / 110 |
| Triangle `full` / `lite`, `flat` | 30.373 | 211.913 / 203.579 |
| Program `full` / `lite` / `flat` | 24 / 16 / 12 | 24 / 16 / 12 |
| Chrome p95 (mọi cấu hình) | 9,2–9,4 ms | 9,1–10,2 ms |
| Safari p95, `full` DPR 2 | 17 ms | 18 ms |

Số tam giác tăng khoảng 7 lần do glyph ép đùn, đặc biệt các path có nhiều đường cong (xem [geometry-stats.md](./geometry-stats.md)). Ở 200 node, mức này không ảnh hưởng p95. Đây là chi phí cần theo dõi khi cảnh lớn hơn hoặc khi thêm icon M7. Đòn bẩy đầu tiên là giảm `curveSegments`.

## Safari: các lượt đo không hợp lệ

Chạy cả bộ một lần (`suite=1`) cho 10/12 cấu hình có `frameTimeMs.max` trên 1 s. Đó là dấu hiệu Safari mất focus hoặc bị điều tiết, giống M0. Các cấu hình đó được đo lại từng cái một, giữ Safari ở trước bằng AppleScript. Ba cấu hình cần thêm lượt thứ ba hoặc thứ tư. Các file hỏng nằm trong `bench/invalid/`, kèm lý do trong `bench/invalid/README.txt`.

`safari-lite-light-dpr2-run2` có max 103 ms, 592 khung hình, p95 18 ms. Chỉ có một khung dài, hơi vượt mốc 100 ms của checklist. Lượt này vẫn được giữ.

## Bevel cho glyph

Không bật. Bài đo chạm trần vsync nên không biết còn dư bao nhiêu, và bevel sẽ làm số tam giác của glyph tăng thêm vài lần. Hình đã đủ đọc khi không có bevel (xem [object-design.md](./object-design.md)).
