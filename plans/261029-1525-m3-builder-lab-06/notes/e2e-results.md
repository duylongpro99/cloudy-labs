# Kiểm thử đầu-cuối M3

Ngày chạy: 2026-10-29. Máy: MacBook Pro M1 Pro, Docker Desktop, Floci 2.3.0, aws CLI v2, Chrome qua Playwright (`channel: 'chrome'`).

## Cách chạy

`uv run pytest -m docker tests/test_builder_e2e_docker.py -s` (thư mục `server/`). Test tự làm hết:

| Tiến trình | Cổng | Cách chạy, cách dừng |
|---|---|---|
| Stack compose (api-tap, Floci, moto) | 4566 / 5050 | `labctl up` trong fixture của test, `labctl down` ở cuối dù test đạt hay trượt |
| lab-server | 8730 | luồng uvicorn trong test; test dừng nếu cổng đã bị chiếm |
| Vite dev server | 5174 | dùng lại nếu đang chạy, không thì test tự bật và tắt cả process group |

`CLOUDY_LABS_HOME`, thư mục lab và `AWS_CONFIG_FILE` đều trỏ vào thư mục tạm, nên test không đụng `~/.aws/config` thật. `fixture-lab-06` được chép vào thư mục lab tạm.

Script `web/scripts/e2e-builder-lab-06.mjs` mở trang live và dựng Lab 6 chỉ bằng thao tác chuột: kéo từ palette, kéo tay cầm để nối, bấm nút thuộc tính, điền form, bấm Run. Kết quả từng bước nằm ở [e2e-builder.json](./e2e-builder.json).

## Kết quả

| Bước | Kết quả |
|---|---|
| 20 thao tác: VPC, DNS hostnames, 4 subnet, 2 lần map-public-ip, IGW, attach, EIP, 2 route table, route public → IGW, 2 association public, NAT, route private → NAT, 2 association private | Cả 20 bước exit 0 và tới trạng thái `done`, tức graph mới đã xác nhận thay đổi |
| Không chạy gì trước khi bấm Run | Trước mỗi lần Run không có `/api/run` nào. Tổng cộng 20 request cho 20 lần bấm |
| Lệnh trên panel đúng là lệnh đã chạy | Ở cả 20 bước, chuỗi trên panel trùng với `command` trong phản hồi `/api/run`, tức `shlex.join` của argv mà runner chạy |
| Subnet sai CIDR (`10.99.1.0/24` trong VPC `10.66.0.0/16`) | Form báo "outside", Run bị khoá, không gửi request nào |
| Form VPC | Gợi ý sẵn CIDR của lab |
| Chép lệnh `modify-vpc-attribute` từ panel, chạy lại trong shell không có biến `AWS_*`, chỉ có `AWS_CONFIG_FILE` | exit 0 |
| `labctl check fixture-lab-06` | **8/8 checks passed** |
| Lỗi trên trang trong cả lượt | Không có |
| Run → cảnh đổi (từ lúc bấm Run tới khi phase `done`) | **p50 813 ms, p95 818 ms**, max 822 ms. Riêng aws CLI mất 450–680 ms, phần còn lại là notify hub, collect và vẽ |
| Độ trễ ghi → WebSocket sau khi collector đọc thêm `describe-vpc-attribute` (`tests/test_latency_docker.py`, 20 lần) | p50 196 ms, p95 215 ms, max 236 ms (M2: p95 281 ms; giới hạn NFR3: 2 s) |

Ảnh cảnh cuối: [e2e-builder-lab-06.png](./e2e-builder-lab-06.png).

Kiểm tra trình duyệt với `/ws` và `/api` giả (`web/scripts/check-builder.mjs`, không cần lab-server): 22/22 PASS. Các bước gồm: palette đúng loại; ghost báo được thả khi kéo VPC; form và preview; chỉ gọi một preview sau debounce khi sửa form; không chạy trước khi bấm Run; Esc đóng form; NAT thả lên region bị từ chối và có giải thích; kéo route table sang IGW cho ra `create-route` với `0.0.0.0/0`; nút public IP của subnet đi qua Run → chờ → done; thả subnet ở chủ đề tối. Ảnh: [kéo sáng](./builder-drag-light.png), [form](./builder-form-light.png), [nối](./builder-connect-light.png), [xong](./builder-done-light.png), [kéo tối](./builder-drag-dark.png).

## Vấn đề gặp khi chạy và cách xử lý

Hai lượt đầu trượt vì cách script nhắm điểm trên màn hình, không phải lỗi builder:

1. **Bước 10 (attach IGW)**: tay cầm IGW nằm ngoài khung hoặc dưới panel trên cùng. Camera chỉ đóng khung một lần, nên cảnh lớn dần sẽ tràn ra ngoài. Script bấm "Vừa khung" trước mỗi thao tác, kiểm tra điểm nhắm thật sự nằm trên canvas, và tính điểm đích sau khi đã chọn nguồn.
2. **Bước 18 (route private → NAT)**: bấm vào NAT lại chọn nhầm EIP, vì icon EIP vẽ đè lên NAT. Script đợi NAT `available` qua `/api/graph` và nhắm lệch lên 14 px.

## Hạn chế thấy được

- Camera không tự đóng khung lại khi cảnh lớn lên; người học phải bấm "Vừa khung".
- Icon EIP che một phần NAT, nên khó bấm hay kéo nối tới NAT.
- Object ở cấp region (IGW chưa attach, EIP) có thể nằm dưới panel góc trên bên trái.
- Phần lớn độ trễ Run → cảnh (~0,5 s) là thời gian khởi động aws CLI, không phải collector.
- Mới kiểm bằng lab fixture. Khi có Lab 6 thật phải chạy lại test này với lab đó rồi mới đóng M3.

## Chạy lại sau khi sửa theo review (2026-10-29)

Sau các sửa trong [code-review-m3.md](../reports/code-review-m3.md) (Run chỉ bật khi preview khớp lần sửa cuối, 409 khi bận, `runBlocker`, runner kill process group): `pytest -m docker tests/test_builder_e2e_docker.py` đạt trong 58 giây. 20/20 bước, 20 request `/api/run` cho 20 lần bấm Run, Run → cảnh p50 809 ms, p95 816 ms, max 819 ms, `labctl check` 8/8.
