# Kiểm tra IMDS của Floci và lỗi mất cổng host sau reset

Ngày 2026-10-28. Floci 2.3.0, Docker Desktop trên macOS arm64, AMI `ami-amazonlinux2023-arm64`, instance profile có role.

## Kết luận

- **IMDS ổn định trong lần đo này.** 21/21 instance có IMDS và trả credential của role (đủ 7 trường), sau 17,8–21,6 giây (trung vị 18,8). Không lần nào chạm mốc timeout 180 giây mà spike M0 gặp một lần. Timeout đó xảy ra ở bước Floci cài `iproute socat curl` qua mạng, nên vẫn có thể gặp lại khi mạng chậm.
- **Phát hiện một lỗi khác, nặng hơn, trong `labctl reset`, và đã sửa.** Reset bằng `compose restart floci` khi còn instance làm cổng `127.0.0.1:4566` treo 2 trên 16 lần, dù container vẫn healthy.

## Nguyên nhân lỗi mất cổng host

Floci tự gắn container của nó vào network của mỗi VPC. Docker events lúc lỗi cho thấy: khi restart, Docker gắn lại Floci vào cả `cloudy-labs_default` lẫn network VPC cũ; ngay sau đó Floci (reconcile lúc khởi động) ngắt và xoá network VPC. Từ trong network compose, Floci vẫn trả 200; chỉ đường chuyển tiếp cổng của Docker Desktop là chết. Phần "Docker Desktop bám vào endpoint đã mất" là suy luận từ hiện tượng, chưa đọc mã nguồn Docker Desktop.

## Sửa

- `stack.recreate_floci()`: `compose rm -s -f floci`, dọn tài nguyên mồ côi, `compose up -d --wait floci`. Container mới chỉ gắn vào network compose. `reset` của Floci dùng hàm này.
- `labctl up`: xoá container Floci đã dừng trước khi dọn mồ côi và khởi động lại; khi Floci healthy trong Docker nhưng cổng host không trả lời, `up` tạo lại container (lối thoát cho người đã bị restart ngoài `labctl`).
- Kiểm tra sức khoẻ qua cổng host gom về `stack.reachable()`; `AwsProvider.health()` dùng lại hàm này.

## Bằng chứng

| Lượt | Reset dùng | Kết quả |
|---|---|---|
| Trước sửa | `compose restart` | 2 lần treo cổng host trên 16 lần reset khi có instance |
| Sau sửa | xoá rồi tạo lại container | 15/15 lần reset xong trong khoảng 5 giây, IMDS 15/15 |

Kiểm thêm: `labctl up` đưa một Floci đang treo cổng về trả 200. 61 test đơn vị và 3 test Docker đạt, ruff sạch, không còn tài nguyên `io.floci.owner=4566`.

## Image Amazon Linux 2023 build sẵn (đã áp dụng theo quyết định của người dùng)

Floci đọc catalog AMI từ khoá cấu hình `floci.services.ec2.image-catalog-path` (mặc định là `ec2/image-catalog.yaml` nhúng trong binary). Script cài của Floci thoát ngay khi image đã có `ip`, `socat`, `curl`.

- `server/src/cloudy_labs/emulator/al2023/Dockerfile`: `amazonlinux:2023` (ghim digest đa kiến trúc) cài sẵn `iproute socat curl ca-certificates openssh-server openssh-clients`.
- `ec2-image-catalog.yaml`: bản sao catalog mặc định của Floci 2.3.0; các mục Amazon Linux 2023 trỏ sang `cloudy-labs/al2023:1-x86_64` hoặc `:1-arm64` theo `architecture`. Compose mount file này và đặt `FLOCI_SERVICES_EC2_IMAGE_CATALOG_PATH`.
- `labctl up` build image còn thiếu với `--platform` tương ứng: arm64 khoảng 30 giây (363 MB), amd64 qua giả lập khoảng 53 giây (250 MB) trên Mac Apple Silicon.

Hai điều chỉnh sau khi thử thật:

- Floci pull image theo kiến trúc của mục catalog, nên một tag chỉ có bản arm64 làm AMI x86_64 hỏng (`pull access denied`). Vì vậy mỗi kiến trúc có tag riêng.
- Image mặc định (cho AMI ID lạ) không có kiến trúc trong catalog và cũng bị pull, nên giữ bản `amazonlinux:2023` gốc. AMI lạ vẫn chạy được nhưng IMDS chậm (khoảng 33 giây).

| Đo ngày 2026-10-28 | Trước | Sau |
|---|---|---|
| IMDS sẵn sàng (instance profile, arm64) | 17,8–21,6 giây, 21/21 | 2,1–2,2 giây, 20/20 |
| AMI x86_64 (`ami-amazonlinux2023`, AMI từ SSM) | không đo | IMDS khoảng 1 giây sau khi container chạy |
| UserData bắt đầu chạy | 45 giây đến 6 phút (spike M0) | 1–2 giây, 3/3 |

64 test đơn vị (thêm test catalog khớp kiến trúc, compose mount đúng đường dẫn, `up` chỉ build image còn thiếu) và 3 test Docker đạt; ruff sạch; không còn tài nguyên Floci sau `down`.

## Bảo trì (đã làm theo trả lời của người dùng)

- `python -m cloudy_labs.emulator.images sync-catalog` sinh lại catalog từ binary Floci đang ghim; bản sinh ra khớp nguyên văn catalog đã chép tay, chỉ khác chú thích đầu file.
- `bump-base` ghim digest `amazonlinux:2023` mới nhất và tăng `AL2023_VERSION` cùng các tag trong catalog (`--force` để chỉ tăng phiên bản). Ngày 2026-10-28 digest đang ghim vẫn là bản mới nhất.
- Test Docker so catalog với bản nhúng trong Floci; test đơn vị kiểm tag Floci ở đầu catalog khớp `compose.yaml` và kiểm logic sinh catalog, nâng phiên bản. 69 test đơn vị đạt, test Docker mới đạt.
