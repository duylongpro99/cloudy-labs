# Scout: labaws.site nhóm D (DVA) — 6 lab

Ngày: 2026-11-01 (Asia/Saigon). Nguồn: trang lab gated trên https://labaws.site, đọc bằng Chrome đã đăng nhập (tab riêng, đã đóng). Không gọi fetch/XHR, không bấm tải Markdown hay nút nào khác. Nội dung dưới đây chỉ là tóm tắt, không chép lại văn bản lab.

Đếm "khối aws" = số khối code có rào ``` chứa ít nhất một lệnh `aws <service>`.

## Tổng quan

| Lab | Đã lưu | Kích thước | Chế độ | Khối code / khối aws |
| --- | --- | --- | --- | --- |
| lab-05 (STS tại Edge) | **KHÔNG** (bị hook chặn) | — | console-first + mã SDK | 8 / 1 (chỉ cleanup) |
| lab-100 (API caching) | có | 24 028 B | console-first (+ curl) | 7 / 1 (chỉ cleanup) |
| lab-102 (CodeArtifact) | có | 27 040 B | mixed | 10 / 2 |
| lab-103 (Kinesis backoff) | có | 25 622 B | SDK code (boto3) + console | 9 / 1 (chỉ cleanup) |
| lab-27 (SigV4) | có | 20 939 B | SDK/code thuần (Python urllib) | 7 / 1 (chỉ cleanup) |
| lab-66 (Step Functions Wait) | có | 23 808 B | mixed | 9 / 3 |

Đường dẫn đã lưu: `/Users/onedayin20902/personal/agent/aws-hands-on-labs/labs/<slug>/content/lab.md` (thư mục `content/` đã được gitignore, xác nhận bằng `git check-ignore`).

## Chi tiết từng lab

### lab-05-lay-aws-sts-credentials-dong-tai-edge-cho-frontend-bang-cloudfront-va-lambda-at-edge
- Đã lưu: **không**. Hook `.claude/hooks/privacy-block.cjs` chặn Write vì đường dẫn khớp mẫu `/credentials/i` (do slug chứa chữ "credentials"). Theo quy tắc, không lách bằng Bash; trang đã đọc được đầy đủ, cần người dùng chấp thuận rồi mới lưu.
- Chế độ: console-first; có 1 hàm Lambda Node.js 20 (SDK v3 `@aws-sdk/client-sts`); CLI chỉ dùng cho cleanup.
- Tài nguyên tạo/kiểm chứng: S3 bucket ở ap-southeast-2 (chặn public, upload index.html); IAM role có trust cho `lambda.amazonaws.com` + `edgelambda.amazonaws.com`, inline policy `sts:AssumeRole`, gắn AWSLambdaBasicExecutionRole; Lambda ở us-east-1 + publish version 1; CloudFront distribution với origin S3 qua OAC, viewer-request Lambda@Edge association, cache policy CachingOptimized; cập nhật bucket policy cho OAC; kiểm chứng qua tên miền CloudFront và CloudWatch Logs ở region edge (log group `/aws/lambda/us-east-1.<fn>`).
- Dịch vụ ngoài registry: **sts** — lab xoay quanh `sts:AssumeRole` (quyền IAM + SDK `AssumeRoleCommand`), nhưng lệnh gọi trong code mẫu bị comment out; thực tế hàm chỉ gắn header. Ngoài ra chỉ là IAM/S3/Lambda/CloudFront/Logs (đều có trong registry).
- Khó giả lập: Lambda@Edge (bắt buộc us-east-1, version số, replicate ra edge, log ở region gần người dùng), CloudFront OAC + thời gian deploy distribution, hành vi viewer-request thực.

### lab-100-tang-toc-phan-hoi-api-thong-ke-cong-cong-bang-api-caching-tren-api-gateway
- Chế độ: console-first; kiểm thử bằng `curl`; CLI chỉ ở cleanup (`apigateway get-rest-apis/delete-rest-api`, `lambda delete-function`, `logs delete-log-group`).
- Tài nguyên: Lambda Python 3.11 (sleep 0.5s, trả `last_updated_at`); REST API Regional, resource `/statistics`, method GET, Lambda proxy integration; deployment + stage `prod`; stage cache `cacheClusterEnabled` 0.5 GB, TTL 86400s, mã hóa cache; theo dõi trạng thái cache CREATE_IN_PROGRESS → AVAILABLE; flush entire cache; kiểm tra CloudWatch Logs chỉ có 1 lần invoke.
- Dịch vụ ngoài registry: không có.
- Khó giả lập: caching thật (cache hit không gọi Lambda, `last_updated_at` không đổi), độ trễ ms, thời gian cấp phát cache cluster 3–4 phút, flush cache, chi phí theo giờ.

### lab-102-quan-ly-va-tich-hop-thu-vien-java-tap-trung-trong-codepipeline-bang-aws-codeartifact
- Chế độ: mixed — console cho domain/repo/role/pipeline/rule; CLI cho publish (`codeartifact get-authorization-token`, `publish-package-version` format maven) và cleanup.
- Tài nguyên: CodeArtifact domain + repository (Maven, không upstream); IAM role cho EventBridge với `codepipeline:StartPipelineExecution` (customer-managed policy); CodePipeline (source S3 `source.zip` + build CodeBuild, bỏ deploy) và CodeBuild project (buildspec chỉ echo); S3 bucket nguồn; EventBridge rule pattern `aws.codeartifact` / "CodeArtifact Package Version State Change" lọc domain/repo/package/operation, target CodePipeline; publish package version 1.1.0; kiểm chứng pipeline được kích hoạt.
- Dịch vụ ngoài registry: **sts** chỉ trong cleanup (`sts get-caller-identity` lấy account ID). Còn lại (codeartifact, codepipeline, codebuild, events, iam, s3) đều có.
- Lưu ý nội dung: event pattern dùng `packageName` "com.corp.payment.core" trong khi publish dùng namespace `com.corp.payment` + package `core` — có thể không khớp event thật; mã cleanup có account ID cứng của tác giả làm fallback.
- Khó giả lập: phát sự kiện CodeArtifact → EventBridge → khởi chạy pipeline, chạy CodeBuild thật, auth token CodeArtifact.

### lab-103-xu-ly-provisionedthroughputexceeded-tren-kinesis-bang-exponential-backoff-va-kcl
- Chế độ: SDK code — script Python boto3 `put_records` với exponential backoff + full jitter; console cho tạo stream/resharding/IAM; CLI chỉ ở cleanup (`kinesis delete-stream`, `wait stream-not-exists`, `iam delete-policy`).
- Tài nguyên: Kinesis data stream Provisioned 1 shard → `UpdateShardCount` lên 2 shard (console); IAM customer-managed policy (PutRecord(s), DescribeStream(Summary), ListShards, UpdateShardCount); xem metric CloudWatch WriteProvisionedThroughputExceeded / IncomingRecords.
- Dịch vụ ngoài registry: **sts** chỉ ở cleanup (`get-caller-identity`). Slug nhắc "KCL" nhưng nội dung không dùng KCL (không có DynamoDB lease table).
- Lưu ý nội dung: batch 1200 record vượt giới hạn 500 record/lần gọi của PutRecords, nên lần gọi đầu thực tế sẽ lỗi validation thay vì throttle một phần như lab mô tả.
- Khó giả lập: throttling theo shard (1 MB/s, 1000 rec/s), lỗi một phần `FailedRecordCount`, thời gian resharding, timing backoff, metric CloudWatch.

### lab-27-ky-va-xac-thuc-request-aws-bang-signature-version-4-qua-http-authorization-header
- Chế độ: SDK/code — hai script Python thuần (hashlib/hmac/urllib) tự ký SigV4: header `Authorization` và presigned URL (`X-Amz-Signature`, UNSIGNED-PAYLOAD); console cho S3/IAM; CLI chỉ ở cleanup.
- Tài nguyên: S3 bucket private + object `secure-data.txt`; IAM user gắn AmazonS3ReadOnlyAccess; **tạo access key IAM user** (long-lived) để nhúng vào script; kiểm chứng GET object trả 200 bằng cả hai cách.
- Dịch vụ ngoài registry: **sts** chỉ ở cleanup (`get-caller-identity`).
- Khó giả lập: emulator phải kiểm tra chữ ký SigV4 thật (canonical request, RequestTimeTooSkewed, SignatureDoesNotMatch), presigned URL hết hạn; virtual-hosted-style host `<bucket>.s3.<region>.amazonaws.com`. Lab cũng yêu cầu tạo và dán access key — điểm nhạy cảm về bảo mật nếu chuyển thành bài thực hành tự động.

### lab-66-dieu-phoi-rate-limit-cua-api-ben-thu-ba-bang-aws-step-functions-wait-state
- Chế độ: mixed — console là chính; CLI `stepfunctions start-execution`, `get-execution-history` (lọc WaitStateEntered/Exited) và script cleanup.
- Tài nguyên: 2 IAM role (Lambda basic execution; Step Functions trust `states.amazonaws.com` + policy `lambda:InvokeFunction`); Lambda Python 3.12 arm64 giả lập rate-limit; state machine Standard với Task (lambda:invoke, OutputPath $.Payload), Choice, Wait `SecondsPath: $.wait_seconds`, Pass, Succeed; execution input `{"iteration":1}` → Succeeded sau ~20s; kiểm tra execution history.
- Dịch vụ ngoài registry: **sts** trong `start-execution` (lấy account ID trong ARN) và cleanup (`get-caller-identity`).
- Khó giả lập: Wait state theo thời gian thực (2×10s), timestamp event history khớp đúng 10s, loop Choice/Pass, tích hợp `lambda:invoke` optimized.

## Dịch vụ ngoài registry (tổng hợp)

- **sts**: lab-05 (AssumeRole — trọng tâm khái niệm, nhưng code thực thi bị comment), lab-102 / lab-103 / lab-27 / lab-66 (GetCallerIdentity, chỉ để lấy account ID trong cleanup hoặc dựng ARN).
- Không lab nào dùng GetSessionToken, AssumeRoleWithWebIdentity, X-Ray, SES hay Firehose.
- Không có dịch vụ mới nào khác ngoài sts.

## Hành vi khó với emulator cục bộ

- Lambda@Edge + CloudFront (lab-05): region bắt buộc, version, replicate edge, log theo edge region.
- Cache API Gateway (lab-100): cache hit/miss, TTL, flush, thời gian cấp phát.
- Throttling Kinesis theo shard + resharding (lab-103).
- Xác thực chữ ký SigV4 thật và presigned URL (lab-27).
- Sự kiện CodeArtifact → EventBridge → CodePipeline/CodeBuild (lab-102).
- Timing Wait state Step Functions (lab-66).

## Câu hỏi còn mở

1. Có chấp thuận lưu lab-05 không? Hook privacy chặn vì slug chứa "credentials"; cần người dùng duyệt (hoặc đổi tên thư mục).
2. Lab-102 (lệch packageName/namespace) và lab-103 (batch 1200 > giới hạn 500) có lỗi nội dung; xử lý thế nào khi chuyển thành lab của dự án?
