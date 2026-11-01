# Scout: labaws.site nhóm B (RDS + Storage)

Ngày: 2026-11-01 (Asia/Saigon). Nguồn: trang lab có đăng nhập trên https://labaws.site/labs/<slug>, đọc bằng Chrome của người dùng (chỉ navigate, get_page_text và script đánh dấu DOM cục bộ `md-mark.js`). Không gọi fetch/XHR, không bấm tải về, không bấm share/submit.

Cả 6 trang đều tải được, không trang nào 404 hay còn bị chặn. Nội dung lưu làm markdown cá nhân trong `labs/<slug>/content/lab.md` (thư mục này bị gitignore). Báo cáo này chỉ tóm tắt, không chép lại nội dung lab.

Cách đếm: "khối có `aws `" là số fenced code block chứa ít nhất một dòng lệnh AWS CLI. Nếu một sơ đồ ASCII có ghi lệnh `aws` thì được tách ra ghi chú riêng, vì đó không phải lệnh để chạy.

## Tổng quan

| Lab | Kích thước | Số khối code | Khối có lệnh `aws` (thực chạy) | Chế độ |
| --- | --- | --- | --- | --- |
| lab-013 | 25,493 B | 7 | 3 (+1 sơ đồ ASCII) | console-first |
| lab-014 | 22,066 B | 12 | 3 (+1 sơ đồ ASCII) | mixed (console + CLI/psql trên EC2) |
| lab-059 | 26,377 B | 5 | 1 (chỉ script dọn dẹp) | console-first |
| lab-079 | 27,059 B | 7 | 1 (chỉ script dọn dẹp) | console-first |
| lab-047 | 22,493 B | 8 | 4 | mixed (console dựng hạ tầng, CLI để kiểm chứng) |
| lab-094 | 31,465 B | 12 | 3 | mixed (console dựng, CLI + Athena SQL để kiểm chứng) |

Các service AWS có xuất hiện nhưng KHÔNG nằm trong registry:
- **sts**: 4/6 lab (013, 014, 047, 079) dùng `aws sts get-caller-identity`, chủ yếu trong script dọn dẹp hoặc khi đặt biến. Lab-014 còn nêu STS AssumeRole trong luồng sinh token.
- **rds-db**: ở lab-014 (và nhắc tới trong lab-079), đây là namespace của IAM action `rds-db:connect`, không phải một service API riêng. Registry nên mô hình nó thành một phần của IAM/RDS.
- Không có service mới nào khác thực sự được tạo. Một số service chỉ được nhắc tới mà không dùng: Organizations Backup Policy (059), Resource Groups Tagging API (059, chỉ trong bảng trace), EFS (094, chỉ trong sơ đồ), RDS Proxy (014/079, chỉ là gợi ý).

## Chi tiết từng lab

### lab-013-luu-database-secret-trong-secrets-manager
- File: `/Users/onedayin20902/personal/agent/aws-hands-on-labs/labs/lab-013-luu-database-secret-trong-secrets-manager/content/lab.md` (25,493 B)
- Chế độ: console-first. Có 3 khối CLI thực: `describe-secret`, `get-secret-value` và script dọn dẹp. Có thêm 1 khối Python boto3 + psycopg2.
- Tài nguyên tạo hoặc kiểm chứng:
  - Secrets Manager secret `lab-013-rds-secret`, loại RDS credentials, mã hoá bằng KMS mặc định `aws/secretsmanager`.
  - Bật rotation 30 ngày, kèm hàm Lambda xoay vòng `lab-013-rotation-lambda` do console tự sinh từ template. Lab bấm "Rotate secret now" rồi kiểm tra version stage AWSCURRENT.
  - IAM customer policy chỉ cho `secretsmanager:GetSecretValue`/`DescribeSecret` trên ARN của secret, cùng IAM role EC2 `lab-013-ec2-role` (gắn thêm AmazonSSMManagedInstanceCore).
  - RDS PostgreSQL `lab-013-db` (db.t4g.micro). Đây là điều kiện tiên quyết: lab chỉ chọn DB có sẵn, không có bước tạo DB.
- Service ngoài registry: sts (khi dọn dẹp).
- Phần emulator local khó tái hiện:
  - Rotation thật cần Lambda từ template của AWS (SAR) đăng nhập vào Postgres thật, chạy ALTER USER rồi test kết nối.
  - Chiến lược alternating users (multi-user).
  - Đoạn Python kết nối DB thật bằng psycopg2.
  - Lambda trong VPC cần endpoint hoặc NAT để tới Secrets Manager.

