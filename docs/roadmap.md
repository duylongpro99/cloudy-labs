# Roadmap: Cloudy Labs — hands-on labs for AWS

- Cập nhật: 2026-10-29
- Yêu cầu sản phẩm: [product-requirements.md](product-requirements.md). Mã F*/NFR*/A* trong file này trỏ về PRD.
- Mỗi giai đoạn sẽ có plan riêng trong `plans/` trước khi bắt đầu làm. Roadmap này chỉ ghi thứ tự, phạm vi và điều kiện để chuyển sang giai đoạn sau.
- Cột "Quy mô" là ước lượng tương đối cho một người làm, chưa được kiểm chứng: S nghĩa là vài ngày, M khoảng 1–2 tuần, L khoảng 2–4 tuần.

## Tổng quan

```text
M0 Spike ─► M1 Nền tảng lab ─► M2 Resource graph + cảnh 3D ─► M3 Builder Lab 6 ─► M4 Builder Lab 7
                                                                                         │
                                       M7 Mở rộng lab ◄─ M6 Twin + ghost ◄─ M5 Chat ◄────┘
```

Thứ tự tính năng mà người dùng nhìn thấy là **builder → chat → twin**. Hạ tầng đồng bộ trạng thái (M2) phải có trước builder, vì builder vẽ cảnh dựa trên trạng thái thật mà emulator trả về.

## Các giai đoạn

