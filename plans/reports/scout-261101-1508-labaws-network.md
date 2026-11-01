# Scout: labaws.site nhóm A (Network) — 7 lab

- Ngày: 2026-11-01 (Asia/Saigon)
- Nguồn: https://labaws.site/labs/<slug>, đọc bằng Chrome đã đăng nhập của user (chỉ navigate + get_page_text + script đánh dấu DOM `md-mark.js`). Không gọi API, không bấm tải Markdown hay nút chia sẻ.
- Kết quả: cả 7 trang đều tải được, không có trang nào 404 hay bị khóa.
- File lưu ở `labs/<slug>/content/lab.md`. Thư mục này bị `.gitignore:13` (`labs/*/content/`) loại khỏi git và chỉ để dùng cá nhân.
- Cột "khối aws" đếm số khối code (fenced block) chứa lệnh `aws `. Ở cả 7 lab, khối duy nhất có lệnh này là script dọn dẹp ở mục 10.

## Tổng quan

| Lab | Kích thước | Mode | Khối fenced / khối `aws` | Dịch vụ ngoài registry |
| --- | --- | --- | --- | --- |
| lab-041-s3-gateway-endpoint | 26 217 B | console-first | 5 / 1 | không |
| lab-042-dynamodb-gateway-endpoint | 22 885 B | console-first | 4 / 1 | không |
| lab-051-route-53-public-hosted-zone | 22 472 B | console-first | 3 / 1 | không |
| lab-057-alb-path-based-routing | 22 923 B | console-first (kiểm tra bằng curl) | 5 / 1 | không |
| lab-060-cloudfront-va-global-accelerator | 24 801 B | console-first (kiểm tra bằng curl) | 7 / 1 | không |
| lab-065-transit-gateway-co-ban | 23 942 B | console-first | 3 / 1 | không |
| lab-081-aws-network-firewall-co-ban | 24 769 B | console-first | 3 / 1 | không |

Đặc điểm chung: các lab đều theo một khuôn gồm kịch bản đề thi, sơ đồ ASCII và Mermaid, bảng so sánh, bảng hop-by-hop, các bước console click-by-click, bảng troubleshooting và script dọn dẹp bash. Vùng mặc định là ap-southeast-2. Phần lớn khối fenced là sơ đồ, JSON policy hoặc output của curl, không phải lệnh CLI. Phần tạo tài nguyên thì không lab nào viết bằng CLI. Vì vậy, để đưa vào builder hoặc terminal của dự án, phải tự chuyển các bước console thành lệnh CLI.

## Chi tiết từng lab

### lab-041-s3-gateway-endpoint
- Đường dẫn: `labs/lab-041-s3-gateway-endpoint/content/lab.md` (26 217 B)
- Mode: console-first, có 1 khối `aws` (cleanup). Lệnh `aws s3 cp` dùng để kiểm tra chỉ xuất hiện dưới dạng một mục danh sách, không nằm trong khối fenced.
- Tài nguyên tạo hoặc kiểm tra:
  - ec2: VPC, private subnet, đổi tên main route table và gán subnet
  - ec2: VPC gateway endpoint cho s3, có endpoint policy tùy chỉnh giới hạn theo ARN bucket
  - Route tự sinh trỏ prefix list `pl-…` tới `vpce-…`
  - s3: bucket private (SSE-S3, chặn public access), upload object
  - s3: bucket policy Deny có điều kiện `StringNotEquals aws:sourceVpce`
- Có nhắc đến nhưng không có bước tạo: security group trỏ outbound tới prefix list, EC2 workload có instance profile SSM, IAM role.
- Ngoài registry: không có (dùng ec2, s3, iam, ssm).
- Khó giả lập bằng emulator:
  - Route của prefix list được chèn tự động khi tạo gateway endpoint.
  - Bước kiểm tra thật cần EC2 trong subnet không có internet tải object qua endpoint.
  - Truy cập từ máy cá nhân phải bị 403 nhờ `aws:sourceVpce`. Emulator cần đánh giá được context key này theo đường mạng thực tế.

