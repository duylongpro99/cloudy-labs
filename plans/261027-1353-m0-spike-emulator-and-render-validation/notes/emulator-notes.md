# Ghi chú emulator (Phase 1 + 2), 2026-10-27

Ghi chú thô, sẽ được tổng hợp vào báo cáo spike ở Phase 5. Mọi đường dẫn tính từ gốc repo.

## Phiên bản đã ghim

| Thành phần | Tag | Digest (index đa kiến trúc) | arm64 |
|---|---|---|---|
| Floci | `floci/floci:2.3.0` | `sha256:e0b292df4dc9559b7b1bf4f51bdda4bb8e269276236438cd03cae661260ea8a9` | Có, chạy native |
| MiniStack | `ministackorg/ministack:1.5.33` | `sha256:b58186186515a372798ccf0ca9975c295db219b5a811975337d6967b968e07b4` | Có, chạy native |
| moto | `moto[server]==5.2.4` (PyPI, Apache-2.0) | lockfile `spikes/m0-moto/uv.lock` | Python thuần |

Docker Hub không có repo `floci-io/floci`; image chính thức nằm ở `floci/floci` (README tag 2.3.0 xác nhận). Floci còn có tag `nightly-*` hằng ngày, không dùng.

## Lệch so với plan

- **moto chạy ở cổng 5050 thay vì 5000.** Cổng 5000 bị AirPlay Receiver của macOS (ControlCenter, PID 611) chiếm. Đây là tiến trình của hệ điều hành, không phải tiến trình spike cũ, nên không dừng nó. M1 không nên dùng cổng 5000 mặc định cho moto trên macOS.
- **Instance type `t4g.micro` thay vì `t3.micro`.** Floci trả `InvalidParameterValue` khi AMI arm64 đi với `t3.micro`, giống AWS thật. Bằng chứng: `spikes/m0-emulators/out/floci-default-config/26-run-instances.err`.
- Thêm các script không có trong danh sách file của plan nhưng cần cho bước 7 và 8: `reset-by-api.sh`, `api-tap-compare.sh`, `api-tap-latency.py`.

## Lab 6 + 7: kết quả chạy

Cả hai backend chạy đủ 36 bước, không bước nào lỗi (`out/<backend>/*.rc`). Mỗi lệnh CLI mất khoảng 0,5 giây, phần lớn là thời gian khởi động AWS CLI chứ không phải emulator (boto3 đo trực tiếp: `DescribeVpcs` p50 1,8 ms trên Floci).

Ma trận trường: `spikes/m0-emulators/out/field-matrix.md`.

| Tài nguyên | Floci | MiniStack |
|---|---|---|
| VPC, AZ, Subnet, IGW, Route Table, SG, Key Pair | đủ, đúng | đủ, đúng |
| NAT Gateway | đủ, đúng (`NatGatewayAddresses` có `PublicIp` + `AllocationId`) | **thiếu `NatGatewayAddresses`** (mảng rỗng dù đã truyền `--allocation-id`) |
| Instance `PrivateIpAddress` | **sai** khi CIDR VPC trùng mạng Docker (xem dưới); đúng khi không trùng | **sai**: `10.0.146.90` nằm trong VPC nhưng ngoài subnet `10.0.1.0/24` |
| Instance `PublicIpAddress` | `127.0.0.1` (Docker Desktop không định tuyến IP container) | IP công khai giả (`54.226.x.x`) |
| `wait instance-running` | ~15 giây (container thật) | tức thì (chỉ là bản ghi) |

### Floci thay CIDR khi trùng mạng Docker

Floci tạo một Docker network cho mỗi VPC. Nếu CIDR khai báo trùng một mạng Docker có sẵn trên máy, Floci âm thầm đổi sang dải dự phòng `10.240.0.0/16` và ghi WARN. Khi đó `describe-*` vẫn báo CIDR khai báo (`10.0.0.0/16`), nhưng IP private của instance thuộc dải thay thế (`10.240.0.11`).