| Mốc | Mục tiêu | Phạm vi (PRD) | Điều kiện để qua mốc | Phụ thuộc | Quy mô |
|---|---|---|---|---|---|
| **M0. Spike** ([plan](../plans/261027-1353-m0-spike-emulator-and-render-validation/plan.md), [báo cáo](../plans/reports/spike-261027-2248-m0-validation.md)). **Hoàn thành 2026-10-27** | Kiểm chứng giả định trước khi xây | A4, A5, A6. Chạy các lệnh của Lab 6 + 7 trên Floci và MiniStack, rồi Lab 3 trên moto. Dựng một cảnh mẫu 200 node theo công thức F3.7, ở cả chủ đề sáng và tối, để đo hiệu năng. Kiểm tra mọi phụ thuộc dự kiến đều có giấy phép tương thích MIT và cho phép dùng thương mại | Có báo cáo spike ghi lại output `describe-*` cho từng loại tài nguyên ở F2.4, những trường bị thiếu hoặc sai, và quyết định chọn Floci hay MiniStack. Có số đo FPS và thời gian khung hình trên Chrome và Safari, đủ để chốt mức hậu kỳ mặc định. Đã chốt A5. Kết quả: chọn Floci, hậu kỳ mặc định đầy đủ, A4/A6/A8 đạt. A5 vẫn chờ pháp lý; từ 2026-10-28 icon AWS được dùng làm mặc định và người dùng chấp nhận rủi ro (PRD A13) | — | S |
| **M1. Nền tảng lab** | `labctl` chạy được Lab 6 + 7 hoàn toàn bằng CLI | F1.1–F1.5, NFR1, NFR5–NFR7. File `docker-compose` cho emulator. Định nghĩa YAML và các check của Lab 6 + 7. Theo spike M0: preflight cảnh báo CIDR trùng mạng Docker, dọn container/network mồ côi của Floci theo label `io.floci.owner`, pull sẵn `alpine/socat:latest`, moto chạy ở cổng 5050 và reset bằng `reset` + `reset-auth`, UserData Lab 7 bind vào IP private. Phần engine đã xong ([plan](../plans/261028-1104-m1-lab-engine-labctl/plan.md), [labctl.md](labctl.md), [emulator-differences.md](emulator-differences.md)); YAML và check của Lab 6 + 7 còn chờ nội dung lab. Điều kiện qua mốc hiện mới chứng minh bằng lab fixture; **phải kiểm lại bằng Lab 6 + 7 thật** trước khi coi M1 là đóng | Chạy `labctl up`, `start lab-06`, tự làm bằng CLI, rồi `check` báo đạt. `reset` đưa emulator về trạng thái sạch. Có test cho các checker | M0 | M |
| **M2. Resource graph + cảnh 3D** ([plan thư viện object](../plans/261028-0230-m2-aws-icon-3d-object-library/plan.md), [plan graph và cảnh trực tiếp](../plans/261029-1006-m2-resource-graph-collector-scene/plan.md), [số đo hiệu năng](../plans/261029-1006-m2-resource-graph-collector-scene/notes/perf-results.md), [kiểm thử đầu-cuối](../plans/261029-1006-m2-resource-graph-collector-scene/notes/e2e-results.md)). **Hoàn thành 2026-10-29** | Nhìn thấy trạng thái emulator dưới dạng sơ đồ AWS 3D, ở chế độ chỉ xem | F2.1–F2.4, F3.1–F3.9, NFR2–NFR4, NFR8. Thư viện 3D object dựng từ AWS Architecture Icons cho các tài nguyên ở F2.4, có biến thể sáng và tối ([plan](../plans/261028-0230-m2-aws-icon-3d-object-library/plan.md), đã xong). Theo spike M0: collector xử lý `PrivateIpAddress`/`PublicIpAddress`/`ReservationId` của Floci (báo cáo mục 2), và cảnh dùng `<Canvas orthographic>` (báo cáo mục 5) | Tạo tài nguyên bằng CLI thì cảnh hiện đúng cấu trúc lồng nhau trong ≤ 2 giây. Bố cục xác định. Có test cho schema của graph. Đạt ≥ 50 fps với 200 node ở cả hai chủ đề. Không dùng asset nào chưa rõ giấy phép thương mại, trừ icon AWS đã chấp nhận rủi ro theo PRD A13 | M1 | L |
| **M3. Builder Lab 6** | Dựng được VPC hoàn chỉnh bằng kéo-thả | F4.1–F4.6 cho VPC, Subnet, IGW, NAT, Route Table và route | Hoàn thành Lab 6 chỉ bằng builder, `labctl check` báo đạt. Mỗi thao tác hiện đúng lệnh CLI. Có test cho validate CIDR | M2 | L |
| **M4. Builder Lab 7** | Chạy được EC2 trong VPC bằng builder | F4.1–F4.6 cho Security Group, Key Pair, Instance và UserData. F4.7 (chế độ luyện tập) | Hoàn thành Lab 7 bằng builder. SG không mở cổng 22 cho `0.0.0.0/0` (check đạt). Chế độ luyện tập hoạt động qua api-tap | M3 | M |
| **M5. Chat** | Hỏi bằng ngôn ngữ tự nhiên và nhận lệnh CLI đúng | F5.1–F5.6 | Với một bộ câu hỏi mẫu cho Lab 6 + 7, lệnh gợi ý dùng ID thật và qua được validate. Không lệnh nào tự chạy | M4 (dùng lại command-builder và validate) | M |
| **M6. Twin + ghost** | Làm lab ở terminal và nhìn kiến trúc tự hiện ra | F6.1–F6.4. Trường `target` trong YAML của Lab 6 + 7 | Ghost chuyển sang đặc khi check qua. Bấm vào check thì tô sáng node liên quan. `reset` làm sạch cảnh | M2 (hạ tầng), M5 (theo thứ tự ưu tiên) | M |
| **M7. Mở rộng lab** | Phủ đủ lộ trình 11 lab | F7.1–F7.2. Palette và kiểu hiển thị cho IAM, S3, DynamoDB, Lambda, SQS, CloudFormation | Mỗi lab mới có YAML, checker, palette và ghost. Lab 3 chạy trên moto và hiển thị được | M6 | L, chia nhỏ theo từng lab |

## Ngoài roadmap (xem xét sau M7)

- GCP qua `GcpProvider` (floci-gcp hoặc emulator chính thức của Google).
- Chế độ builder sinh CloudFormation hoặc Terraform cho cả kiến trúc, thay vì từng lệnh.
- Hỗ trợ người soạn lab viết lab mới mà không cần sửa code.

## Cách cập nhật

Khi một mốc hoàn thành hoặc thay đổi phạm vi, cập nhật bảng trên và đặt link tới plan hoặc báo cáo tương ứng. Chi tiết thực thi nằm trong `plans/`, không ghi vào đây.
