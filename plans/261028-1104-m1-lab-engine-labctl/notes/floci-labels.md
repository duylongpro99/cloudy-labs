# Label tài nguyên Floci tạo ra

Kiểm ngày 2026-10-28, Floci `2.3.0`, compose project `cloudy-labs`. Tạo một VPC `10.77.0.0/16`, một subnet và một instance `t3.micro`, rồi `docker inspect`.

## Kết quả

- **Container EC2** `floci-aws-ec2-i-<id>`: `io.floci=aws`, `io.floci.owner=4566`, `io.floci.service=ec2`, `io.floci.resource-id=i-<id>`, `io.floci.region=us-east-1`.
- **Network VPC** `floci-aws-vpc-4566-us-east-1-vpc-<id>`: `io.floci=aws`, `io.floci.owner=4566`, `io.floci.component=vpc-network`.
- **Volume**: không có ở lần thử này. Báo cáo M0 thấy `floci-aws-ec2-volumes` và container `floci-aws-ec2-volume-helper` khi có EBS; bộ lọc theo label phủ luôn các thứ đó.
- **Container `floci` của compose không mang `io.floci.owner`**, nên lọc theo label không bao giờ chọn nhầm chính nó.

Giá trị owner là **cổng host của Floci (`4566`)**, không phải tên project. Bộ lọc dùng `label=io.floci.owner=4566` cộng `label=io.floci=aws`.

## Phát hiện thêm: thứ tự khi tắt

Container EC2 được gắn vào cả network `cloudy-labs_default` của compose. Vì vậy `docker compose down -v` báo `Network cloudy-labs_default Resource is still in use`, trả mã 125 và để lại network đó.

Thứ tự đúng cho `labctl down`: `compose stop` → xoá container mồ côi → `compose down -v` → xoá network và volume mồ côi.

## Rủi ro đã chấp nhận

Một Floci khác từng chạy trên cổng 4566 (ví dụ container `floci` cũ của người dùng) cũng gắn `owner=4566`. Tài nguyên đó cũng là mồ côi khi stack này giữ cổng 4566, nên dọn chung là đúng. labctl không bao giờ đụng tới container Floci đó, chỉ đụng tài nguyên nó sinh ra.
