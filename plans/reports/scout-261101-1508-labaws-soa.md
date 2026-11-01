# Scout labaws.site — nhóm C (SOA), 7 lab

Ngày: 2026-11-01 (Asia/Saigon). Nguồn: Chrome của user (đã đăng nhập), tab riêng, chỉ dùng navigate + get_page_text + script đánh dấu DOM `md-mark.js`. Không có download/fetch/click nút nào.

## Tổng quan

- Tải được cả 7/7 lab. Không trang nào 404 hoặc bị chặn (gated).
- Cả 7 lab đều **console-first**. Không có fenced block nào chứa lệnh `aws ` (0/7). Các code block chỉ gồm sơ đồ mermaid, user-data, JSON/YAML mẫu, log mẫu và một lệnh `curl`.
- Mọi dịch vụ AWS mà các lab thực sự dùng đều **đã có trong registry**: autoscaling, ec2, elbv2, acm, route53, logs, cloudwatch, sns, events, config, s3, cloudformation, sqs. Không phát hiện dịch vụ mới.
- Region trong mọi lab là ap-southeast-2 (Sydney).

| Lab | File đã lưu | Kích thước | Chế độ | Block có `aws ` / tổng số fence |
| --- | --- | --- | --- | --- |
| lab-02 | `labs/lab-02-cau-hinh-auto-scaling-group-da-az-de-tang-high-availability/content/lab.md` | 11 726 B | console-first | 0 / 2 |
| lab-15 | `labs/lab-15-import-certificate-vao-acm-va-gan-vao-load-balancer/content/lab.md` | 11 105 B | console-first | 0 / 3 |
| lab-62 | `labs/lab-62-tao-cloudwatch-logs-metric-filter-tu-application-log/content/lab.md` | 8 462 B | console-first | 0 / 4 |
| lab-64 | `labs/lab-64-tao-eventbridge-rule-bat-su-kien-ec2-state-change/content/lab.md` | 8 663 B | console-first | 0 / 6 |
| lab-76 | `labs/lab-76-tao-aws-config-managed-rule-kiem-tra-tag-bat-buoc/content/lab.md` | 8 689 B | console-first | 0 / 1 |
| lab-81 | `labs/lab-81-tao-cloudformation-template-co-mapping-ami-theo-region/content/lab.md` | 8 370 B | console-first | 0 / 2 |
| lab-93 | `labs/lab-93-tao-sqs-queue-dlq-va-kiem-thu-retry/content/lab.md` | 8 486 B | console-first | 0 / 2 |

(Tất cả đường dẫn đều tính từ project root `/Users/onedayin20902/personal/agent/aws-hands-on-labs/`.)

## Chi tiết từng lab

### lab-02 — ASG đa AZ
- **Tài nguyên tạo:**
  - 2 security group (ALB SG mở 80 ra internet; web SG chỉ nhận traffic từ ALB SG).
  - Launch template AL2023 t2/t3.micro, user-data cài httpd và gọi IMDSv2 để lấy AZ/instance-id.
  - Target group HTTP:80, health check `/`, healthy và unhealthy threshold đều là 2.
  - ALB internet-facing trải 2 AZ, listener HTTP:80 forward tới TG.
  - ASG desired/min/max = 2/2/4 trên 2 subnet, gắn TG, health check type ELB, grace 300s, tag Name được propagate.
- **Kiểm chứng:**
  - Mỗi AZ có 1 instance, trạng thái InService/Healthy.
  - TG báo 2 target healthy.
  - Terminate 1 instance thì Activity history phải hiện cả event terminate lẫn launch, và capacity trở về 2.
  - Web vẫn truy cập được qua DNS của ALB trong lúc thay thế.
- **Dịch vụ:** ec2, autoscaling, elbv2.
- **Emulator khó làm:** tự phục hồi sau terminate (ASG reconcile và tạo lại instance), ELB health check thật lên httpd, phân bổ đều theo AZ, user-data thực thi, ALB phục vụ HTTP thật, activity history.

### lab-15 — ACM + HTTPS listener
- **Lưu ý về tiêu đề:** lab nói là "Import certificate" nhưng nội dung thực tế dùng **Request public certificate** với DNS validation. Không có bước import (không có `ImportCertificate`).
- **Tài nguyên tạo:**
  - ACM certificate RSA 2048 cho FQDN (có thể kèm wildcard), validation qua CNAME tạo bằng nút "Create records in Route 53".
  - Thêm inbound 443 vào SG của ALB.
  - HTTPS:443 listener với policy `ELBSecurityPolicy-TLS13-1-2-2021-06`, cert từ ACM, forward tới TG.
  - Sửa listener HTTP:80 thành redirect 301 sang HTTPS:443.
  - Route 53 A-alias trỏ về ALB.
  - Lab giả định ALB, TG và EC2 đã có sẵn (soa-lab15-*). Không có bước nào tạo chúng.
