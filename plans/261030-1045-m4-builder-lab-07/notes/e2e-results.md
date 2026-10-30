# Kiểm thử đầu-cuối M4

Ngày chạy: 2026-10-30. Máy: MacBook Pro M1 Pro, Docker Desktop, aws-cli 2.36.31, Chrome qua Playwright (`channel: 'chrome'`).

## Cách chạy

`uv run pytest -m docker tests/test_builder_e2e_docker.py -s` (thư mục `server/`). Các tiến trình và thư mục tạm giống [M3](../../261029-1525-m3-builder-lab-06/notes/e2e-results.md#cách-chạy). `fixture-lab-06` và `fixture-lab-07` được chép vào thư mục lab tạm.

Script `web/scripts/e2e-builder-lab-07.mjs <run|practice> <out>` dựng Lab 7 bằng chuột trên trang live. Mỗi chế độ chạy sau một lần `labctl start fixture-lab-07`, tức trên mạng mới và không còn key pair hay instance của lượt trước:

- **run**: bấm Run ở mỗi bước.
- **practice**: bật Luyện tập, bấm Chép, rồi chạy đúng chuỗi trên panel bằng `bash -c` trong một môi trường chỉ có `AWS_CONFIG_FILE` (giả lập người học gõ ở terminal).

Kết quả từng bước: [run](./e2e-builder-lab-07-run.json), [practice](./e2e-builder-lab-07-practice.json). Hai file này không có `stdout`, nên không chứa private key (test khẳng định không có `KeyMaterial`).

## Kết quả

| Bước | Run | Luyện tập |
|---|---|---|
| 7 thao tác: SG `web` trong VPC, rule tcp 80 ← `0.0.0.0/0`, rule tcp 22 ← `203.0.113.10/32`, key pair `lab07-key`, instance trong subnet công khai với UserData mặc định, SG `admin`, kéo cạnh `admin` → instance | Cả 7 bước exit 0, phase `done` | Cả 7 lệnh chép ra chạy exit 0 trong shell, panel tự sang `done` |
| `/api/run` | 7 request cho 7 lần bấm Run, không có request nào trước khi bấm | **0 request** |
| Rule 22 ← `0.0.0.0/0` | Form giải thích, Run và Chép bị khoá, không gửi gì | Form giải thích, Chép bị khoá |
| Tải .pem | Tải về `lab07-key.pem`, nội dung là private key | Lệnh `create-key-pair` chạy trong shell; terminal nhận private key |
| Form instance | Tự chọn SG `web`, key pair `lab07-key`, điền UserData của lab | Như Run |
| Gắn `admin` | Lệnh giữ `web` và thêm `admin` vào `--groups`; `web` vẫn gắn | Như Run |
| `labctl check fixture-lab-07` | **6/6 checks passed** | **6/6 checks passed** |
| Thời gian tới `done` | Từ bấm Run: p50 817 ms, max 1321 ms (`create-key-pair`, riêng aws CLI 795 ms) | Từ lúc bắt đầu chạy lệnh: p50 703 ms, max 1159 ms |
| Lỗi trên trang | Không có | Không có |

`web-server-answers` đạt ngay lần check đầu ở cả hai chế độ (`http://127.0.0.1:30000/`), trong giới hạn chờ 60 giây của test.

Test API không qua trình duyệt (`test_run_instances_through_the_api_reaches_the_graph`): tạo SG rồi `run-instances` qua `/api/run`; instance và cạnh `attached:<sg>-><instance>` lên graph trong 5 giây. Ảnh cảnh cuối: [run](./e2e-builder-lab-07-run.png), [practice](./e2e-builder-lab-07-practice.png).

Toàn bộ `pytest -m docker`: **10 passed** trong 154 giây (Lab 6 builder, Lab 7 run và practice, API run-instances, độ trễ, vòng đời stack). Dòng `FAIL vpc-exists` trong log là của test vòng đời, test đó cố ý check một lab chưa dựng.

Câu hỏi còn mở từ M3: Floci từ chối subnet CIDR chồng lấn bằng `InvalidSubnet.Conflict`, giống AWS ([floci-ec2-ops.md](./floci-ec2-ops.md), [emulator-differences.md](../../../docs/emulator-differences.md)).

## Vấn đề gặp khi chạy và cách xử lý

1. **`web-server-answers` trượt sau 60 giây.** UserData cũ chỉ bind IP private của VPC (10.67.1.x). Container socat `floci-aws-ec2-fwd-i-<id>-80` mà Floci tạo cho cổng 80 lại gọi tới địa chỉ của instance trên mạng compose `cloudy-labs_default` (172.19.x), nên bị từ chối kết nối. Instance có ba địa chỉ (bridge 172.17.x, VPC 10.67.x, compose 172.19.x), còn `0.0.0.0:80` đã bị proxy IMDS chiếm. Sửa: UserData bind `python3 -m http.server 80` lên từng địa chỉ IPv4 của instance trừ `lo`. Gợi ý UserData trên form, thông điệp của check và [emulator-differences.md](../../../docs/emulator-differences.md) cũng sửa theo.
2. **Test API ném `StopIteration`.** Test đọc graph khi `labctl start` chưa dựng xong mạng: subnet đã có nhưng chưa thành `subnet-public` vì collector chưa thấy route tới IGW. Sửa: `_wait_for` chờ thêm theo loại node.
3. **Script đếm sai số bước** (chờ 8, thực tế 7 thao tác). Sửa con số trong script và trong test.

## Sửa theo review

Sau [code-review.md](../reports/code-review.md) (lượt docker ở trên chạy sau các sửa này):

- Server từ chối mọi giá trị bắt đầu bằng `file://` hoặc `fileb://`, vì aws CLI sẽ đọc file trên máy chạy lab-server thay cho chuỗi đó. `http(s)://` không cần chặn: aws CLI v2 mặc định không tải URL (`cli_follow_urlparam` tắt).
- Luyện tập không tính tài nguyên trùng tên đã có lúc bấm Chép.
- `/api/run` cho `modify-instance-attribute` collect graph mới trước khi điền `--groups`; collect lỗi thì trả 503 thay vì dùng graph cũ.
- Server từ chối `currentGroups` ở cả tên snake_case.
- Chép bị khoá khi server đã từ chối lệnh (ở cả hai chế độ, như tài liệu ghi).
- Cổng chỉ nhận chữ số ASCII. Mô tả SG theo bộ ký tự của AWS và là ô một dòng. Gắn SG thứ sáu được giải thích trước khi chạy.
- Key của danh sách rule không trùng nữa; nhãn rule đọc đúng `from: null`; URL của .pem được thu hồi sau 60 giây.

## Hạn chế thấy được

- Dòng "đã thấy" trong Luyện tập đếm cả lệnh ghi bị lỗi, vì api-tap không gửi status HTTP về trình duyệt.
- Chép vẫn chuyển sang chờ khi ghi clipboard lỗi. Đây là cố ý: lệnh vẫn hiện để chép tay, và Chrome headless không có clipboard.
- Ở trạng thái lỗi trong Luyện tập không có nút Thử lại; phải sửa form hoặc tắt công tắc.
- Một thuộc tính đã đúng sẵn lúc bấm Chép (ví dụ SG đã gắn) làm Luyện tập báo xong ngay.
- `since` dựa trên `seq` của api-tap, số này đếm lại từ 1 khi api-tap khởi động lại.
- Mới kiểm bằng lab fixture. Khi có Lab 7 thật phải chạy lại test này với lab đó rồi mới đóng M4.
