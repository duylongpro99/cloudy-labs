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
- **`run-instances` bỏ qua `Groups` trong `NetworkInterfaces`**, nên instance rơi vào security group mặc định. Dùng `--subnet-id` và `--security-group-ids` ở cấp trên.
- **Rule inbound trùng vẫn được thêm.** `authorize-security-group-ingress` với rule đã có trả exit 0 và nhân đôi rule; AWS thật trả `InvalidPermission.Duplicate`. Builder tự chặn rule trùng trước khi chạy; checker nên coi một group có rule trùng là bình thường.
- **Key pair bỏ qua tag.** `create-key-pair --tag-specifications` chạy được nhưng `describe-key-pairs` trả `Tags: []`. Đừng tìm key pair của lab theo tag; dùng `KeyName`.
- **Subnet chồng lấn bị từ chối như AWS** (`InvalidSubnet.Conflict`). Trùng tên security group (`InvalidGroup.Duplicate`), trùng tên key pair (`InvalidKeyPair.Duplicate`) và `modify-instance-attribute --groups` cũng giống AWS ([ghi chú kiểm](../plans/261030-1045-m4-builder-lab-07/notes/floci-ec2-ops.md)).
- **Instance không có systemd.** Container instance không chạy init, nên `systemctl enable --now httpd` trong UserData lỗi dù `dnf install httpd` thành công. Cộng với việc IMDS chiếm cổng 80 (xem phần Mạng và IP), UserData kiểu "cài httpd rồi bật service" của trang lab không bao giờ trả trang. UserData trong `builder.userData` của lab (ví dụ lab-900) chạy server bằng `python3 -m http.server` trên từng địa chỉ IPv4. Kiểm ngày 2026-11-01.
- **`HttpTokens=required` được lưu nhưng không được áp.** `describe-instances` trả `MetadataOptions.HttpTokens: required`, nhưng bên trong instance gọi IMDS không token (IMDSv1) vẫn nhận 200. Checker chấm IMDSv2 trên `MetadataOptions`, không thử gọi IMDSv1. Kiểm ngày 2026-11-01.
- **Lần đầu public cổng ứng dụng, Floci pull `alpine/socat` không kèm tag**, khiến Docker kéo về mọi tag. `labctl up` pull sẵn `alpine/socat:latest` để tránh việc này.

### API Floci 2.3.0 không có

Lab cần một trong các API dưới đây ra `blocked` trong `labctl coverage`. Danh sách nằm ở [`catalog-overrides.yaml`](../server/src/cloudy_labs/coverage/catalog-overrides.yaml); bảng theo từng kind ở [coverage.md](coverage.md).

- EC2: `GetConsoleOutput` (trả `UnsupportedOperation`), EBS snapshot (`CreateSnapshot`, `CopySnapshot`), DHCP option set, egress-only internet gateway, placement group, replace root volume task.
- RDS: engine Oracle và SQL Server; read replica và snapshot của MySQL/MariaDB; blue/green deployment.
- CodeCommit, X-Ray, FSx, Storage Gateway, Direct Connect, Site-to-Site VPN không có.
- API Gateway v2: `CreateStage`, `GetStages` và các API integration.

### VPC mở rộng, RDS, S3, Lambda, IAM

- **Có sẵn tài nguyên mặc định như AWS:** default VPC, subnet, route table, NACL, DB subnet group và các AWS prefix list. Instance có root volume và ENI chính. ENI của interface endpoint là `requesterManaged`; cảnh không vẽ nó.
- **NACL và launch template bỏ qua tag** lúc tạo. Tìm chúng theo id hoặc tên, không theo tag.
- **Gateway endpoint không thêm route** vào route table được gắn. Checker kiểm `RouteTableIds` của endpoint, không tìm route prefix list.
- **Aurora chạy trên container MySQL hoặc PostgreSQL thường** và bỏ qua security group cùng cluster parameter group. Multi-AZ và failover chỉ là cờ (caveat `flag-only`): `failover-db-cluster` chỉ đổi `IsClusterWriter` giữa các instance.
- **RDS luôn báo `StorageType` `gp2`**, dù lúc tạo hay modify yêu cầu `gp3` hay `io1` (caveat `rds-storage-type-gp2`). `AllocatedStorage` và `MaxAllocatedStorage` (storage autoscaling) thì được giữ đúng; checker chấm hai giá trị này và để kiểu storage ở mức INFO.
- **S3 báo mã hoá `AES256` và public access block đầy đủ cho mọi bucket**, dù có cấu hình hay không (caveat `s3-default-encryption`). Đừng chấm hai cấu hình này bằng `Get*`; xem lệnh người học đã chạy.
- **Replication của S3 chỉ lưu rule** và không chép object (caveat `control-plane-only`). Chấm theo rule.
- **Floci có bucket nội bộ `awslambda-*`** để giữ code Lambda; cảnh lọc bỏ nó. `ListBuckets` không trả `BucketRegion`, nên collector hỏi `GetBucketLocation` từng bucket.
- **IAM lưu policy nhưng không thực thi** (caveat `iam-not-enforced`). Lab cần `AccessDenied` thật dùng `emulator: moto`.
- AWS CLI tạo NACL entry bằng `--ingress` hoặc `--egress`, không có `--egress false`.
- **Route tới transit gateway mất target.** `create-route --transit-gateway-id` chạy được, nhưng `describe-route-tables` trả route không có `TransitGatewayId`. Phân tích reachability vì vậy báo `route-target-unknown` cho route đó thay vì đoán; fixture ghi lại đặt target trở lại bằng [`patches.yaml`](../server/tests/fixtures/reachability/patches.yaml).
- **Association của TGW route table chỉ thấy qua `describe-transit-gateway-attachments`**, không qua `get-transit-gateway-route-table-associations`.
- **Route tới NAT gateway đã xoá vẫn `active`**; AWS thật chuyển nó sang `blackhole`.
- **`create-network-acl` bỏ qua `TagSpecifications`.** Gắn tag bằng `create-tags` sau khi tạo.