- **Kiểm chứng:**
  - Cert chuyển từ Pending validation sang Issued.
  - Trình duyệt hiện ổ khóa, issuer là Amazon RSA 2048.
  - `curl -I http://...` trả 301 kèm Location https.
- **Dịch vụ:** acm, elbv2, route53, ec2.
- **Emulator khó làm:**
  - Phải sở hữu domain/hosted zone thật.
  - ACM DNS validation và chuyển trạng thái sang ISSUED.
  - TLS handshake thật với cert do Amazon CA ký.
  - Kiểm tra bằng trình duyệt và DNS công khai.
  - Redirect 301 có thể kiểm bằng cấu hình listener, nhưng gọi HTTP thật thì khó.

### lab-62 — CloudWatch Logs metric filter
- **Tài nguyên tạo:**
  - Log group `/aws/app/lab62-payment-service` với retention 1 ngày, log stream `payment-api-node-01`.
  - Nạp log mẫu bằng tay.
  - Metric filter pattern `?ERROR ?CRITICAL ?Exception` ra metric `MyApp/Production` / `ApplicationErrorCount`, value 1, default 0, unit Count.
  - Alarm Sum, period 1 phút, ngưỡng > 2, 1/1 datapoint, action SNS (dùng topic có sẵn hoặc tạo mới).
- **Kiểm chứng:**
  - Test pattern highlight các dòng khớp.
  - Đẩy thêm log lỗi thì metric tăng lên 4 và alarm chuyển từ OK sang ALARM.
- **Dịch vụ:** logs, cloudwatch, sns.
- **Nội dung không nhất quán / không chính xác:**
  - Console không có thao tác "Actions > Create log event". Trên thực tế phải dùng PutLogEvents qua CLI/SDK, nên bước này cần builder/terminal bổ sung.
  - Lab nói "thêm 5 sự kiện" nhưng chỉ liệt kê 4.
  - Sơ đồ ghi ngưỡng > 5, còn phần các bước ghi > 2.
  - Timestamp mẫu cố định ở 2026-10-26. Nếu PutLogEvents dùng đúng timestamp này sẽ bị coi là quá cũ.
- **Emulator khó làm:** metric filter phải sinh datapoint từ log, alarm phải tự đánh giá theo chu kỳ 1 phút rồi chuyển trạng thái, và gửi notification qua SNS/email.

### lab-64 — EventBridge rule EC2 state-change
- **Tài nguyên tạo:**
  - Rule trên default bus với pattern `source aws.ec2`, `detail-type "EC2 Instance State-change Notification"`, `detail.state` gồm stopping/stopped/shutting-down/terminated.
  - Target SNS topic kèm input transformer: InputPath map instance/state/time/region, template nhiều dòng.
  - Lab giả định đã có sẵn EC2 instance và SNS topic với email subscription đã confirm.
- **Kiểm chứng:**
  - Stop instance thì nhận email đã được format, gồm 1 email cho stopping và 1 email cho stopped.
  - Tab Monitoring của rule có Invocations và TriggeredRules.
- **Dịch vụ:** events, ec2, sns.
  - Lambda/SSM chỉ xuất hiện như mũi tên tùy chọn trong sơ đồ, không có bước tạo.
- **Emulator khó làm:**
  - EC2 phải phát event state-change lên EventBridge khi stop.
  - Input transformer render template, và template nhiều dòng có dấu ngoặc kép từng dòng là cú pháp khá đặc thù.
  - Gửi email qua SNS.
  - Metric Invocations/TriggeredRules.
  - Resource policy của SNS cho `events.amazonaws.com` được nhắc trong phần troubleshooting.

### lab-76 — AWS Config required-tags
- **Tài nguyên tạo:**
  - Configuration recorder ghi tất cả hoặc chỉ `AWS::EC2::Instance` + `AWS::S3::Bucket`, delivery channel tới S3 bucket mới, role service-linked.
  - Managed rule `required-tags` tên `lab76-check-environment-tag`, trigger theo thay đổi, scope EC2 Instance + S3 Bucket, `tag1Key=Environment`, `tag1Value=Dev,Staging,Prod`.
  - Lab giả định đã có sẵn ít nhất 1 tài nguyên có tag và 1 tài nguyên không có tag.
