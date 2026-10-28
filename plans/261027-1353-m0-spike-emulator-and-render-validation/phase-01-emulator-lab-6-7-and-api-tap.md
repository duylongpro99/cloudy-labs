---
phase: 1
title: "Emulator Lab 6 + 7 và api-tap"
status: completed
priority: P1
effort: "5h"
dependencies: []
---

# Phase 1: Emulator Lab 6 + 7 và api-tap

## Goal

Chạy toàn bộ lệnh của Lab 6 + 7 trên Floci và MiniStack, lưu output `describe-*` thật, so sánh với nhu cầu của resource graph (PRD F2.4) để chọn backend. Đồng thời xác nhận một proxy mỏng chuyển tiếp được lệnh AWS CLI.

## Files to Create / Modify

- Create: `spikes/m0-emulators/docker-compose.yml`. Floci ở cổng 4566 và MiniStack ở cổng 4567. Image được ghim bằng tag cụ thể kèm digest, tra tại thời điểm làm.
- Create: `spikes/m0-emulators/lab-06-07.sh`. Chạy chuỗi lệnh Lab 6 + 7 với `--endpoint-url` lấy từ tham số, rồi lưu từng output vào `out/<backend>/<step>.json`.
- Create: `spikes/m0-emulators/field-check.py`. Đọc `out/<backend>/` và so với bảng trường cần thiết bên dưới, in ra ma trận "có / thiếu / sai".
- Create: `spikes/m0-emulators/api-tap.py`. Reverse proxy tối giản bằng Python stdlib hoặc aiohttp, lắng nghe ở 4580, chuyển tiếp nguyên header và body tới một upstream, rồi in một dòng log cho mỗi request: service, action, status, thời gian.
- Create: `spikes/m0-emulators/out/` (kết quả, có commit để làm bằng chứng)

## Bảng trường cần cho resource graph

| Tài nguyên | Lệnh | Trường bắt buộc |
|---|---|---|
| VPC | `describe-vpcs` | `VpcId`, `CidrBlock`, `Tags` |
| AZ | `describe-availability-zones` | `ZoneName`, `ZoneId` |
| Subnet | `describe-subnets` | `SubnetId`, `VpcId`, `CidrBlock`, `AvailabilityZone`, `MapPublicIpOnLaunch` |
| Internet Gateway | `describe-internet-gateways` | `InternetGatewayId`, `Attachments[].VpcId` và `State` |
| NAT Gateway | `describe-nat-gateways` | `NatGatewayId`, `SubnetId`, `VpcId`, `State`, `NatGatewayAddresses` |
| Route Table | `describe-route-tables` | `RouteTableId`, `VpcId`, `Associations[].SubnetId` và `Main`, `Routes[]` (`DestinationCidrBlock`, `GatewayId`, `NatGatewayId`) |
| Security Group | `describe-security-groups` | `GroupId`, `VpcId`, `IpPermissions`, `IpPermissionsEgress` |
| Key Pair | `describe-key-pairs` | `KeyName`, `KeyPairId` |
| Instance | `describe-instances` | `InstanceId`, `State.Name`, `SubnetId`, `VpcId`, `SecurityGroups`, `PublicIpAddress`, `PrivateIpAddress`, `KeyName` |

## Tasks & Steps

1. Tra tag ổn định mới nhất của Floci và MiniStack trên registry (dùng repo `floci-io` và `ministackorg`, không dùng fork), ghi tag và digest vào compose. Kiểm tra cổng 4566 và 4567 đang trống.
2. `docker compose up -d`, chờ health của cả hai backend.
3. Viết `lab-06-07.sh` theo đúng kịch bản Lab 6 + 7:
   - VPC `10.0.0.0/16`, hai subnet public và hai subnet private ở hai AZ.
   - IGW được attach vào VPC, NAT đặt trong subnet public.
   - Một route table public có route `0.0.0.0/0` trỏ tới IGW, một route table private có route `0.0.0.0/0` trỏ tới NAT, kèm các association.
   - SG mở cổng 22 cho một IP và cổng 80 cho mọi nơi.
   - Một key pair, và một instance trong subnet public có UserData chạy một web server.
4. Chạy script cho từng backend. Lưu cả stderr và exit code của từng bước.
5. Chạy `field-check.py` để ra ma trận trường cho mỗi backend.
6. Với Floci: thử `curl` tới cổng 80 của container EC2 xem trang do UserData tạo ra có trả về không. Đây là chỉ báo cho tiêu chí "curl tới cổng 80" của Lab 7.
7. Đo thời gian reset: thời gian `docker compose restart` khi persistence tắt, và thời gian xoá từng tài nguyên bằng API.
8. **api-tap**:
   - Chạy proxy ở 4580 với upstream là Floci.
   - Chạy lại một phần script qua `--endpoint-url http://localhost:4580`.
   - So sánh output với lần gọi trực tiếp. Ghi lại khác biệt nếu có, chú ý header `Host` và chữ ký SigV4.
   - Ghi lại độ trễ mà proxy thêm vào.
9. Ghi ghi chú thô vào `plans/261027-1353-m0-spike-emulator-and-render-validation/notes/emulator-notes.md`, gồm lỗi, hành vi khác AWS thật và workaround. Ghi chú này sẽ được tổng hợp vào báo cáo ở Phase 5.
10. `docker compose down -v`, dừng api-tap.

## Verification

- `ls spikes/m0-emulators/out/floci spikes/m0-emulators/out/ministack` có đủ file cho mọi bước.
- `python3 spikes/m0-emulators/field-check.py` in ra ma trận đầy đủ 9 loại tài nguyên cho cả hai backend.
- Có kết luận api-tap kèm số đo độ trễ.
- `docker ps` không còn container của spike, và `lsof -i :4566 -i :4567 -i :4580` không trả về gì.

## Rủi ro và rollback

- Nếu một backend không chạy được trên arm64, ghi lại nguyên nhân và tiếp tục với backend còn lại.
- Nếu SigV4 bị lỗi qua proxy, thử giữ nguyên header `Host` gốc khi chuyển tiếp. Nếu vẫn lỗi thì ghi lại; phương án dự phòng cho M2 là chỉ dùng polling.
- Rollback: xoá `spikes/m0-emulators/` và chạy `docker compose down -v`.