### lab-014-iam-database-authentication
- File: `/Users/onedayin20902/personal/agent/aws-hands-on-labs/labs/lab-014-iam-database-authentication/content/lab.md` (22,066 B)
- Chế độ: mixed. RDS và IAM policy làm trên console. Sinh token và kết nối làm bằng CLI/psql trên EC2 client. Có 3 khối CLI thực: `describe-db-instances`, `generate-db-auth-token` và script dọn dẹp. Có thêm khối psql/SQL và curl tải CA bundle.
- Tài nguyên tạo hoặc kiểm chứng:
  - RDS PostgreSQL `lab-014-db` với `IAMDatabaseAuthenticationEnabled=true`, `PubliclyAccessible=false`. Lab đọc `DbiResourceId`.
  - DB user `db_iam_user` được GRANT `rds_iam`.
  - IAM policy `lab-014-rds-iam-auth-policy` cho `rds-db:connect` trên ARN `arn:aws:rds-db:...:dbuser:<DbiResourceId>/db_iam_user`, gắn vào role EC2 `lab-014-ec2-app-role`.
  - Security group DB `lab-014-db-sg` mở cổng 5432 từ SG của client. DB subnet group cũng được nêu.
- Service ngoài registry: sts. `rds-db` là IAM action namespace.
- Phần emulator local khó tái hiện:
  - Token SigV4 15 phút được RDS kiểm qua IAM (PAM).
  - Bắt buộc TLS (sslmode=require) với RDS CA.
  - Đăng nhập Postgres thật bằng token.
  - Hết hạn token nhưng phiên đã mở vẫn sống.
  - Cần một EC2 client nằm trong VPC.
  - Có một lỗi nhỏ trong nội dung lab: script dọn dẹp dựng ARN dạng `arn:aws:iam://`, sai cú pháp.

### lab-059-aws-backup-cho-rds-va-aurora
- File: `/Users/onedayin20902/personal/agent/aws-hands-on-labs/labs/lab-059-aws-backup-cho-rds-va-aurora/content/lab.md` (26,377 B)
- Chế độ: console-first. Chỉ có 1 khối CLI là script dọn dẹp. Có 1 khối JSON key policy.
- Tài nguyên tạo hoặc kiểm chứng:
  - 2 KMS CMK đối xứng: `lab-059-backup-kms-syd` ở ap-southeast-2 và `lab-059-backup-kms-sin` ở ap-southeast-1. Key policy cho phép `backup.amazonaws.com`.
  - Backup vault `lab-059-enterprise-vault-syd` có Vault Lock (Governance mode, min 1 ngày, max 90 ngày) và DR vault `lab-059-dr-vault-sin`.
  - Backup plan `lab-059-plan-enterprise-daily`: cron 12 giờ, retention 90 ngày, copy action cross-region sang Singapore giữ 30 ngày. Backup selection gán theo tag `BackupPlan=EnterpriseDaily`, dùng service role mặc định.
  - RDS PostgreSQL `lab-059-source-db` gắn tag trên.
  - Chạy on-demand backup job, kiểm tra recovery point, rồi chạy restore job ra `lab-059-restored-db`.
- Service ngoài registry: không có. Lab này không gọi sts. Aurora có trong tiêu đề nhưng lab chỉ tạo RDS instance. Organizations Backup Policy chỉ được nhắc tới, không có bước dùng.
- Phần emulator local khó tái hiện:
  - Thời gian chạy backup job và restore job (tạo DB thật từ snapshot).
  - Copy cross-region kèm re-encrypt KMS.
  - Vault Lock chặn xoá recovery point.
  - Cron schedule và start window.
  - Gán tài nguyên theo tag.

### lab-079-lambda-ket-noi-rds-an-toan
- File: `/Users/onedayin20902/personal/agent/aws-hands-on-labs/labs/lab-079-lambda-ket-noi-rds-an-toan/content/lab.md` (27,059 B)
- Chế độ: console-first. Chỉ có 1 khối CLI là script dọn dẹp. Có 1 khối code Lambda Python (pg8000) và các khối JSON policy và output.
- Tài nguyên tạo hoặc kiểm chứng:
  - RDS PostgreSQL private `lab-079-db` (PubliclyAccessible=No).
  - Secrets Manager secret `lab-079-rds-secret`.
  - 2 EC2 security group: `lab-079-lambda-sg`, và `lab-079-db-sg` có inbound 5432 tham chiếu theo SG id.
  - IAM role `lab-079-lambda-vpc-role`, gắn managed `AWSLambdaVPCAccessExecutionRole` và inline/customer policy `lab-079-lambda-read-secret`.
  - Lambda `lab-079-claims-processor` (Python 3.12, chạy trong VPC trên 2 private subnet, timeout 15s, 256MB).
  - Kiểm chứng gồm: invoke test trả 200, ghi bảng trong Postgres, và log CloudWatch phân biệt cold start với warm start.
- Service ngoài registry: sts.
- Phần emulator local khó tái hiện:
  - Lambda chạy thật và kết nối Postgres thật qua TLS (thư viện pg8000 phải đóng gói thì mới chạy được).
  - ENI Hyperplane và VPC networking.
  - Truy cập Secrets Manager từ private subnet, cần VPC endpoint hoặc NAT.
  - Hành vi tái dùng kết nối giữa cold start và warm start.