### lab-042-dynamodb-gateway-endpoint
- Đường dẫn: `labs/lab-042-dynamodb-gateway-endpoint/content/lab.md` (22 885 B)
- Mode: console-first, có 1 khối `aws` (cleanup).
- Tài nguyên tạo hoặc kiểm tra:
  - ec2: VPC, private subnet, route table
  - dynamodb: bảng on-demand, partition key `OrderId`
  - ec2: VPC gateway endpoint cho dynamodb, policy giới hạn theo ARN bảng
  - Route prefix list trỏ tới `vpce` (kiểm tra trên tab Routes)
  - ec2: security group chỉ có egress 443 tới prefix list của DynamoDB, đã xóa rule mặc định 0.0.0.0/0
- Không có EC2 và không có bước gọi PutItem thật.
- Ngoài registry: không có (ec2, dynamodb).
- Khó giả lập: prefix list do AWS quản lý (`pl-…`) phải tồn tại để vừa dùng làm route vừa làm đích của SG rule. Bước SG yêu cầu chọn đúng prefix list theo tên.
- Lưu ý nội dung: lab khẳng định DynamoDB không hỗ trợ interface endpoint. Điều này đã lỗi thời vì AWS ra mắt PrivateLink cho DynamoDB từ năm 2024. Nếu tái sử dụng lab, nên đánh dấu caveat.

### lab-051-route-53-public-hosted-zone
- Đường dẫn: `labs/lab-051-route-53-public-hosted-zone/content/lab.md` (22 472 B)
- Mode: console-first, có 1 khối `aws` (cleanup; cleanup dùng thêm `jq`).
- Tài nguyên tạo hoặc kiểm tra:
  - route53: public hosted zone, kiểm tra SOA và 4 bản ghi NS tự sinh
  - elbv2: ALB internet-facing trên 2 AZ, listener HTTP:80 trỏ tới target group rỗng
  - route53: hai bản ghi alias A (zone apex và `www`) trỏ tới ALB, bật evaluate target health
  - Kiểm tra bằng nút "Test record" trên console (API TestDNSAnswer), kỳ vọng NOERROR kèm IP của ALB
- Ngoài registry: không có (route53, elbv2, ec2).
- Khó giả lập:
  - Phân giải DNS thật qua alias. Route 53 phải tự trả IP của ALB, tức emulator cần ALB có IP và TestDNSAnswer hoạt động.
  - Ủy quyền NS tại registrar và người dùng internet phân giải được tên miền đều không thể làm cục bộ.
  - Tên miền mẫu `lab051-enterprise.com` không thuộc sở hữu người học.

### lab-057-alb-path-based-routing
- Đường dẫn: `labs/lab-057-alb-path-based-routing/content/lab.md` (22 923 B)
- Mode: console-first, kiểm tra bằng `curl -I`. Có 1 khối `aws` (cleanup) cộng 2 khối curl.
- Tài nguyên tạo hoặc kiểm tra:
  - ec2: VPC tạo bằng "VPC and more" gồm 2 public subnet, IGW và route table
  - elbv2: 2 target group (`web`:80 với health check `/`, `orders`:8080 với health check `/api`), không đăng ký target
  - elbv2: ALB internet-facing có listener HTTP:80, default forward tới `web`
  - elbv2: listener rule priority 10 với điều kiện path-pattern `/api/orders*`, forward tới `orders`
- Kịch bản có nhắc `tg-search` nhưng không tạo.
- Ngoài registry: không có (ec2, elbv2).
- Khó giả lập: phần kiểm tra là HTTP thật tới DNS của ALB. Lab kỳ vọng 503 vì target group không có target khỏe, và dùng 503 đó để chứng minh request đã khớp rule. Emulator cần ALB data plane thật có khớp path-pattern và trả 503 khi không có target.

### lab-060-cloudfront-va-global-accelerator
- Đường dẫn: `labs/lab-060-cloudfront-va-global-accelerator/content/lab.md` (24 801 B)
- Mode: console-first, kiểm tra bằng curl. Có 1 khối `aws` (cleanup); 6 khối còn lại là sơ đồ, curl và output mẫu.
- Tài nguyên tạo hoặc kiểm tra:
  - elbv2: ALB ở ap-southeast-2 (default VPC)
  - cloudfront: distribution với origin là ALB (HTTP only), viewer chuyển HTTP sang HTTPS, cache policy CachingOptimized, price class All, không bật WAF
  - globalaccelerator: accelerator Standard IPv4, listener TCP:80, endpoint group ap-southeast-2 với traffic dial 100, endpoint là ALB weight 128
  - Kiểm tra 2 static anycast IP
