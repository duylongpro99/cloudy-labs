# Coverage trên 24 lab labaws thật (2026-11-01)

Báo cáo scout từng nhóm: [network](scout-261101-1508-labaws-network.md), [rds-storage](scout-261101-1508-labaws-rds-storage.md), [soa](scout-261101-1508-labaws-soa.md), [dva](scout-261101-1508-labaws-dva.md). Nội dung lab nằm ở `labs/<slug>/content/lab.md` (gitignore). Bốn lab DVA có slug dài hơn 81 ký tự nên được đổi tên thành `dva-lab-100-api-gateway-caching`, `dva-lab-102-codeartifact-codepipeline`, `dva-lab-103-kinesis-backoff` và `dva-lab-27-sigv4`. Lab-05 (STS, Lambda@Edge) không được lưu vì hook bảo mật chặn mọi đường dẫn có chữ "credentials".

## Kết luận

- **Không cần thêm service mới vào registry.** Mọi service mà 24 lab dùng đều đã có kind. Ngoại lệ duy nhất là `sts`, mà coverage đã coi là service không có tài nguyên (`NO_RESOURCES`). Các lab gọi `get-caller-identity` để lấy account ID; lab-05 xoay quanh AssumeRole.
- **Kết quả `labctl coverage`:** 20 lab `ready-with-caveats`, 2 lab `gap`, 1 lab `blocked`. Cả 3 lab không đạt đều vướng ở script dọn dẹp hoặc ở lỗi của chính công cụ coverage, không phải ở phần chính của lab.
- **Kết quả này không đáng tin bằng con số trên.** 22/24 lab là console-first: lệnh `aws` duy nhất trong lab là script dọn dẹp. Coverage vì thế đoán kind chủ yếu từ văn xuôi, và việc đoán đó vừa báo thừa vừa bỏ sót (xem bên dưới).

## Bảng kết quả

| Lab | Kết luận | Ghi chú |
| --- | --- | --- |
| lab-041 S3 gateway endpoint | ready-with-caveats | Điều kiện `aws:sourceVpce` cho ra 403 chưa được kiểm |
| lab-042 DynamoDB gateway endpoint | ready-with-caveats | |
| lab-051 Route 53 public zone | ready-with-caveats | Floci không trả lời DNS cho public zone (`route53-private-dns-only`) |
| lab-057 ALB path routing | ready-with-caveats | |
| lab-060 CloudFront + Global Accelerator | ready-with-caveats | Thiếu kind cho cache policy, OAC, endpoint group; cache Hit/Miss không giả lập được |
| lab-065 Transit Gateway | **gap** | Script dọn dẹp dùng waiter `transit-gateway-attachment-deleted`, waiter này không tồn tại trong AWS CLI (lỗi nội dung lab) |
| lab-081 Network Firewall | ready-with-caveats | control-plane-only |
| lab-013 Secrets Manager | ready-with-caveats | Rotation thật cần Lambda đổi mật khẩu Postgres |
| lab-014 IAM DB auth | **gap** | Coverage hiểu sai `aws rds generate-db-auth-token`: đây là lệnh CLI tính token cục bộ, không phải API |
| lab-047 CRR + KMS | ready-with-caveats | Floci lưu rule replication nhưng không copy object |
| lab-059 AWS Backup | ready-with-caveats | |
| lab-079 Lambda → RDS | ready-with-caveats | |
| lab-094 CloudTrail data events | ready-with-caveats | |
| lab-02 ASG đa AZ | ready-with-caveats | Floci không thay instance unhealthy (`asg-no-elb-health`) |
| lab-15 ACM + ALB | ready-with-caveats | |
| lab-62 Logs metric filter | ready-with-caveats | Chưa có kind cho log stream |
| lab-64 EventBridge EC2 state | ready-with-caveats | |
| lab-76 Config required-tags | ready-with-caveats | Bỏ sót kind `config-rule` (xem bên dưới) |
| lab-81 CloudFormation mapping | ready-with-caveats | |
| lab-93 SQS DLQ | ready-with-caveats | |
| dva-lab-100 API caching | ready-with-caveats | **Thực ra phải là blocked hoặc caveat:** Floci không có `FlushStageCache`, nhưng bước flush làm trên console nên coverage không thấy |
| dva-lab-102 CodeArtifact | **blocked** | Floci không có `DeletePackageVersions` và `ListPackageVersions`; lệnh bị chặn nằm ở script dọn dẹp (dòng 491), nên có thể đánh dấu `--optional` |
| dva-lab-103 Kinesis | ready-with-caveats | Lab là mã boto3; throttling theo shard không giả lập |
| lab-66 Step Functions Wait | ready-with-caveats | |