- Trên máy này, mạng `ingress` (Docker Swarm, `10.0.0.0/24`) và `ecommerce-net` (`10.0.1.0/24`) của người dùng gây ra trùng lặp. Đây là tình huống bình thường trên máy người học.
- Kiểm chứng: VPC `10.50.0.0/16` không trùng thì Floci báo đúng `10.50.1.10` (`out/floci/side-test-non-overlapping-cidr.txt`).
- `FLOCI_SERVICES_EC2_AWS_FAITHFUL_PRIVATE_IP=true` không sửa được trường hợp này, vì subnet đã bị thay dải trước khi cấp IP.
- Hệ quả cho M1–M2: lab engine nên kiểm tra trước (preflight) xem CIDR của lab có trùng mạng Docker nào không và cảnh báo. Collector nên lấy CIDR từ `describe-*` để vẽ, không suy ra từ IP instance.

### Hành vi EC2 của Floci

- **UserData chạy được, nhưng web server bind `0.0.0.0:80` bị lỗi `Address already in use`.** Floci cài một proxy IMDS lắng nghe `169.254.169.254:80` bên trong instance. Workaround trong lab: bind vào IP private lấy từ IMDS (`local-ipv4`). Với cách này, `curl localhost:30000` trả HTTP 200 với nội dung UserData (`out/floci-default-config/` cho lần chạy đầu, `out/floci/curl-port-80.txt`).
- **Thời gian khởi động không ổn định.** Floci cài gói (sshd, phụ thuộc của proxy IMDS) qua mạng trong mỗi lần khởi động. Lần đầu UserData xong sau khoảng 45 giây. Lần thứ hai, bước cài proxy IMDS timeout sau 180 giây, nên instance **không có IMDS**, và UserData xong sau khoảng 6 phút. Lab 7/8 cần timeout checker dài, và Lab 8 (đọc credential qua IMDS) có rủi ro thật. Cần theo dõi ở M1.
- **Lần đầu public một cổng ứng dụng, Floci pull `alpine/socat` không kèm tag, nên Docker kéo về toàn bộ 23 tag** (~2 phút). Lab engine nên pull sẵn `alpine/socat:latest` lúc cài đặt.
- Cổng ứng dụng được public qua sidecar socat ở dải 30000–30999 của host; SSH ở 2200–2299.
- `ReservationId` thay đổi sau mỗi lần gọi `describe-instances` (gọi trực tiếp hai lần liên tiếp, không qua proxy). Collector không được dùng `ReservationId` làm khoá.

### Reset

| Cách | Floci | MiniStack |
|---|---|---|
| `docker compose restart` tới khi health OK (persistence tắt) | 1,1 s | 0,7 s |
| Xoá từng tài nguyên bằng API (`reset-by-api.sh`, ~20 lệnh CLI) | 19,3 s (gồm chờ instance terminate) | 10,6 s |
| Endpoint reset có sẵn | không thấy trong README | `POST /_ministack/reset` |

**Tài nguyên mồ côi:** sau `docker compose down -v`, Floci để lại container EC2, `floci-aws-ec2-volume-helper`, các network `floci-aws-vpc-*` và volume `floci-aws-ec2-volumes` (`out/floci/orphans-after-compose-down.txt`). Restart ở chế độ memory cũng xoá trạng thái API mà không dừng container EC2 đang chạy. Lab engine phải dọn theo label `io.floci.owner=<port>` sau mỗi lần reset hoặc tắt. Đây là đầu vào trực tiếp cho quy tắc quản lý tiến trình.

## api-tap

- Proxy stdlib Python giữ nguyên header `Host`, chuyển tiếp nguyên header và body.
- 10 lệnh đọc (9 `describe-*` + `sts get-caller-identity`) qua proxy cho kết quả **giống hệt** gọi trực tiếp, trừ `ReservationId` (do Floci, xem trên). Ghi EC2 (tạo/xoá SG, ingress, tag) và S3 (tạo bucket, upload, tải về khớp nội dung, xoá) đều thành công. Bằng chứng: `out/api-tap/compare.txt`.
- **SigV4 còn nguyên** khi kiểm với moto, vốn kiểm chữ ký thật: qua proxy, `alice/tap` thành công, `bob/tap` bị `AccessDenied`. Đối chứng âm: khi sửa `Host` thành `localhost:5050`, moto trả `403 SignatureDoesNotMatch` (`spikes/m0-moto/out/api-tap-sigv4.txt`).
- Độ trễ thêm (boto3, 200 lần `DescribeVpcs`): p50 +2,8 ms, p95 +5,3 ms (`out/api-tap/latency.txt`). Proxy mở kết nối upstream mới cho mỗi request; nếu cần có thể dùng keep-alive.
- Hạn chế: log không nhận ra action của S3 REST (in ra `?`). M2 cần suy action từ method + path cho S3.
- **Kết luận:** api-tap dùng được nguyên trạng cho M2; không cần phương án dự phòng chỉ dùng polling.