### Giám sát, sự kiện, dữ liệu, cấu hình và mạng tải

Mỗi điểm dưới đây cũng là một caveat trên kind tương ứng trong registry; mã caveat nằm trong ngoặc.

- **CloudWatch không có metric `AWS/*`** (`no-service-metrics`). Alarm trên CPU EC2 hay lỗi Lambda không bao giờ đổi trạng thái. Đẩy số bằng `put-metric-data`, khi đó Floci đánh giá alarm sau khoảng một phút. Hoặc đổi trạng thái bằng `set-alarm-state`. Dashboard nằm theo region, không global (`floci-regional-dashboards`).
- **Floci tự tạo log group `/aws/rds/instance/<id>/error`** cho mọi DB instance (`floci-rds-log-groups`).
- **EventBridge nhận log group làm target nhưng không ghi event vào đó** (`floci-no-logs-target`). Floci giao event mà không assume `RoleArn` của target, rule hay schedule (`floci-target-role-not-assumed`). Scheduler chạy đúng giờ, không có jitter (`floci-schedule-no-jitter`).
- **AWS Backup chỉ mô phỏng.** Job xong sau vài giây và có recovery point, nhưng không chép dữ liệu (`floci-backup-simulated`). Plan không tự chạy theo lịch (`floci-backup-plan-no-schedule`). Selection bỏ `ListOfTags` (`floci-selection-tags-dropped`). Vault lock không được thực thi.
- **CloudFormation không kiểm template.** Stack đạt `CREATE_COMPLETE` cả với loại tài nguyên Floci không có và thuộc tính AWS sẽ từ chối (`cfn-no-validation`). Floci cũng không đòi `CAPABILITY_IAM` (`cfn-capabilities-not-required`). `DeleteStack` để lại tài nguyên stack đã tạo. Bảng DynamoDB tạo qua stack bỏ qua `PAY_PER_REQUEST`.
- **DynamoDB global table chỉ là bản ghi** (`control-plane-only`): region replica không có bảng hay item nào. Key KMS của bảng được trả nguyên như lúc truyền vào (`dynamodb-kms-key-as-given`).
- **KMS giữ `Enabled: true` cho key đang chờ xoá** (`kms-enabled-while-pending`). Chấm theo `KeyState`.
- **Secrets Manager báo xoay vòng xong khi hàm xoay chưa làm gì** (`secret-rotation-not-verified`). Chấm theo `pendingRotation`.
- **SSM Run Command không bao giờ xong** vì instance của Floci không có agent. Parameter Store chạy được; label của version không có trong `DescribeParameters`, nên cảnh không vẽ label.
- **EFS chỉ có control plane** (`efs-no-data-plane`). Không mount được NFS. Mount target luôn có IP `10.0.0.10` và AZ đầu tiên (`efs-fake-ip`). Backup tự động báo `ENABLED` (`efs-backup-default`).
- **ELB chỉ chuyển tiếp HTTP** (`elb-http-only`). Cổng listener không mở ra host. Target group nhận cả instance id không tồn tại (`elb-accepts-unknown-targets`).
- **Auto Scaling không chạy scaling policy** (`control-plane-only`). Floci không thay instance unhealthy (`asg-no-elb-health`) và không gắn tag `aws:autoscaling:groupName` (`asg-no-group-tag`).
- **Route 53 chỉ trả lời DNS cho private hosted zone**, chỉ record A (`route53-private-dns-only`). Tên trả về giữ dấu chấm cuối (`example.com.`).

### Biên, tin nhắn, triển khai, dữ liệu và quản trị

