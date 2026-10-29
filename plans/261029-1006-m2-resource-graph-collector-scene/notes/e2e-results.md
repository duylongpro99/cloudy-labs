# Kiểm thử đầu-cuối M2

Ngày chạy: 2026-10-29. Máy: MacBook Pro M1 Pro, Docker Desktop, Floci 2.3.0, Chrome qua Playwright (`channel: 'chrome'`).

## Tiến trình

| Tiến trình | Cổng | Cách chạy, cách dừng |
|---|---|---|
| Stack compose `cloudy-labs` (api-tap, Floci, moto) | 4566, 4568 / 4567 (Floci nghe 4567 cả trong container) / 5050 | `labctl up` từ trước; `labctl down` khi xong |
| Vite dev server (`pnpm dev`, có `BENCH_RESULTS_DIR` trỏ về `notes/bench/`) | 5174 | tác vụ nền của phiên; dừng khi xong |
| `labctl serve` | 8730 | tiến trình con của script kiểm thử, dừng bằng SIGINT ở cuối mỗi bước (PID đổi giữa hai lần chạy vì có bước tắt rồi bật lại) |

Script kiểm thử (không commit, nằm ở scratchpad của phiên) mở trang live trong Chrome, cài một bộ đếm ghi lại mọi trạng thái kết nối (`#connection-state[data-state]`) mà trang đi qua, rồi chạy lần lượt các bước dưới đây.

## Kết quả

