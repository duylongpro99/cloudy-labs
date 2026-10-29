# Floci lùi sang cổng host 4567

Kiểm ngày 2026-10-29, Floci `2.3.0`, compose project `cloudy-labs`, Floci publish `127.0.0.1:4567:4566`, api-tap ở `127.0.0.1:4566` và `127.0.0.1:4568`.

## Cách kiểm

Chạy `spikes/m0-emulators/lab-06-07.sh floci-4567 http://127.0.0.1:4567` (đi thẳng Floci, không qua api-tap), rồi `docker ps`/`docker network ls` theo label `io.floci=aws` và gọi IMDS từ trong container EC2.

## Kết quả

- 36/36 bước trả mã 0.
- `io.floci.owner` vẫn là **`4566`** trên cả container EC2 (`floci-aws-ec2-i-…`) và network VPC (`floci-aws-vpc-4566-us-east-1-vpc-…`). Giá trị này là cổng **trong container** của Floci, không phải cổng host. Vì vậy `orphans.py` không lọc theo `FLOCI_PORT` nữa mà theo hằng số `FLOCI_OWNER = 4566`.
- Instance lên `running`; IMDS trong container trả đúng `instance-id`; UserData đã chạy (`/srv/www/index.html` có mặt sau khoảng 20 giây).
- `PublicIpAddress` là `127.0.0.1`. Cổng host được publish theo hai cách:
  - SSH ngay trên container instance: `floci-aws-ec2-i-<id>` có `0.0.0.0:2200->22/tcp`.
  - Cổng ứng dụng mà security group mở (ở đây 80) qua một container socat riêng `floci-aws-ec2-fwd-i-<id>-80`, `0.0.0.0:30000->80/tcp`. Container này **không** mang label `io.floci.*` (chỉ `floci=true`, `floci_emulator=floci-aws`).
  Collector vì vậy lấy cổng theo tên container (`floci-aws-ec2-i-<id>` và `floci-aws-ec2-fwd-i-<id>-*`) thay vì lọc label `io.floci.resource-id` và dải 30000–30999, và trả dạng `{"22/tcp": 2200, "80/tcp": 30000}`.
- Vì container forwarder không có `io.floci.owner`, bộ dọn mồ côi của M1 bỏ sót nó. `orphans.py` thêm bộ lọc `label=floci_emulator=floci-aws` cho container.
- `PrivateIpAddress` là `10.240.0.11`, ngoài CIDR `10.0.1.0/24`: máy kiểm có mạng Docker trùng `10.0.0.0/16`, đúng điểm 1 của spike. Đây là dữ liệu tốt cho cảnh báo `privateIpOutOfCidr`.

## Kết luận

Không cần phương án dự phòng. Floci đổi cổng host không ảnh hưởng label owner hay EC2.

Ghi chú bên lề (không thuộc M2): Floci publish cổng SSH của instance trên `0.0.0.0`, không phải `127.0.0.1`. Hành vi này có từ M1, ghi lại để xem xét ở NFR7 sau.

## Đi qua api-tap (Phase 1, bước xác minh)

`labctl up` rồi chạy `lab-06-07.sh floci-tap http://127.0.0.1:4566` trong khi `curl -N 127.0.0.1:4568/events` nghe:

- 36/36 bước trả mã 0.
- Kênh SSE nhận đúng **25** sự kiện, bằng số bước ghi của kịch bản (1 `CreateVpc`, 4 `CreateSubnet`, 4 `AssociateRouteTable`, …). Các lệnh `describe-*` và `wait` không sinh sự kiện.
- So 31 file output với lần chạy thẳng Floci ở 4567 trong cùng phiên: giống hệt sau khi bỏ id, IP, thời điểm, `ClientToken` và thứ tự phần tử trong list (Floci trả list theo thứ tự không cố định).
- So với output của spike M0 (`spikes/m0-emulators/out/floci/`): khác thêm ở chỗ bản spike có security group `default` trong `describe-security-groups`; khác này có cả khi chạy thẳng 4567 nên không do api-tap.

## Cập nhật sau review: Floci nghe 4567 cả trong container

Review chỉ ra hằng số `FLOCI_OWNER = 4566` khiến `labctl reset`/`down` có thể xoá instance của một Floci mặc định khác đang chạy trên cùng máy (owner cũng là `4566`). Probe ngày 2026-10-29 với `FLOCI_PORT=4569` cho thấy `io.floci.owner` đi theo cổng Floci nghe trong container. Compose nay đặt `FLOCI_PORT: "4567"`, publish `127.0.0.1:4567:4567`, api-tap trỏ `http://floci:4567`, và `orphans.py` lọc theo `FLOCI_PORT` của config. Container forwarder (không có owner) chỉ bị dọn khi tên của nó chứa id của một instance mang owner của stack này. Stack dựng trước thay đổi này cần `labctl down` bằng bản cũ trước khi cập nhật.