### lab-047-cross-region-replication-voi-kms
- File: `/Users/onedayin20902/personal/agent/aws-hands-on-labs/labs/lab-047-cross-region-replication-voi-kms/content/lab.md` (22,493 B)
- Chế độ: mixed. Dựng hạ tầng trên console. Kiểm chứng bằng CLI qua 4 khối: `s3 cp --sse aws:kms`, 2 lần `s3api head-object` và script dọn dẹp.
- Tài nguyên tạo hoặc kiểm chứng:
  - 2 KMS CMK: `alias/lab-047-src-key` ở ap-southeast-2 và `alias/lab-047-dst-key` ở us-east-1. Key policy của key đích phải cho phép role.
  - 2 bucket S3 có versioning: `lab-047-kms-src-<acct>` ở ap-southeast-2 và `lab-047-kms-dst-<acct>` ở us-east-1.
  - IAM role `lab-047-kms-crr-role` (trust s3) với policy `lab-047-kms-crr-policy`: quyền replication S3, `kms:Decrypt` trên key nguồn, `kms:Encrypt`/`GenerateDataKey` trên key đích.
  - Replication rule có bật "replicate KMS-encrypted objects" và chỉ định ReplicaKmsKeyID.
  - Kiểm chứng: object nguồn có `ReplicationStatus` chuyển từ PENDING sang COMPLETED, object đích là REPLICA và `SSEKMSKeyId` là ARN key đích.
- Service ngoài registry: sts. Script dọn dẹp cũng cần `jq` ở máy local.
- Phần emulator local khó tái hiện:
  - Replication bất đồng bộ cross-region, độ trễ 20–30 giây, cần chuyển trạng thái PENDING → COMPLETED/REPLICA.
  - Re-encrypt bằng key ở region khác.
  - Đánh giá key policy của KMS ở cả hai đầu.

### lab-094-centralized-storage-logging-va-cloudtrail-data-events
- File: `/Users/onedayin20902/personal/agent/aws-hands-on-labs/labs/lab-094-centralized-storage-logging-va-cloudtrail-data-events/content/lab.md` (31,465 B)
- Chế độ: mixed. Dựng trên console. Có 3 khối CLI: upload/xoá giả lập, thử xoá object bị lock và script dọn dẹp. Ngoài ra có DDL/SQL Athena, filter pattern và bucket policy.
- Tài nguyên tạo hoặc kiểm chứng:
  - Bucket log trung tâm `lab-094-central-log-archive-sydney-<rand>`: versioning, Object Lock bật khi tạo bucket, default retention Compliance 1 ngày, bucket policy cho CloudTrail kèm deny khi không dùng TLS.
  - Bucket dữ liệu `lab-094-financial-data-sydney-<rand>`, bật server access logging về bucket trung tâm với prefix riêng.
  - CloudTrail trail `lab-094-central-trail`: management events, S3 data events cho riêng bucket dữ liệu, log file validation, gửi sang CloudWatch Logs group `/aws/cloudtrail/lab-094-storage-audit` qua role `lab-094-cloudtrail-cw-role`.
  - Metric filter `lab-094-filter-s3-access-denied` (namespace CustomSecurityMetrics) và alarm `lab-094-alarm-s3-unauthorized-access` (>=3 trong 5 phút) gửi tới SNS topic `lab-094-soc-alerts` có subscription email.
  - Athena database `lab_094_storage_audit_db` và bảng external `cloudtrail_logs` (CloudTrailInputFormat).
  - Kiểm chứng: query lọc DeleteObject/AccessDenied, và xoá object bị Object Lock phải lỗi.
- Service ngoài registry: không có. EFS chỉ có trong sơ đồ, không có bước nào dùng.
- Phần emulator local khó tái hiện:
  - CloudTrail phát data event thật và giao log vào S3 lẫn CloudWatch (độ trễ 5–15 phút).
  - Metric filter tạo ra datapoint và alarm đổi trạng thái.
  - SNS gửi email và cần xác nhận subscription.
  - Athena chạy SerDe trên file log gzip.
  - Object Lock Compliance chặn xoá trong thời hạn retention, khiến bucket log không xoá được trong ít nhất 1 ngày. Script dọn dẹp cố ý giữ lại bucket này.
  - Có một điểm lệch trong nội dung lab: kịch bản 1 nói là "không có quyền" nhưng lại chạy cùng identity vừa upload thành công.

## Ghi chú vận hành
- Mỗi trang cần 2 lần đọc: lần get_page_text đầu ngay sau navigate trả về rỗng vì body nạp bất đồng bộ, lần sau có đủ nội dung.
- Tab group của MCP bị đổi giữa phiên vì agent khác dùng chung trình duyệt. Tab đầu tiên tôi tạo (1677954483) và tab thứ hai (1677954489) đều rơi ra khỏi group hiện tại, nên `tabs_close_mcp` từ chối đóng. Hai tab này có thể vẫn còn mở trong Chrome. Tôi không đụng vào tab của agent khác.

## Câu hỏi chưa giải quyết
- Registry có nên thêm `sts`, ít nhất là `GetCallerIdentity`, vì 4/6 lab dùng?
- Lab-013 và lab-014 cần một RDS hoặc EC2 client có sẵn, lab không có bước tạo. Builder có dựng sẵn các tài nguyên tiên quyết này không?