## moto Lab 3 (Phase 2)

Cấu hình: `INITIAL_NO_AUTH_ACTION_COUNT=3`. Chỉ ba lệnh tạo user `admin` (kèm policy `*` và access key) là không xác thực; mọi lệnh sau đó đều ký bằng key IAM thật. Như vậy không phải đếm lại khi kịch bản thay đổi. Bằng chứng: `spikes/m0-moto/out/summary.txt`.

| Trường hợp | Kỳ vọng (AWS thật) | moto 5.2.4 | Floci `simulate-*` |
|---|---|---|---|
| Allow `lab03/alice/*`, ghi `alice/x` | cho phép | cho phép (đúng) | `allowed` (đúng) |
| Như trên, ghi `bob/x` | `AccessDenied` | `AccessDenied` (đúng) | `implicitDeny` (đúng) |
| Như trên, `iam list-users` / `s3 get-object` | `AccessDenied` | `AccessDenied` (đúng) | — |
| Allow `lab03/*` + Deny `lab03/bob/*`: ghi `alice/`, `carol/` | cho phép | cho phép (đúng) | — |
| Như trên, ghi `bob/` | `AccessDenied` | `AccessDenied` (đúng) | — |
| Allow có `Condition` SSE=AES256, ghi **không** SSE | `AccessDenied` | **cho phép (sai)**: moto bỏ qua Condition | `implicitDeny` (đúng); `allowed` khi truyền context AES256 |
| Key bootstrap sau khi hết lượt không xác thực | bị từ chối | `InvalidClientTokenId` (đúng) | — |
| `simulate-principal-policy` / `simulate-custom-policy` | trả quyết định | **HTTP 500, `NotImplementedError`** | **hoạt động, đánh giá cả Condition** (`spikes/m0-moto/out/floci-simulate.txt`) |

Reset moto:
- `POST /moto-api/reset` xoá sạch trạng thái, nhưng **không** khôi phục lượt không xác thực, nên sau đó không bootstrap được nữa.
- `POST /moto-api/reset-auth` với body là số trần và `Content-Type: text/plain` sẽ khôi phục lượt. Body JSON, hoặc body form mặc định của curl, gây HTTP 500.
- Sau reset + reset-auth, chạy lại Lab 3 cho kết quả giống hệt ở cả 28 bước (`spikes/m0-moto/out/rerun-after-reset/`).
- Request không ký gửi tới moto trả HTTP 500 thay vì 403.

Hệ quả:
- Lab 3 dùng được moto cho enforcement với Allow/Deny theo resource.
- Lab có `Condition` không được dựa vào moto để chặn. Với các lab đó, checker IAM có thể gọi `iam simulate-principal-policy` của Floci. Điều này trả lời câu hỏi mở số 5 trong báo cáo nghiên cứu: Floci có, moto không. MiniStack chưa kiểm.

## Chọn backend

**Floci làm backend chính.** Lý do:
- 38/39 trường đúng trên máy đo, và trường còn lại (`PrivateIpAddress`) đúng khi CIDR không trùng mạng Docker; MiniStack thiếu `NatGatewayAddresses` và cấp IP private ngoài subnet.
- EC2 chạy container thật, nên tiêu chí "curl tới cổng 80" của Lab 7 làm được.
- Có `simulate-principal-policy` để chấm IAM.

Những điểm collector ở M2 phải xử lý hoặc vá:
1. `PrivateIpAddress` có thể nằm ngoài CIDR khai báo (CIDR trùng mạng Docker). Cần preflight cảnh báo, và vẽ theo `SubnetId` chứ không theo IP.
2. `PublicIpAddress` là `127.0.0.1` trên Docker Desktop. Hiển thị cổng đã public thay cho IP.
3. `ReservationId` không ổn định. Dùng `InstanceId` làm khoá.
4. Instance có thể ở trạng thái `running` nhiều phút trước khi UserData xong. Checker cần thăm dò cổng có timeout dài.
5. Dọn tài nguyên mồ côi theo label `io.floci.owner`.

MiniStack giữ vai trò dự phòng: khởi động và reset nhanh hơn, có endpoint reset, nhưng chỉ đủ cho các lab kiểm tra cấu hình.
