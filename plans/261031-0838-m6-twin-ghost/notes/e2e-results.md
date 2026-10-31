# M6: kết quả kiểm thử đầu-cuối

- Ngày: 2026-10-31
- Môi trường: macOS, stack của `labctl up` (Floci + api-tap trên Docker), fixture `fixture-lab-06` và `fixture-lab-07`.
- Test: `server/tests/test_twin_docker.py` (đánh dấu `docker`). Chạy 3 lần liên tiếp đều đạt (2 test, khoảng 48 giây mỗi lần).

```bash
cd server && uv run pytest -m docker tests/test_twin_docker.py -v -s
```

## Số đo

Mỗi số là khoảng giá trị qua 3 lần chạy. "Trung vị" là trung vị của 5 lần đo trong một lần chạy.

| Đại lượng | Kết quả |
|---|---|
| `aws ec2 create-vpc` đến node VPC trong tin `graph` | trung vị 98–103 ms, lớn nhất 162 ms |
| Lệnh ghi cuối cùng (`modify-vpc-attribute` bật DNS hostnames) đến lúc ghost VPC biến mất khỏi tin `twin` | trung vị 354–383 ms, lớn nhất 401 ms |
| boto3 `create_subnet` qua profile `lab` đến node subnet trong tin `graph` | trung vị 193–219 ms, lớn nhất 239 ms |
| Một lượt check `fixture-lab-06` (trung vị 5 lượt) | 262–300 ms |
| Một lượt check `fixture-lab-07` (trung vị 5 lượt) | 211–225 ms |
| Lượt check lab-server ghi vào `check_runs` trong một lượt làm lab 06 | 21 lượt, gồm 5 vòng tạo rồi xoá VPC để đo |
| Lượt check lab-server ghi vào `check_runs` trong một lượt làm lab 07 | 8 lượt |
| `labctl reset` đến tin `twin` của attempt mới (đủ ghost, không check nào đạt) | 3,4–3,8 giây, phần lớn là thời gian xoá emulator |
| Lab 07: lệnh ghi cuối đến lúc `web-server-answers` đạt | 0,3–0,4 giây, không có tin `graph` nào trong khoảng này |

Đo lại một lần sau khi sửa theo review (mỗi lượt check dùng một boto3 session riêng): graph trung vị 110 ms; ghost VPC trung vị 501 ms (lớn nhất 513 ms); subnet boto3 trung vị 198 ms; một lượt check lab 06 là 398 ms, lab 07 là 360 ms; `check_runs` là 23 (lab 06) và 7 (lab 07); reset tới twin mới 1,5 giây. Thời gian tăng khoảng 100 ms mỗi lượt check là do tạo session mới, đổi lại tránh dùng chung session mặc định với collector ở hai thread. Mọi số vẫn trong giới hạn của tiêu chí.

Ghost VPC của Lab 6 chỉ mất khi cả `vpc-exists` và `vpc-dns-hostnames` đều đạt, vì node gắn khi **mọi** check nó khai báo đều qua. Nếu đo từ `create-vpc`, ghost sẽ còn mãi cho tới khi bật DNS hostnames. Vì vậy độ trễ ghost được đo từ lệnh ghi hoàn tất điều kiện.

`check_runs` chỉ được ghi khi kết quả đổi (`record_if_changed`). Các lượt chạy theo nhịp poll mà kết quả giữ nguyên thì không ghi thêm dòng nào.

## Bench web

`ghosts20` (cảnh synthetic 200 node cộng thêm 20 ghost) đạt 120,1 fps, p95 8,6 ms, 211 draw call. Baseline không có ghost là 119,86 fps với 189 draw call. Khi cảnh đứng yên, bench không render frame nào.

## Kiểm tay trên trình duyệt

Kiểm trên dữ liệu thật với `labctl serve` và Vite dev server, cửa sổ 1272×868, cả theme sáng lẫn tối.

- Ghost của AZ, subnet, NAT, `rt-private` và EIP vẽ mờ với viền nét đứt. Nhãn của ghost có chữ "mục tiêu". Node VPC thật có dấu đạt.
- Panel check hiện đủ ba trạng thái Đạt / Chưa đạt / Đang chờ, gom theo task.
- Bấm `subnets-two-azs` tô sáng các subnet thật mà check đó trả về, cùng các ghost subnet đang chờ check đó. Các tray khác bị làm mờ. Bấm lại hoặc nhấn Esc thì bỏ chọn.
- Công tắc "Mục tiêu: hiện/ẩn" ẩn mọi ghost và xếp lại layout; dấu đạt vẫn còn.
- Chạy `labctl reset` trong lúc trang đang mở: panel về 0/8, cảnh chỉ còn ghost, không cần tải lại trang.

Ảnh chụp:
- [check-highlight-dark.jpg](check-highlight-dark.jpg): tô sáng `subnets-two-azs`, theme tối, panel đã gập.
- [check-highlight-light.jpg](check-highlight-light.jpg): tô sáng, theme sáng.
- [ghosts-hidden-light.jpg](ghosts-hidden-light.jpg): ghost đã ẩn.
- [after-reset-light.jpg](after-reset-light.jpg): sau `labctl reset`, 0/8, chỉ còn ghost.

