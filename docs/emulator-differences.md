# Emulator khác AWS thật ở đâu

Ghi chú cho người soạn lab (PRD NFR5). Mỗi lab chạy trên Floci (mặc định) hoặc moto. Những điểm dưới đây đã được đo ở spike M0 ([báo cáo](../plans/reports/spike-261027-2248-m0-validation.md), mục 2 và 3). Khi viết đề bài và checker, hãy tránh dựa vào hành vi khác với AWS thật, hoặc ghi rõ khác biệt đó trong đề.

## Floci

### Mạng và IP

- **CIDR trùng mạng Docker thì IP private bị đổi.** Floci tạo một Docker network cho mỗi VPC. Nếu CIDR của VPC trùng một mạng Docker có sẵn trên máy, Floci âm thầm dựng VPC trên `10.240.0.0/16`. `PrivateIpAddress` khi đó nằm ngoài subnet đã khai báo.
  - Khai báo mọi CIDR lab sẽ tạo trong trường `cidrs` của `lab.yaml`. `labctl start` sẽ cảnh báo khi có trùng.
  - Checker nên kiểm instance thuộc subnet nào qua `SubnetId`, không suy từ IP.
- **`PublicIpAddress` là `127.0.0.1`** trên Docker Desktop. SSH được public ngay trên container instance (`floci-aws-ec2-i-<id>`, ví dụ `2200->22`); mỗi cổng ứng dụng mà security group mở đi qua một container socat riêng (`floci-aws-ec2-fwd-i-<id>-<cổng>`) trong dải 30000–30999. Cả hai bind `0.0.0.0`, không phải `127.0.0.1`. Cảnh 3D và panel thuộc tính hiển thị các cổng host này (`127.0.0.1:<cổng>`) thay cho IP công khai.
- **IMDS chiếm `169.254.169.254:80` bên trong instance.** Web server bind `0.0.0.0:80` sẽ lỗi `Address already in use`. Bind riêng IP private cũng chưa đủ: container instance có ba địa chỉ (bridge Docker, IP private trong VPC, và network `cloudy-labs_default`), và container chuyển cổng `floci-aws-ec2-fwd-…` nối tới địa chỉ trên `cloudy-labs_default`. UserData (ví dụ Lab 7) phải bind từng địa chỉ IPv4 của instance, trừ `lo`. Trên AWS thật vòng lặp này chỉ gặp IP private:

  ```bash
  for IP in $(ip -4 -o addr show scope global | awk '$2 != "lo" {sub(/\/.*/, "", $4); print $4}'); do
    nohup python3 -m http.server 80 --bind "$IP" &
  done
  ```

### EC2

- **`ReservationId` đổi sau mỗi lần gọi `describe-instances`.** Dùng `InstanceId` làm khoá.
- **Instance báo `running` trước khi UserData chạy xong.** Với AMI Amazon Linux 2023 trong catalog, UserData bắt đầu chạy khoảng 1–2 giây sau đó; spike M0 (trước khi có image build sẵn) đo được từ 45 giây đến khoảng 6 phút. UserData tự cài gói (ví dụ `dnf install httpd`) vẫn tốn thời gian tải. Checker kiểm kết quả của UserData cần nói rõ trong thông điệp trượt rằng người học có thể phải chờ.
- **AMI Amazon Linux 2023 chạy image `labctl` tự build** (`cloudy-labs/al2023:1-<kiến trúc>`, khai báo trong [`ec2-image-catalog.yaml`](../server/src/cloudy_labs/emulator/ec2-image-catalog.yaml)). Image này cài sẵn `iproute`, `socat`, `curl` và OpenSSH, nên Floci bỏ qua bước cài gói qua mạng mỗi lần khởi động. IMDS sẵn sàng khoảng 2 giây sau khi container instance chạy (trước đây 18–22 giây, và spike M0 từng gặp timeout 180 giây khiến instance không có IMDS). Đo ngày 2026-10-28: 20/20 lần IMDS trả credential của instance profile.
  - Chỉ AMI có trong catalog được hưởng. AMI ID lạ rơi về image mặc định `amazonlinux:2023` gốc và vẫn cài gói lúc khởi động (khoảng 30 giây). Lab nên dùng AMI có trong catalog, ví dụ `ami-amazonlinux2023-arm64` hoặc `ami-amazonlinux2023`, hoặc lấy qua tham số SSM `/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64`.
  - AMI kiến trúc khác máy (ví dụ AMI x86_64 trên Mac Apple Silicon) chạy qua giả lập, chậm hơn khi chạy lệnh nặng.