- **Kiểm chứng:**
  - Compliance summary có cả Compliant và Non-compliant.
  - Resource timeline hiển thị lý do vi phạm.
  - Thêm tag Environment=Dev cho EC2, chạy Re-evaluate, sau khoảng 1 phút tài nguyên chuyển sang Compliant.
- **Dịch vụ:** config, s3, ec2.
- **Emulator khó làm:** điểm cốt lõi là **rule evaluation thật** (managed rule logic, Re-evaluate, chuyển trạng thái compliance), cùng với configuration items/timeline và việc ghi snapshot ra S3. Phần này hầu như chắc chắn phải giả lập hoặc để ngoài phạm vi.

### lab-81 — CloudFormation Mappings AMI theo Region
- **Tài nguyên tạo:**
  - Stack `lab81-ec2-mapping-stack` từ template YAML.
  - Parameters: EnvironmentType, InstanceTypeParam.
  - Mappings `RegionMap` cho 3 region.
  - 1 `AWS::EC2::Instance` với `ImageId: !FindInMap [RegionMap, !Ref AWS::Region, AMI]` và tag Name/ManagedBy/DeployedRegion.
  - Outputs InstanceID và SelectedAMI.
- **Kiểm chứng:**
  - Events đi tới CREATE_COMPLETE.
  - Outputs SelectedAMI khớp AMI của Sydney.
  - Instance `lab81-server-dev` có đúng AMI và tag.
- **Dịch vụ:** cloudformation, ec2.
  - SSM Parameter Store chỉ được nhắc trong bảng so sánh, không có bước tạo.
- **Lưu ý:**
  - Các AMI ID trong template là giá trị cứng và rất có thể đã cũ/không tồn tại. Builder nên cho phép AMI tùy ý hoặc dùng AMI giả lập.
  - `get_page_text` làm mất thụt lề YAML. Tôi đã đọc lại khối YAML trực tiếp từ DOM (chỉ đọc, sau khi chạy md-mark) để giữ đúng indentation trong `lab.md`.
- **Emulator khó làm:** tương đối dễ (CFN + FindInMap + pseudo parameter). Khó nhất là upload template bằng file chooser trên console và kiểm tra AMI có thật.

### lab-93 — SQS + DLQ + redrive
- **Tài nguyên tạo:**
  - DLQ Standard `lab93-orders-dlq`, visibility 30s, retention 14 ngày.
  - Main queue `lab93-orders-main-queue`, visibility 30s, retention 4 ngày, RedrivePolicy tới DLQ với `maxReceiveCount=3`.
  - Task DLQ redrive về source queue (StartMessageMoveTask).
- **Kiểm chứng:**
  - Gửi 1 message, poll 3 lần không xóa và chờ hết visibility timeout giữa các lần.
  - Main queue về 0, DLQ lên 1.
  - Redrive đưa message trở lại main queue.
- **Dịch vụ:** sqs. CloudWatch chỉ được nhắc tên metric, không có bước tạo.
- **Lưu ý ngữ nghĩa:** trên AWS thật, message chuyển sang DLQ ở **lần receive thứ 4** (khi ReceiveCount vượt maxReceiveCount), không phải ngay sau lần thứ 3. Lab chỉ "refresh" sau lần 3, nên kết quả có thể không như mô tả. Cần xử lý cẩn thận trong checker/emulator.
- **Emulator khó làm:**
  - Timing của visibility timeout (chờ 30s × 3).
  - Đếm ApproximateReceiveCount và thời điểm chuyển sang DLQ.
  - Message move task là bất đồng bộ.

## Ghi chú kỹ thuật về quá trình lấy dữ liệu

- `get_page_text` cắt khoảng trắng đầu dòng. JSON (lab-64, lab-93) và heredoc (lab-02) vẫn đúng ngữ nghĩa nhưng mất thụt lề. Riêng YAML của lab-81 đã được khôi phục từ DOM.
- Fence mermaid không còn nhãn ngôn ngữ (` ``` ` trống) vì script md-mark không giữ language.
- Tab group của Chrome bị agent khác thay đổi giữa chừng, khiến tab đầu tiên tôi tạo (1677954484) không còn truy cập được. Tôi đã tạo tab mới (1677954487) và đóng nó khi xong. Tab 1677954484 không còn xuất hiện trong context nên không đóng được.

## Câu hỏi còn mở

- lab-15: có muốn giữ tên "Import" hay đổi cho khớp với nội dung (request + DNS validation)? Có muốn thêm biến thể import cert tự ký để không cần domain thật?
- lab-62: dùng CLI `put-log-events` thay cho bước console không tồn tại?
- lab-76: phạm vi giả lập rule evaluation của AWS Config đến đâu?
