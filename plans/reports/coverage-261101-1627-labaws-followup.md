# Kết quả ba bước sau khi scout lab labaws

Báo cáo này tiếp nối `coverage-261101-1508-labaws-real-labs.md`. Ba bước đã làm theo thứ tự đề xuất: sửa công cụ coverage, thêm các kind còn thiếu, rồi viết hai lab thật và chạy chúng đầu-cuối trên Floci.

## Bước 1: công cụ coverage

- Lệnh CLI không trùng tên API (`cloudformation deploy`, `ecr get-login-password`, `codeartifact login`, `logs tail`…) giờ được quy về API mà nó thật sự gọi. `rds generate-db-auth-token` và `eks get-token` ký token cục bộ nên không còn bị tính là gọi API.
- Tên tài nguyên trong phần chữ được phép chen một từ tiếng Anh.
- Từ đơn chung chung ("key", "api") chỉ tính khi trang đã cho thấy service của nó.
- Thao tác console có thể gọi một API mà Floci thiếu (ví dụ "Flush entire cache") giờ hiện trong danh sách cần review. Một API đã được emulate của bất kỳ service nào được nhắc tới đều được coi là API mà nút bấm đó muốn gọi, nên nút "Launch instances" là `RunInstances` của EC2, không phải `LaunchInstances` của Auto Scaling.
- Lab-001, lab-020 và lab-900 đều không còn là bản nháp.

## Bước 2: registry

- Thêm 5 kind mới:
  - CloudFront: cache policy, origin request policy và origin access control.
  - API Gateway: API key và usage plan.
- Mở rộng 5 kind có sẵn:
  - Log group thêm log stream và các op ghi log.
  - Global Accelerator thêm listener và endpoint group.
  - TGW route table thêm propagation và route tĩnh.
  - IAM user thêm access key: chỉ id và trạng thái, không bao giờ có secret.
  - CloudFormation stack thêm change set.
- Fixture của collector đã được ghi lại và golden file đã được tạo lại.
- Contract test trên Floci qua 110/110.
- `docs/coverage.md` đã được tạo lại.

## Bước 3: hai lab chạy đầu-cuối

| Lab | Kết quả `labctl check` | Ghost | Ghi chú |
|-----|------------------------|-------|---------|
| lab-93 (SQS + DLQ + redrive) | 5/5 | 2/2 node gắn đúng | Floci chuyển message sang DLQ sau `maxReceiveCount` lần nhận; `StartMessageMoveTask` chạy được. |
| lab-62 (metric filter + alarm) | 8/8 | 4/4 node gắn đúng | Metric filter tạo datapoint, alarm chuyển sang ALARM sau khoảng một phút. |

- Task và check được viết bằng lời của chúng tôi. Hai file `lab.yaml` và `checks.py` của mỗi lab không chia sẻ chuỗi 8 từ nào với nội dung lab.
- Ở mỗi chặng của lab, check đều cho đúng kết quả đạt hoặc chưa đạt.
- Hai điểm học được khi viết lab:
  - Ghost gắn vào id đứng đầu theo thứ tự tên, không theo thứ tự trong `resource_ids`. Vì vậy với lab-93, node DLQ phải được khai báo trước. `docs/labctl.md` đã được sửa cho đúng.
  - Floci không có `DescribeAlarmHistory`, nên check "alarm đã kêu" dựa vào chính metric.

## Kiểm thử

- Server: 942 test qua, ruff sạch.
- Web: 615 test qua, typecheck sạch.
- Test `test_leak_check_finds_copied_text_without_printing_it` chỉ lỗi trên máy này. Lý do là nội dung lab vừa scout (bị gitignore) có chung một số thành ngữ AWS với file được theo dõi, ví dụ lệnh curl IMDSv2 và filter của IGW. Code không gây ra lỗi này.

## Quyết định sau báo cáo

- Lab-05 (STS) không lưu. Nếu sau này cần một lab bị chặn vì liên quan tới credential, có thể dựng một sandbox riêng để lưu nó.
- Lệnh dọn dẹp lỗi được đánh dấu `--optional`: dòng 285 của lab-065 (waiter không tồn tại) và dòng 491 của dva-lab-102 (`DeletePackageVersions`). Cả hai lab chuyển từ `gap`/`blocked` sang `ready-with-caveats`. Các dòng chưa nhận diện còn lại của hai lab đều là nhận nhầm ("VPC attachment" đã có `tgw-attachment`, "package version" bị gán nhầm sang IoT) nên được accept.
- Không giữ các thư mục lab chỉ dùng để scout: 23 thư mục đã bị xoá, chỉ giữ lab-62 và lab-93 vì hai lab này đã có `lab.yaml` và `checks.py`. Vì vậy các đường dẫn `labs/.../content/lab.md` trong các báo cáo scout không còn tồn tại, và quyết định `--optional` ở trên không còn được lưu lại. Sau khi xoá, `test_lab_content.py` qua hết và `check-content-leak.py` không tìm thấy nội dung lab trong file được theo dõi.
- Commit theo từng bước.