- **Rule inbound trùng vẫn được thêm.** `authorize-security-group-ingress` với rule đã có trả exit 0 và nhân đôi rule; AWS thật trả `InvalidPermission.Duplicate`. Builder tự chặn rule trùng trước khi chạy; checker nên coi một group có rule trùng là bình thường.
- **Key pair bỏ qua tag.** `create-key-pair --tag-specifications` chạy được nhưng `describe-key-pairs` trả `Tags: []`. Đừng tìm key pair của lab theo tag; dùng `KeyName`.
- **Subnet chồng lấn bị từ chối như AWS** (`InvalidSubnet.Conflict`). Trùng tên security group (`InvalidGroup.Duplicate`), trùng tên key pair (`InvalidKeyPair.Duplicate`) và `modify-instance-attribute --groups` cũng giống AWS ([ghi chú kiểm](../plans/261030-1045-m4-builder-lab-07/notes/floci-ec2-ops.md)).
- **Lần đầu public cổng ứng dụng, Floci pull `alpine/socat` không kèm tag**, khiến Docker kéo về mọi tag. `labctl up` pull sẵn `alpine/socat:latest` để tránh việc này.

### Cổng host

- **Floci nghe ở `4567`, cả trong container (`FLOCI_PORT=4567`) lẫn trên host (`127.0.0.1:4567`)**; người học và checker vẫn dùng `4566`, nơi api-tap chuyển tiếp nguyên vẹn sang Floci ([bảng cổng](labctl.md#cổng)). Label `io.floci.owner` bằng cổng Floci nghe trong container, nên tài nguyên của stack này mang `4567` và không lẫn với một Floci mặc định khác (owner `4566`) trên cùng máy ([ghi chú kiểm](../plans/261029-1006-m2-resource-graph-collector-scene/notes/floci-port-move.md)).

### Vòng đời

- **`docker compose down` để lại container EC2, network VPC và volume.** Các tài nguyên này mang label `io.floci.owner=4567`, trừ container socat chuyển cổng ứng dụng (chỉ có `floci_emulator=floci-aws`; `labctl` nhận chúng qua id instance trong tên `floci-aws-ec2-fwd-i-<id>-<cổng>`). `labctl down` và `labctl up` dọn chúng; xem [ghi chú label](../plans/261028-1104-m1-lab-engine-labctl/notes/floci-labels.md).
- **Nâng cấp từ stack dựng trước khi Floci đổi sang cổng 4567:** chạy `labctl down` bằng bản cũ trước khi cập nhật. Tài nguyên còn sót của stack cũ mang owner `4566`, bản mới không dọn chúng vì không phân biệt được với một Floci khác.
- **Reset bằng cách tạo lại container Floci** (khoảng 1 giây, khoảng 5 giây khi còn instance) vì Floci giữ trạng thái trong bộ nhớ. Xoá từng tài nguyên bằng API chậm hơn nhiều (khoảng 19 giây cho Lab 6 + 7).
- **Không restart container Floci khi đã có instance.** Floci tự gắn container của nó vào network của mỗi VPC. Khi restart, Docker gắn lại các network đó, rồi Floci xoá chúng lúc khởi động. Thỉnh thoảng (2 trên 16 lần đo) Docker Desktop khi đó chuyển tiếp cổng host vào endpoint đã mất: container vẫn healthy nhưng cổng host của Floci (`127.0.0.1:4567`, và vì thế cả `4566` qua api-tap) treo. `labctl` vì vậy xoá container rồi tạo mới thay cho restart. Nếu Floci bị restart ngoài `labctl` (ví dụ `docker restart`), chạy `labctl up`; lệnh này phát hiện cổng host không trả lời và tạo lại container.

## moto

- **Không đánh giá `Condition` trong policy IAM.** Lab về IAM không được chấm dựa trên điều kiện.
- **`simulate-principal-policy` và `simulate-custom-policy` trả HTTP 500** (`NotImplementedError`).
- **Request không ký trả HTTP 500 thay vì 403** sau khi hết lượt không xác thực.
- **IAM được thực thi từ lần `start`/`reset` đầu tiên.** Mỗi lần, `labctl` gọi `/moto-api/reset-auth` để mở 3 lượt không xác thực (số này chỉ khai báo ở `providers/aws.py`) rồi dùng hết 3 lượt đó để tạo user `cloudy-labs-admin` có quyền `*` và một access key. Sau đó `test`/`test` bị từ chối (`AuthFailure`). Lệnh của người học (qua `labctl env <lab>`) và checker đều ký bằng user này. Lab muốn kiểm `AccessDenied` thì để người học tự tạo user ít quyền; checker có thể dùng `ctx.client(service, credentials=(key, secret))` để hành động như user đó. Trước lần `start` đầu tiên, moto chưa bật IAM.
- **Cổng 5050** trên host, vì cổng 5000 trên macOS bị AirPlay Receiver chiếm.