Các service của đợt 3 phần lớn chỉ có control plane: Floci lưu cấu hình nhưng không chạy phần làm việc thật. Mỗi điểm là một caveat trong registry (mã trong ngoặc); bảng đầy đủ theo kind ở [coverage.md](coverage.md). Checker vì vậy chấm cấu hình, không chấm kết quả chạy.

- **Biên.** CloudFront deploy ngay, chuyển tiếp mà không cache (`cloudfront-no-edge-cache`) và bỏ `WebACLId` (`cloudfront-web-acl-dropped`). WAF lưu rule nhưng không lọc, và gắn được vào ARN không tồn tại (`waf-no-inspection`, `waf-accepts-unknown-resources`). ACM cấp chứng chỉ ngay, không cần validate (`acm-issued-at-once`). API Gateway không có API key, usage plan, throttling (`apigateway-no-throttling`). HTTP API không có `CreateStage` và các API integration: tạo bằng quick create (`--target`) (`apigatewayv2-no-create-stage`). Global Accelerator không chuyển traffic (`globalaccelerator-config-only`). Route 53 health check luôn healthy, và `UpdateHealthCheck` thay toàn bộ cấu hình (`route53-health-check-always-healthy`, `route53-health-check-update-replaces`).
- **Cập nhật CloudFront và WAF cần `ETag`/`LockToken`** của lần đọc trước. Contract test vì vậy chỉ tạo và xoá hai loại này. Web ACL scope `CLOUDFRONT` không được vẽ: collector chỉ đọc scope `REGIONAL` của region lab.
- **Tin nhắn.** Subscription email của SNS mãi ở trạng thái chờ xác nhận (`floci-sns-email-pending`). SNS giao tới SQS mà không xét queue policy (`floci-sns-no-queue-policy`). SQS nhận tên queue thay cho URL (`floci-queue-name-as-url`). Kinesis reshard ngay (`floci-kinesis-instant-resharding`). Step Functions không assume role (`floci-sfn-role-not-assumed`).
- **Triển khai.** ECR không scan (`ecr-no-scan`). EKS từ chối `UpdateClusterConfig` và `UpdateClusterVersion` (`eks-no-cluster-update`). Beanstalk nhận mọi `PlatformArn` (`beanstalk-platform-not-checked`) và không có `TagResource`. ECS, CodeBuild, CodeArtifact và CodePipeline dùng tag chữ thường (`key`/`value`), nên tài nguyên của chúng không mang tag lab.
- **Dữ liệu.** DMS (`dms-no-private-ip`, `dms-endpoint-not-tested`, `dms-task-moves-no-data`), DataSync (`datasync-task-never-runs`), Glue crawler (`glue-crawler-finds-no-tables`), Transfer (`transfer-no-file-endpoint`, `transfer-endpoint-sg-dropped`) và RDS event subscription (`rds-event-categories-dropped`, `rds-event-source-ids-dropped`) chỉ có control plane. Query Athena luôn `FAILED` vì container DuckDB không ghi được kết quả ra S3 (`athena-query-results-fail`). ElastiCache chạy Valkey hoặc Memcached thật, nhưng endpoint không mở ra host (`elasticache-endpoint-not-published`). ElastiCache giữ node type cũ khi modify (`elasticache-node-type-ignored`) và không báo security group (`elasticache-no-security-groups`).
- **Quản trị.** CloudTrail chỉ ghi data event S3; nó bỏ log group, role và key KMS, và không kiểm bucket (`cloudtrail-data-events-only`, `cloudtrail-logs-and-key-dropped`, `cloudtrail-bucket-not-checked`). Config không ghi configuration item, không đánh giá rule, và start được khi chưa có delivery channel (`config-no-snapshots`, `config-rules-never-evaluate`, `config-starts-without-channel`). Budgets không có số chi tiêu (`budgets-no-spend`). GuardDuty, Inspector và Security Hub không có finding. Inspector và Security Hub không tắt được sau khi bật. Organizations tạo account ngay mà không có account thật (`organizations-accounts-instant`); cảnh chỉ vẽ OU cấp một dưới root. Landing zone của Control Tower `ACTIVE` ngay mà không dựng gì (`controltower-landing-zone-instant`). Network Firewall không lọc traffic, không kiểm tham chiếu, và tự bật protection khi lệnh tạo bỏ trống (`network-firewall-no-filtering`, `network-firewall-refs-not-checked`, `network-firewall-protection-on`). Rule group bỏ chuỗi `Rules`; truyền rule Suricata trong `RuleGroup.RulesSource.RulesString` (`network-firewall-rules-flag-dropped`).
- **CodeCommit và X-Ray không có trên Floci 2.3.0.** Lab cần chúng ra `blocked`.

### Cổng host