- Ngoài registry: không có (elbv2, cloudfront, globalaccelerator, ec2).
- Khó giả lập (nhiều nhất trong nhóm):
  - Header `x-cache` của CloudFront phải chuyển từ Miss sang Hit giữa hai lần curl.
  - Phải curl được tới anycast IP của GA.
  - Thời gian deploy distribution (2–3 phút) và trạng thái accelerator từ In Progress sang Deployed.
  - Lab có nói tới failover đa vùng dưới 30 giây, nhưng không có bước nào tạo vùng thứ hai. Đây chỉ là lý thuyết, không có phần kiểm tra cross-region.
  - Control plane của GA nằm ở us-west-2, nên emulator cần xử lý endpoint toàn cục này.

### lab-065-transit-gateway-co-ban
- Đường dẫn: `labs/lab-065-transit-gateway-co-ban/content/lab.md` (23 942 B)
- Mode: console-first, có 1 khối `aws` (cleanup, dùng `aws ec2 wait transit-gateway-attachment-deleted`).
- Tài nguyên tạo hoặc kiểm tra:
  - ec2: transit gateway với ASN 64512, bật default association và propagation
  - ec2: 2 VPC, mỗi VPC có workload subnet /24 và subnet riêng /28 cho TGW
  - ec2: 2 VPC attachment
  - Kiểm tra route propagated trong TGW route table
  - ec2: thêm route trong VPC route table trỏ CIDR của VPC còn lại tới `tgw-…`
- Không tạo EC2, không có bước ping thật.
- Ngoài registry: không có (ec2).
- Khó giả lập:
  - Propagation tự động phải sinh route TGW kiểu `propagated` sau khi attachment chuyển sang available.
  - Các chuyển trạng thái pending → available mất vài phút.
  - Kết nối thật giữa hai VPC thì lab không kiểm tra.

### lab-081-aws-network-firewall-co-ban
- Đường dẫn: `labs/lab-081-aws-network-firewall-co-ban/content/lab.md` (24 769 B)
- Mode: console-first, có 1 khối `aws` (cleanup, dùng `network-firewall` và `ec2`).
- Tài nguyên tạo hoặc kiểm tra:
  - ec2: VPC, IGW gắn vào VPC, workload subnet /24, firewall subnet /28
  - network-firewall: firewall và firewall policy rỗng, tạo bằng tùy chọn "Create and associate an empty firewall policy"; lấy ID firewall endpoint `vpce-…`
  - ec2: 3 route table:
    - firewall RT: 0.0.0.0/0 → IGW
    - workload RT: 0.0.0.0/0 → firewall endpoint
    - IGW edge RT: gắn edge association vào IGW, route CIDR workload → firewall endpoint
- Không có rule group, EC2 hay traffic kiểm tra.
- Ngoài registry: không có (network-firewall, ec2).
- Khó giả lập:
  - Firewall endpoint phải xuất hiện trong `SyncStates` theo AZ, và dùng được làm target route (route kiểu GWLB/VPC endpoint).
  - Edge association của route table với IGW.
  - Thời gian provisioning 3–5 phút.
  - Lab không kiểm tra lọc traffic thật.

## Kết luận nhanh

- Cả 7 lab chỉ dùng các dịch vụ đã có trong registry: ec2, s3, iam, ssm, dynamodb, route53, elbv2, cloudfront, globalaccelerator và network-firewall. Không cần thêm service mới.
- Lab nào cũng thuần console-first và chỉ có CLI ở script dọn dẹp. Nếu dự án cần lệnh dựng tài nguyên thì phải tự viết.
- Theo mức khó giả lập, xếp từ khó nhất:
  - 060: cache CloudFront thật và anycast IP
  - 051: phân giải DNS alias và TestDNSAnswer
  - 057: data plane của ALB
  - 041 và 042: route prefix list và `aws:sourceVpce`
  - 081 và 065: chỉ kiểm tra cấu hình hoặc trạng thái
- Phần nội dung cần caveat: lab 042 nói DynamoDB không có interface endpoint, điều này đã lỗi thời. Lab 057 và 060 có kịch bản rộng hơn các bước thực hành, cụ thể là `tg-search` và failover sang Tokyo không được tạo.

## Câu hỏi còn mở
- Có nên chuyển các bước console thành CLI để đưa vào builder, hay giữ console-first và chỉ chấm theo trạng thái tài nguyên?
- Với lab 051 và 060, có chấp nhận các bước kiểm tra cần mạng hoặc DNS thật là bước "optional/caveat" không?