Bảng dưới là lượt chạy lại sau khi sửa các mục của [review](../reports/code-review-m2.md#xử-lý-2026-10-29). Lượt trước review có cùng kết quả, trừ dòng reset (xem chú thích ở dòng đó).

| Bước | Kết quả |
|---|---|
| Reset emulator khi trang đang mở. Dùng `stack.recreate_floci()`, đúng bước emulator của `labctl reset`, vì repo chưa có lab nào để gọi `labctl reset <lab>` | Cảnh về Region mới, không tải lại trang. Graph sau reset có 11 node: Region, VPC mặc định của Floci với 3 AZ và 3 subnet public, IGW, route table và SG mặc định. "Region trống" trong plan nghĩa là trạng thái mới của Floci, vốn có VPC mặc định. Lượt này trang **không** hiện `emulator-down`: tạo lại Floci mất khoảng 1,4 s và cổng 4567 chỉ đóng chừng 0,5 s (đo bằng `curl` mỗi 100 ms), ngắn hơn chu kỳ poll 5 s. Lượt trước review có hiện `emulator-down`, nhưng là do timeout cũng bị tính là "down", chính là lỗi M1 mà review chỉ ra. Khi poll rơi đúng lúc cổng đóng (đo riêng với `serve`), graph chuyển `emulator-down` khoảng 1 s rồi về `ok` 11 node |
| `eval "$(labctl env)"` rồi `lab-06-07.sh floci http://127.0.0.1:4566` (qua api-tap) | Không bước nào lỗi (không có dòng `FAIL`/`rc≠0`). Chạy riêng: 36 bước, 0 lỗi, 21,8 s. Trong lượt có Chrome mở, một lần máy khựng 128 s giữa hai bước (ngoài lệnh `aws`, cùng lúc trang tải chậm hơn 30 s), không lặp lại khi chạy riêng. Graph cuối: 2 VPC (lab + mặc định), 5 subnet public (2 của lab + 3 mặc định), 2 private, 2 IGW, 1 NAT có 1 EIP, 4 route table, 3 SG, 1 key pair, 1 instance |
| Đối chiếu bằng mắt với sơ đồ Lab 6 + 7 | Khớp: `lab06-vpc` có 2 AZ, mỗi AZ một subnet public và một private; NAT và instance `lab07-web` nằm trong subnet public `us-east-1a`; route `0.0.0.0/0` của `lab06-rt-public` tới IGW, của `lab06-rt-private` tới NAT; key pair nối tới instance. Ảnh: [sáng](./e2e-lab-06-07-light.png), [tối](./e2e-lab-06-07-dark.png) |
| Tắt `serve` khi web đang mở, rồi bật lại | Trang chuyển sang `disconnected`, tự nối lại về `live` khi `serve` chạy lại, instance vẫn hiện đủ (scale 1) |
| Lỗi trên trang trong cả lượt | Không có |
| Độ trễ ghi → WebSocket (`uv run pytest -m docker tests/test_latency_docker.py -s`, 20 lần) | **p50 233 ms, p95 281 ms**, max 301 ms (giới hạn NFR3: 2 s) |

Kiểm tra trình duyệt tự động với WebSocket giả (`web/scripts/check-live.mjs`, không cần lab-server): 12/12 PASS, gồm chỉ id mới chạy hoạt ảnh, tiến độ hoạt ảnh giữ nguyên khi graph đổi giữa chừng, hoạt ảnh xoá, hạt "lệnh bay" xuất hiện rồi biến mất, 0 khung hình trong 10 s idle, bấm instance mở đúng panel có cảnh báo, panel báo đã xoá, Esc đóng panel. Ảnh: [live sáng](./live-light.png), [live tối](./live-dark.png), [panel](./live-panel-light.png), [lệnh bay](./live-api-fly-light.png).

## Hạn chế thấy được

- **Nhãn chồng nhau khi hai khối đứng sát:** trong ảnh Lab 6 + 7, nhãn `lab06-rt-private` dính vào id của route table chính đứng cạnh. Nhãn của khối lá chưa được cắt hay né nhau (nhãn khay đã được cắt theo bề rộng khay). Để lại cho M3, khi builder cần bố cục chi tiết hơn.
- `labctl reset <lab>` chưa chạy được trọn vẹn vì chưa có lab; bước emulator của nó đã được kiểm như trên.
- **Reset thường không hiện `emulator-down`** (xem dòng reset ở trên). Phase 06 ghi "cảnh qua trạng thái `emulator-down` rồi về Region trống"; phần "về Region trống, không tải lại trang" đạt, còn trạng thái trung gian chỉ hiện khi Floci vắng mặt lâu hơn một chu kỳ poll (ví dụ `labctl down`). Không thêm cơ chế báo riêng từ `labctl reset` sang `serve` vì hai tiến trình không nói chuyện với nhau và mục tiêu chính đã đạt.

## Đối chiếu Success Criteria

| Tiêu chí | Kết quả |
|---|---|
| `uv run pytest` xanh không cần Docker; `pnpm test`, `pnpm typecheck` xanh | Đạt: 146 passed; web 97 passed (10 file); typecheck sạch; `pnpm build` thành công |
| `uv run pytest -m docker` xanh, graph cuối khớp cấu trúc, `down` không để lại mồ côi | Đạt: 6 passed (gồm test lab 6 + 7 qua 4566 và test vòng đời có `down`) |
| Độ trễ p95 ≤ 2 s trên 20 lần đo (NFR3) | Đạt: p95 281 ms |
| Bench 200 node qua graph → adapter → layout, p95 ≤ 20 ms ở hai chủ đề trên Chrome và Safari (NFR2) | Đạt: Chrome 9,1–9,4 ms, Safari `full` DPR 2 17 ms cả hai chủ đề ([perf-results.md](./perf-results.md)) |
| Kiểm tra trình duyệt tự động: hoạt ảnh theo id, giữ tiến độ, hoạt ảnh xoá, bấm mở panel | Đạt: `check-live.mjs` 12/12 |
| Cổng mới chỉ bind `127.0.0.1` (NFR7); phụ thuộc mới có giấy phép tương thích MIT | Đạt: 4566, 4567, 4568 (compose), 8730 (`serve`), 5174 (Vite, nay đặt `host: '127.0.0.1'`). Giấy phép FastAPI, uvicorn, websockets và image Python đã ghi vào tóm tắt giấy phép ở Phase 3. Ngoài phạm vi: cổng SSH và cổng ứng dụng của instance do Floci publish trên `0.0.0.0` (có từ M1, xem [floci-port-move.md](./floci-port-move.md)) |
| Web không gọi emulator trực tiếp (NFR4) | Đạt: không có `:4566`/`:4567` trong `web/src` |