- **Floci nghe ở `4567`, cả trong container (`FLOCI_PORT=4567`) lẫn trên host (`127.0.0.1:4567`)**; người học và checker vẫn dùng `4566`, nơi api-tap chuyển tiếp nguyên vẹn sang Floci ([bảng cổng](labctl.md#cổng)). Label `io.floci.owner` bằng cổng Floci nghe trong container, nên tài nguyên của stack này mang `4567` và không lẫn với một Floci mặc định khác (owner `4566`) trên cùng máy ([ghi chú kiểm](../plans/261029-1006-m2-resource-graph-collector-scene/notes/floci-port-move.md)).

### Vòng đời

- **`docker compose down` để lại container EC2, network VPC và volume.** Các tài nguyên này mang label `io.floci.owner=4567`, trừ container socat chuyển cổng ứng dụng (chỉ có `floci_emulator=floci-aws`; `labctl` nhận chúng qua id instance trong tên `floci-aws-ec2-fwd-i-<id>-<cổng>`). `labctl down` và `labctl up` dọn chúng; xem [ghi chú label](../plans/261028-1104-m1-lab-engine-labctl/notes/floci-labels.md).
- **Container service của Floci không mang owner.** ECR (`floci-aws-ecr-registry`), Athena (`floci-aws-duck`), ElastiCache và EKS chạy trong container Floci tự tạo. Các container này có tên cố định và không có label `io.floci.owner`, nên `labctl` không phân biệt được chúng với container của một Floci khác trên máy. `labctl down` không xoá chúng. Lệnh chỉ liệt kê chúng và in lệnh `docker rm -f` để bạn tự chạy khi không còn Floci nào khác đang chạy.
- **Nâng cấp từ stack dựng trước khi Floci đổi sang cổng 4567:** chạy `labctl down` bằng bản cũ trước khi cập nhật. Tài nguyên còn sót của stack cũ mang owner `4566`, bản mới không dọn chúng vì không phân biệt được với một Floci khác.
- **Reset bằng cách tạo lại container Floci** (khoảng 1 giây, khoảng 5 giây khi còn instance) vì Floci giữ trạng thái trong bộ nhớ. Xoá từng tài nguyên bằng API chậm hơn nhiều (khoảng 19 giây cho Lab 6 + 7).
- **Không restart container Floci khi đã có instance.** Floci tự gắn container của nó vào network của mỗi VPC. Khi restart, Docker gắn lại các network đó, rồi Floci xoá chúng lúc khởi động. Thỉnh thoảng (2 trên 16 lần đo) Docker Desktop khi đó chuyển tiếp cổng host vào endpoint đã mất: container vẫn healthy nhưng cổng host của Floci (`127.0.0.1:4567`, và vì thế cả `4566` qua api-tap) treo. `labctl` vì vậy xoá container rồi tạo mới thay cho restart. Nếu Floci bị restart ngoài `labctl` (ví dụ `docker restart`), chạy `labctl up`; lệnh này phát hiện cổng host không trả lời và tạo lại container.

## moto

- **Không đánh giá `Condition` trong policy IAM.** Lab về IAM không được chấm dựa trên điều kiện.
- **`simulate-principal-policy` và `simulate-custom-policy` trả HTTP 500** (`NotImplementedError`).
- **Request không ký trả HTTP 500 thay vì 403** sau khi hết lượt không xác thực.
- **IAM được thực thi từ lần `start`/`reset` đầu tiên.** Mỗi lần, `labctl` gọi `/moto-api/reset-auth` để mở 3 lượt không xác thực (số này chỉ khai báo ở `providers/aws.py`) rồi dùng hết 3 lượt đó để tạo user `cloudy-labs-admin` có quyền `*` và một access key. Sau đó `test`/`test` bị từ chối (`AuthFailure`). Lệnh của người học (qua `--profile lab` hoặc `labctl env <lab>`, cả hai đọc key bằng `credential_process`) và checker đều ký bằng user này. Lab muốn kiểm `AccessDenied` thì để người học tự tạo user ít quyền; checker có thể dùng `ctx.client(service, credentials=(key, secret))` để hành động như user đó. Trước lần `start` đầu tiên, moto chưa bật IAM.
- **Cổng 5050** trên host, vì cổng 5000 trên macOS bị AirPlay Receiver chiếm. Đó là cổng đi thẳng cho `labctl`, checker và collector; AWS CLI của người học đi qua api-tap-moto ở `4569` để lệnh ghi hiện trên cảnh ([bảng cổng](labctl.md#cổng)).
- **Profile `lab` không chứa key.** Khi lab chạy trên moto, profile gọi `credential_process = labctl credentials moto`, nên sau mỗi `reset` lệnh `--profile lab` tự dùng key mới. Trước lần `start` đầu tiên, lệnh này trả `test`/`test`.