## Lỗi của công cụ coverage

1. **Báo thừa kind từ từ đơn chung chung.** Từ điển thuật ngữ gồm cả nhãn kind lẫn danh từ trong `view.actions`, nên một từ đơn đủ để gắn kind. Ví dụ: "api" thành `apigateway-http-api` (19/24 lab), "application" thành `beanstalk-application` và `codedeploy-application`, "environment" (tên tag) thành `beanstalk-environment`, "key" thành `kms-key`, "image" thành `ecr-repository`, "firewall" thành `network-firewall`, "user" và "group" thành `iam-user` và `iam-group`. Hệ quả là danh sách caveat của mỗi lab dài gấp đôi, lẫn caveat của service lab không hề dùng.
2. **Bỏ sót kind khi văn xuôi chen thêm từ.** Lab-76 viết "Config Managed Rule", không có cụm "Config Rule" đứng liền, nên `config-rule` (tài nguyên chính của lab) không được nhận ra. Từ "rule" lại bị gán cho `event-rule` và `listener-rule`.
3. **Lệnh CLI không gọi API.** `rds generate-db-auth-token` bị coi là API không tồn tại và gây `gap`. Cùng loại còn có `eks get-token`, `eks update-kubeconfig`, `ecr get-login-password` (gọi `GetAuthorizationToken`), `codeartifact login` (gọi `GetAuthorizationToken`), `cloudformation package` và `cloudformation deploy`, `deploy push`. Hiện chỉ `configure`, `help`, `history`, `cli` và `sso login/logout` được coi là lệnh cục bộ.
4. **Thao tác console không được kiểm với API của Floci.** Ví dụ: bước "Flush cache" trên console của dva-lab-100 cần `FlushStageCache`, API mà Floci không có, nhưng coverage vẫn báo lab chạy được.

## Kind còn thiếu trong service đã có (Floci có API)

| Kind đề xuất | Service | Lab cần | API trên Floci |
| --- | --- | --- | --- |
| log stream | logs | lab-62, dva-lab-100 | CreateLogStream, DescribeLogStreams, PutLogEvents có |
| cache policy, origin request policy, origin access control | cloudfront | lab-060 | Create* có |
| endpoint group (và listener) | globalaccelerator | lab-060 | CreateEndpointGroup, CreateListener có |
| transit gateway route (và propagation) | ec2 | lab-065 | CreateTransitGatewayRoute, EnableTransitGatewayRouteTablePropagation có |
| API key, usage plan | apigateway | dva-lab-100 | CreateApiKey, CreateUsagePlan có; FlushStageCache **không** |
| IAM access key | iam | dva-lab-27, lab-013 | CreateAccessKey, ListAccessKeys có |
| package version | codeartifact | dva-lab-102 | PublishPackageVersion có; List/DeletePackageVersions **không** |

## Đề xuất thứ tự làm

1. Sửa công cụ coverage (mục 1–4 ở trên): lỗi này ảnh hưởng mọi lab, và cả con số 468 `ready-with-caveats` của danh mục.
2. Thêm các kind ở bảng trên, ưu tiên log stream, CloudFront policy/OAC và GA endpoint group vì xuất hiện nhiều nhất.
3. Chọn 1–2 lab console-first (ví dụ lab-93 SQS, lab-81 CloudFormation) để soạn `lab.yaml` và `checks.py` rồi chạy thật end-to-end, như đã làm với lab-001, lab-020 và lab-900.

## Câu hỏi chưa giải quyết

- Lab-05 (STS) có cần lưu không? Cần duyệt hook bảo mật hoặc lưu dưới một tên thư mục khác.
- Với lỗi trong script dọn dẹp (lab-065 waiter không tồn tại, dva-lab-102 thiếu API), nên chốt bằng `labctl coverage --accept --optional <dòng>` hay để nguyên?
- Có giữ các thư mục lab vừa scout trong `labs/` không? Chúng chỉ có `content/` và chưa có `lab.yaml`.
