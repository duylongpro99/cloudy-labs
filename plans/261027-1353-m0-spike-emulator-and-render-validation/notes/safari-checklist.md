# Checklist đo Safari (Phase 3)

Playwright WebKit không phải Safari thật, nên Safari được chạy bằng Safari của máy. Trang đo tự lưu kết quả qua dev server, nên không phải chép tay.

## Chuẩn bị

1. `cd spikes/m0-render && pnpm dev` (cổng 5173, `--strictPort`). Kiểm tra trước bằng `lsof -i :5173`.
2. Đóng hoặc thu nhỏ các ứng dụng hay tự nhảy lên trước (Teams, Chrome đang có tác vụ). Safari dừng `requestAnimationFrame` khi cửa sổ bị che hoặc mất focus, và lần đo đó sẽ hỏng.
3. Không cần tắt giới hạn 60 fps của Safari. Ngưỡng của A6 là 20 ms, cao hơn khung 16,7 ms.

## Chạy

- Cả bộ (12 cấu hình + idle):
  `open -a Safari "http://localhost:5173/?mode=bench&post=full&theme=light&dpr=1&run=1&suite=1&i=0"`
  Trang tự chuyển qua từng cấu hình. Mỗi cấu hình có 2 s làm nóng và 10 s đo. Khi xong, tiêu đề tab là `SUITE DONE`.
- Một cấu hình: `http://localhost:5173/?mode=bench&post=<full|lite|flat>&theme=<light|dark>&dpr=<1|2>&run=<n>`.
- Idle: `http://localhost:5173/?mode=idle&post=full&theme=light&dpr=2&run=1&warmup=4000`.
- Mỗi lần chạy ghi `results/safari-<post>-<theme>-dpr<d>-run<n>.json`. Trang cũng có link "tải JSON" để dự phòng.
- Có thể giữ Safari ở trước bằng AppleScript (`tell application "Safari" to activate`) và chạy từng cấu hình một. Đó là cách đã dùng sau khi bộ đầy đủ bị gián đoạn.

## Kiểm tra kết quả hợp lệ

- `frames` khoảng 600 (60 Hz × 10 s) và `frameTimeMs.max` dưới khoảng 100 ms. Một khung hình dài hàng giây nghĩa là cửa sổ đã mất focus. Chuyển file đó vào `results/invalid/`, ghi lý do vào `results/invalid/README.txt`, rồi đo lại.
- Lần chạy đầu tiên trong phiên có thể có một khung dài khoảng 2–3 s do biên dịch shader. Đo lại nếu `avgFps` lệch rõ so với các cấu hình khác.
- `node scripts/summarize-results.mjs > results/summary.md` để ra bảng tổng hợp.

## Kết thúc

Dừng dev server, và `lsof -i :5173` không trả về gì.