### Sửa UX phát hiện khi kiểm tay

- **Panel check gập được.** Khi mở hết, danh sách che gần nửa cảnh ở cửa sổ 1272×868. Panel giờ là `<details>`, dòng tóm tắt "Kiểm tra · N/M đạt" luôn hiện, danh sách cuộn trong khung cao tối đa 40vh.
- **Tiêu đề "lần làm N" cũ sau `reset`.** `useLab` trước đây chỉ tải lại khi cửa sổ được focus. Giờ hook tải lại mỗi khi lab hoặc attempt trong tin `twin` đổi.

## Đối chiếu tiêu chí

| # | Tiêu chí | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Schema `target` validate bằng pydantic; `target` sai thì báo lỗi rõ | Đạt | `test_schema.py`: các ca lỗi gồm trùng id, parent không có, sai chỗ lồng, check không có, thiếu check, AZ có check, id sai pattern, trường thừa |
| 2 | Sau `start`, đủ ghost và mọi check chưa đạt | Đạt | Docker test lab 06 (attempt mới: đủ ghost, không check nào đạt). Với lab 07, phần do `setup` dựng sẵn được tính là đã đạt qua `network-ready`, đúng thiết kế. Có ảnh `after-reset-light.jpg` |
| 3 | Node thật hiện ≤ 2 giây sau lệnh CLI; ghost mất khi check qua mà không cần `labctl check` | Đạt | Graph: trung vị khoảng 100 ms. Ghost: trung vị khoảng 370 ms. TwinRunner tự chạy check khi graph đổi |
| 4 | Có test chứng minh tài nguyên tạo bằng SDK hiện trong ≤ 2 giây | Đạt | Docker test: 4 subnet tạo bằng boto3, trung vị khoảng 200 ms |
| 5 | Bấm check tô sáng đúng `resourceIds` và ghost khai báo check đó; bấm lại thì bỏ | Đạt | `highlight.test.ts`, `check-panel.test.tsx`, kiểm tay và ảnh chụp |
| 6 | `labctl reset` khi web đang mở: chỉ còn ghost, check về chưa đạt, không cần tải lại | Đạt | Docker test (attempt mới qua `/ws`), kiểm tay, `after-reset-light.jpg` |
| 7 | Làm xong fixture bằng terminal thì `labctl check` đạt và không còn ghost | Đạt | Docker test cả lab 06 và lab 07: `main(["check"]) == 0` và `ghosts == []` |
| 8 | Unit test cho việc gắn ghost và cho việc chỉ ghi progress khi đổi; lab không có `target` chạy như trước | Đạt | `test_twin_binding.py`, `test_progress.py::test_record_if_changed_skips_repeats_within_an_attempt`. `target` mặc định rỗng (`test_target_nests_like_the_collector`). Bộ test cũ của các lab không có `target` vẫn qua |
| + | `web-server-answers` của lab 07 chuyển trạng thái khi UserData xong mà graph không đổi | Đạt | Docker test lab 07: đạt sau 0,3–0,4 giây, 0 tin `graph` trong khoảng đó (check chạy lại ở nhịp poll) |
| + | Từ lúc tài nguyên hiện trong cảnh đến lúc ghost đặc ≤ 3 giây | Đạt | Tối đa 513 ms tính từ lệnh ghi, nên khoảng từ lúc node hiện tới lúc ghost đặc còn ngắn hơn |

## Sửa sau review

Review code không có mục Critical hay High. Đã sửa cả năm mục, mỗi mục có test:

- **Badge SG và EIP đã gắn không có dấu đạt** (ảnh hưởng tiêu chí 3). Badge giờ có dấu đạt riêng. Chưa kiểm lại bằng mắt trên trình duyệt; mới có test dữ liệu cho `mergeTwin` và `scenePlacements`.
- **Một lệnh describe bị timeout bị tính là check trượt và ghi vào progress.** Giờ lượt đó giữ nguyên kết quả cũ, không ghi gì, và nhịp poll sau chạy lại.
- Một nhịp poll đến giữa lúc collect bị mất.
- Ẩn ghost rồi chọn một check không trả id nào thì cả cảnh bị làm mờ.
- Thứ tự tắt server: hub dừng trước twin runner.

## Giới hạn đã biết

- Khi tô sáng, chỉ tray bị làm mờ. Object nằm trong tray bị làm mờ không mờ theo.
- `reset` xoá emulator trước rồi mới mở attempt mới. Vì vậy ngay sau `reset` có thể thoáng thấy tin `twin` mang số attempt cũ; nhịp poll kế tiếp sẽ sửa lại.
- Ghost của một node còn hiện cho tới khi **mọi** check nó khai báo đều qua. Ví dụ VPC của lab 06 cần cả DNS hostnames. Tác giả lab nên chỉ khai báo những check thật sự xác nhận node đó.
- Mới kiểm với lab fixture. Lab 6 và 7 thật chưa có.
