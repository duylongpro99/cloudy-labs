# Nghiên cứu: Nền tảng mô phỏng dịch vụ đám mây để thực hành AWS (sau đó GCP)

- Thời điểm nghiên cứu: 2026-10-27 10:27 (Asia/Saigon). Mọi nguồn dưới đây truy cập ngày **2026-10-27**.
- Ký hiệu: **[KC]** = đã kiểm chứng trực tiếp từ nguồn trong phiên này; **[SL]** = suy luận/đánh giá của người nghiên cứu, chưa kiểm chứng bằng thực nghiệm.
- Giả định thay cho 3 câu hỏi chưa được trả lời (xem mục 6): ngôn ngữ triển khai là Python; ưu tiên IAM + storage trước rồi mới tới compute/networking; giao diện CLI trước, web để sau.

## Mục lục

1. [Tóm tắt khuyến nghị](#1-tóm-tắt-khuyến-nghị)
2. [Bảng so sánh giải pháp](#2-bảng-so-sánh-giải-pháp)
3. [Dùng có sẵn hay tự xây](#3-dùng-có-sẵn-hay-tự-xây)
4. [Kiến trúc đề xuất](#4-kiến-trúc-đề-xuất)
5. [Lộ trình lab](#5-lộ-trình-lab-11-bài)
6. [Câu hỏi mở và rủi ro](#6-câu-hỏi-mở-và-rủi-ro)
7. [Bước tiếp theo](#7-bước-tiếp-theo)
8. [Nguồn](#8-nguồn)

## 1. Tóm tắt khuyến nghị

Không nên tự viết emulator: phần khó và tốn công nhất (tương thích wire protocol của hàng chục API AWS) đã có sẵn trong các dự án mã nguồn mở MIT/Apache miễn phí. Phương án nên chọn là **phương án A: dùng Floci làm backend AWS chính (MiniStack làm phương án dự phòng thay thế được), và tự xây một lớp "lab engine" mỏng** gồm định nghĩa lab bằng YAML, lệnh `setup/check/reset`, và bộ kiểm tra dựa trên trạng thái (state-based checker) gọi boto3 vào emulator. LocalStack không còn là lựa chọn mặc định: từ 23/03/2026 bản Community đã dừng, bản free (Hobby) cần tài khoản + auth token, chỉ cho phép dùng phi thương mại và không có persistence. moto (Apache-2.0) nên dùng làm công cụ phụ cho các lab IAM cần "Access Denied" thật nhờ cơ chế `INITIAL_NO_AUTH_ACTION_COUNT`, vì các emulator khác hầu như không thực thi IAM policy theo mặc định. Hạn chế cố hữu của mọi emulator là VPC/networking chỉ mô phỏng control plane (tạo route table, security group) chứ không định tuyến gói tin thật, nên lab networking phải chấm điểm bằng cách kiểm tra cấu hình chứ không kiểm tra kết nối. Với GCP, thiết kế một interface `Provider` ngay từ đầu; sau này cắm floci-gcp (cổng 4588) và/hoặc emulator chính thức của Google vào mà không phải sửa lab engine.

## 2. Bảng so sánh giải pháp

### 2.1. Emulator AWS

| Giải pháp | Dịch vụ hỗ trợ (liên quan lộ trình) | Giấy phép / chi phí | Độ đầy đủ | Ghi chú |
|---|---|---|---|---|
| **Floci** (`floci-io/floci`) | IAM, STS, S3, EC2 (+tài nguyên VPC), Lambda, DynamoDB, SQS, SNS, CloudFormation, API Gateway REST+v2, CloudWatch; ~68 dịch vụ theo bên thứ ba [KC] | MIT, miễn phí, không cần tài khoản/token [KC] | Cao ở control plane. EC2 `RunInstances` chạy container Linux thật có SSH key, UserData, IMDS [KC] | Cổng 4566 (drop-in thay LocalStack). Persistence qua `FLOCI_STORAGE_MODE` = memory/persistent/hybrid/wal [KC]. IAM không chặt theo mặc định; S3 có `ENFORCE_AUTH` (mặc định false) [KC]. ~27.2k sao GitHub tại ngày truy cập [KC]. Viết bằng Java/Quarkus [SL từ cấu trúc repo]. Có sibling floci-gcp. |
| **MiniStack** (`ministackorg/ministack`) | IAM, STS, S3, EC2/VPC (route table, NACL, SG, NAT, peering…), Lambda (Python/Node worker pool hoặc Docker), DynamoDB, SQS, SNS, CloudFormation (~100 resource type), API Gateway v1/v2, CloudWatch Logs/Metrics; tự nhận 60+ dịch vụ [KC] | MIT, miễn phí, không cần token [KC] | Cao ở control plane. EC2 mặc định chỉ là bản ghi metadata; muốn có "máy thật" phải đăng ký AMI trỏ tới container [KC] | Cổng 4566, có thể cài qua `pip install ministack` [KC]. `PERSIST_STATE=1` để lưu trạng thái [KC]. IAM enforcement hạn chế, opt-in qua `AUTH=true` [KC]. ~5.0k sao [KC]. Nhiều fork trùng tên trên GitHub — chỉ dùng repo `ministackorg`. Tên dự án trẻ (2026), chưa có đánh giá độc lập. |
| **moto** (`getmoto/moto`) | Rất rộng. Tỉ lệ endpoint đã cài đặt tại ngày truy cập: EC2 232/807, IAM 119/180, S3 77/118, Lambda 46/88, DynamoDB 39/58, STS 7/11, SQS 20/23, SNS 33/42, CloudFormation 33/90, API Gateway 78/124, Logs 52/118, CloudWatch 22/55 [KC, đếm từ IMPLEMENTATION_COVERAGE.md] | Apache-2.0, miễn phí. Bản 5.2.4 phát hành 11/10/2026, Python ≥3.10 [KC] | Trung bình–cao; độ sâu từng dịch vụ không đều | Server mode: `moto_server`, cổng 5000, dashboard `/moto-api/`, API reset trạng thái [KC]. Không mô tả persistence ra đĩa [KC]. Có IAM access control "rất cơ bản" qua `INITIAL_NO_AUTH_ACTION_COUNT` [KC] — đây là điểm mạnh riêng cho lab IAM. Là thư viện Python nên có thể nhúng trực tiếp nếu tự xây. |
| **LocalStack for AWS** (Hobby) | 30+ dịch vụ. Hobby có S3, IAM, STS, EC2, Lambda, DynamoDB, SQS, SNS, CloudFormation, API Gateway REST, CloudWatch; **không** có API Gateway HTTP/WebSocket, RDS, ECS [KC] | Miễn phí nhưng **chỉ phi thương mại**, bắt buộc tài khoản + `LOCALSTACK_AUTH_TOKEN`. Base 39 USD/license/tháng (trả năm), Ultimate 89 USD [KC] | Cao, sản phẩm trưởng thành nhất | Community edition dừng từ 23/03/2026, chỉ còn một image [KC]. Hobby **không có** local persistence và Cloud Pods [KC]. IAM enforcement chỉ có từ gói Base [KC]. CI không giới hạn theo fair-use [KC]. Có kế hoạch gói riêng cho sinh viên đã xác minh [KC]. |

### 2.2. Emulator GCP (chỉ ở mức thiết kế)

| Giải pháp | Dịch vụ | Giấy phép / chi phí | Độ đầy đủ | Ghi chú |
|---|---|---|---|---|
| **Emulator chính thức của Google** (gcloud CLI component) | `gcloud emulators` hiện liệt kê `firestore` (bao gồm chế độ Datastore) và `spanner`; Pub/Sub và Bigtable cài dạng component/container [KC một phần] | Miễn phí, đi kèm gcloud CLI [KC] | Một phần, có danh sách giới hạn rõ ràng | Pub/Sub emulator **không hỗ trợ lệnh `gcloud pubsub` và Console**, chỉ dùng qua client library; không hỗ trợ IAM, UpdateTopic, retention… [KC]. Emulator Datastore cũ đã bị thay bằng `gcloud emulators firestore start --database-mode=datastore-mode` [KC]. Cần JDK [KC]. Không có emulator cho Compute Engine, VPC, IAM. |
| **fake-gcs-server** (`fsouza/fake-gcs-server`) | Cloud Storage JSON API [KC] | BSD-2-Clause, miễn phí [KC] | Một phần | HTTPS mặc định, `-scheme http` để dùng HTTP; signed URL không được kiểm tra chữ ký [KC]. Không xác nhận được tương thích `gcloud storage` [KC: tài liệu không nhắc]. ~1.5k sao. |
| **floci-gcp** (`floci-io/floci-gcp`) | Cloud Storage, Firestore, Datastore, BigQuery, Cloud SQL, Pub/Sub, Cloud Tasks, Scheduler, Secret Manager, KMS, IAM, STS, Cloud Run, Cloud Functions, GKE, Compute Engine (control plane), Logging, Monitoring, Resource Manager… [KC] | MIT, miễn phí, không cần token [KC] | Rộng nhưng dự án nhỏ (~472 sao) | Cổng 4588, gRPC và REST chung cổng; persistence 4 chế độ như Floci [KC]. README nói `gcloud` dùng được qua biến `*_EMULATOR_HOST` [KC là lời README]; điều này mâu thuẫn với việc gcloud không đọc `PUBSUB_EMULATOR_HOST` theo tài liệu chính thức → **cần thử thực tế** [SL]. |

Ghi chú về gcloud: `gcloud config set api_endpoint_overrides/<service> <url>` là cơ chế chính thức để trỏ một nhóm lệnh gcloud sang endpoint khác [KC]. Đây là cách khả thi nhất để chạy lab bằng `gcloud` thay vì chỉ client library [SL].

## 3. Dùng có sẵn hay tự xây

| Phương án | Công sức ban đầu [SL] | Độ chính xác so với dịch vụ thật [SL] | Bảo trì [SL] | Kết luận |
|---|---|---|---|---|
| **A. Dùng emulator có sẵn + tự viết lab engine mỏng** | 1–2 tuần cho engine + 2–4 giờ/lab | Bằng emulator gốc: tốt cho cú pháp CLI/SDK và control plane; IAM và networking yếu | Thấp: emulator do cộng đồng cập nhật; phần mình giữ chỉ là YAML + checker | **Chọn** |
| **B. Tự xây gateway riêng, nhúng moto làm backend, tự thêm IAM enforcement/networking giả lập** | 1–3 tháng | Có thể tốt hơn A ở IAM nhờ tự viết policy evaluator; vẫn không có data plane thật | Cao: phải theo kịp thay đổi API AWS và của moto | Chỉ cân nhắc nếu A thiếu IAM nghiêm trọng |
| **C. Viết emulator hoàn toàn mới** | Nhiều tháng đến năm cho chỉ 6–8 dịch vụ | Thấp hơn A trong thời gian dài | Rất cao | **Loại** — tái phát minh phần đã có, lệch khỏi mục tiêu học |

Lý do chọn A: mục tiêu là học khái niệm và cú pháp, không phải học viết emulator. Giá trị riêng mà không công cụ nào có sẵn là **kịch bản lab + bộ chấm tự động + reset sạch**; đó chính là phần nên tự xây [SL].

Lý do Floci làm mặc định thay vì MiniStack [SL]: EC2 chạy container thật ngay (làm được lab SSH/UserData), cộng đồng lớn hơn nhiều, chế độ persistence rõ ràng, và cùng họ với floci-gcp nên mở rộng GCP thống nhất. MiniStack nhẹ hơn và cài được bằng pip, nên là phương án dự phòng. Vì cả hai cùng nghe cổng 4566 và cùng wire protocol AWS, đổi backend chỉ là đổi image trong `docker-compose.yml`.

## 4. Kiến trúc đề xuất

### 4.1. Sơ đồ

```text
 Người học (macOS)
 ┌───────────────────────────────────────────────┐
 │  aws CLI v2 / boto3 / Terraform   (sau: gcloud)│
 │  AWS_ENDPOINT_URL=http://localhost:4566        │
 └──────────────┬────────────────────────────────┘
                │ API AWS thật (wire-compatible)
 ┌──────────────▼──────────────┐   ┌──────────────────────────┐
 │ Emulator backend (Docker)   │   │ moto_server :5000         │
 │ Floci :4566  (hoặc MiniStack)│   │ chỉ cho lab IAM cần      │
 │ persistence -> ./state/aws  │   │ Access Denied thật       │
 └──────────────▲──────────────┘   └────────────▲─────────────┘
                │ boto3 (đọc trạng thái)         │
 ┌──────────────┴────────────────────────────────┴──────────┐
 │ labctl (Python CLI) — phần tự xây                          │
 │  Provider interface: AwsProvider | GcpProvider (sau)       │
 │  labs/*.yaml  -> setup  -> người học làm -> check -> reset │
 │  progress.sqlite (tiến độ, lần chấm, thời gian)            │
 └───────────────────────────────────────────────────────────┘
          (sau) floci-gcp :4588 / emulator Google / fake-gcs-server
```

### 4.2. Thành phần

1. **Tương thích CLI/SDK**: không cần proxy. AWS CLI v2, boto3 và các SDK hiện hành đều đọc `AWS_ENDPOINT_URL` hoặc `endpoint_url` trong profile `~/.aws/config` [KC]. `labctl env` chỉ cần in ra hoặc tạo một profile `lab` với `endpoint_url = http://localhost:4566` và credential giả. Người học gõ lệnh `aws s3 mb ...` giống hệt trên AWS thật, chỉ thêm `--profile lab`.
2. **Lưu trạng thái**: trạng thái tài nguyên do emulator giữ (Floci `FLOCI_STORAGE_MODE=persistent` hoặc MiniStack `PERSIST_STATE=1`) [KC]; tiến độ học lưu trong SQLite cục bộ [SL]. Reset lab = gọi API xoá tài nguyên có tag/prefix của lab, hoặc xoá thư mục state rồi khởi động lại container (moto có sẵn API reset) [KC cho moto, SL cho phần còn lại].
3. **Định nghĩa lab (YAML)** [SL]:

```yaml
id: aws-02-s3-versioning
provider: aws
title: Bật versioning và khôi phục object bị xoá
setup:
  - create_bucket: { name: lab02-data }
  - put_object: { bucket: lab02-data, key: report.txt, body: "v1" }
tasks:
  - Bật versioning cho bucket lab02-data
  - Ghi đè report.txt thành "v2", rồi xoá nó
  - Khôi phục bản "v2"
checks:
  - s3.bucket_versioning: { bucket: lab02-data, status: Enabled }
  - s3.object_body: { bucket: lab02-data, key: report.txt, equals: "v2" }
  - s3.version_count: { bucket: lab02-data, key: report.txt, min: 3 }
hints: ["aws s3api put-bucket-versioning", "aws s3api list-object-versions"]
```

4. **Cơ chế chấm**: kiểm tra trạng thái cuối (state-based), mỗi `check` là một hàm Python nhỏ gọi boto3 vào emulator [SL]. Chấm theo trạng thái thay vì so lệnh đã gõ, vì cùng một kết quả có nhiều cách làm (CLI, SDK, CloudFormation, Terraform). Với IAM, có hai tầng: (a) kiểm tra cấu trúc policy document (Effect/Action/Resource/Condition); (b) với lab cần thấy lỗi `AccessDenied`, chạy trên moto với `INITIAL_NO_AUTH_ACTION_COUNT` để policy thực sự được đánh giá [KC cho moto]. Với VPC, chỉ kiểm tra cấu hình (route `0.0.0.0/0` trỏ IGW, SG rule, subnet CIDR) [SL].
5. **Mở rộng GCP**: interface `Provider` có `client(service)`, `env()`, `reset(lab)`, `health()`. `GcpProvider` cấu hình `api_endpoint_overrides` cho gcloud và `*_EMULATOR_HOST` cho client library [KC cho cơ chế, SL cho việc floci-gcp tương thích]. Lab YAML có trường `provider`, nên checker GCP chỉ là thêm một module `checks/gcp/*.py`.

### 4.3. So sánh hai kiến trúc chính

| Tiêu chí | A. Emulator có sẵn + lab engine (đề xuất) | B. Gateway tự xây trên moto |
|---|---|---|
| Ưu điểm | Nhanh có lab đầu tiên; đổi backend dễ; bảo trì thấp; EC2/Lambda chạy code thật (Floci) | Kiểm soát hoàn toàn IAM enforcement và thông báo lỗi; một tiến trình Python duy nhất, không cần Docker |
| Nhược điểm | IAM gần như không được thực thi; phụ thuộc chất lượng dự án trẻ (Floci, MiniStack đều bùng nổ sau sự kiện LocalStack 03/2026) | Công sức gấp nhiều lần; vẫn không có data plane EC2/VPC; dễ sa vào viết emulator thay vì học AWS |
| Rủi ro | Dự án upstream đổi giấy phép hoặc ngừng phát triển (đã xảy ra với LocalStack) → giảm thiểu bằng cách chỉ phụ thuộc wire protocol AWS, giữ được khả năng đổi sang MiniStack/moto | Trượt tiến độ; bug trong policy evaluator tự viết dạy sai khái niệm IAM |

## 5. Lộ trình lab (11 bài)

Thứ tự bám theo nhóm kiến thức của chứng chỉ nền tảng (Cloud Practitioner / Solutions Architect Associate) [SL]. Cột "Backend" ghi emulator nên dùng.

| # | Lab | Mục tiêu & kịch bản | Dịch vụ | Tiêu chí hoàn thành (checker) | Backend |
|---|---|---|---|---|---|
| 1 | Làm quen CLI & danh tính | Cấu hình profile `lab`, gọi `sts get-caller-identity`, dùng `--query`/`--output` | STS, CLI | Profile `lab` tồn tại với endpoint đúng; file `answers/lab01.txt` chứa account ID trả về | Floci |
| 2 | IAM users, groups, policies | Tạo group `developers` gắn policy chỉ đọc S3, tạo user `alice` vào group, tạo access key | IAM | Group có đúng 1 managed policy với `s3:Get*`/`s3:List*`; `alice` thuộc group; không có policy `*:*` | Floci |
| 3 | IAM enforcement & least privilege | Dùng key của `alice` thử ghi S3 → bị từ chối; sửa policy để chỉ ghi được prefix `alice/` | IAM, S3 | `PutObject` vào `alice/x` thành công và vào `bob/x` trả `AccessDenied` khi chạy bằng key của alice | moto |
| 4 | S3 cơ bản | Tạo bucket, upload/sync thư mục, dùng prefix, presigned URL | S3 | Bucket có ≥5 object dưới `site/`; presigned URL tải được object | Floci |
| 5 | S3 versioning, lifecycle, bucket policy | Bật versioning, khôi phục object bị xoá, lifecycle chuyển `logs/` sau 30 ngày, bucket policy chặn HTTP không TLS | S3 | Versioning `Enabled`; object khôi phục đúng nội dung; lifecycle rule có transition 30 ngày; policy có `aws:SecureTransport=false` → Deny | Floci |
| 6 | VPC từ đầu | Tạo VPC `10.0.0.0/16`, 2 public + 2 private subnet ở 2 AZ, IGW, route table, NAT gateway | VPC (EC2 API) | CIDR không chồng lấn; public RT có `0.0.0.0/0 → igw`; private RT có `0.0.0.0/0 → nat`; mỗi loại subnet trải 2 AZ | Floci/MiniStack |
| 7 | EC2 & security group | Tạo key pair, SG chỉ mở 22 từ một IP và 80 từ mọi nơi, chạy instance với UserData cài web server | EC2, VPC | Instance `running` trong public subnet; SG không mở 22 cho `0.0.0.0/0`; (Floci) curl tới cổng 80 của container trả nội dung UserData tạo ra | Floci |
| 8 | IAM role cho EC2 | Tạo role + instance profile cho phép đọc 1 bucket, gắn vào instance, đọc credential qua IMDS | IAM, STS, EC2 | Trust policy chỉ có `ec2.amazonaws.com`; instance có instance profile; role chỉ có quyền trên đúng bucket | Floci |
| 9 | DynamoDB | Thiết kế bảng `Orders` (PK/SK), GSI theo `status`, query vs scan, conditional write, TTL | DynamoDB | Bảng có key schema và GSI đúng; ≥20 item; một conditional update bị từ chối được ghi lại; TTL bật trên `expiresAt` | Floci |
| 10 | Lambda + S3/SQS event | Viết Lambda Python, kích hoạt khi có object mới vào S3 hoặc message SQS, ghi kết quả vào DynamoDB, xem log CloudWatch | Lambda, S3, SQS, DynamoDB, CloudWatch Logs | Upload file → trong 30 giây có item tương ứng trong DynamoDB; log group của function tồn tại; role Lambda không có `*` | Floci |
| 11 | Capstone: hạ tầng bằng code | Dựng lại lab 6+9+10 bằng CloudFormation (hoặc Terraform), xoá stack sạch rồi dựng lại | CloudFormation, toàn bộ ở trên | Stack `CREATE_COMPLETE`; mọi checker của lab 6, 9, 10 đều qua; sau `delete-stack` không còn tài nguyên có tag `lab=11` | Floci |

Lab GCP tương ứng (chỉ thiết kế): Cloud Storage ↔ lab 4–5, Firestore ↔ lab 9, Pub/Sub + Cloud Functions ↔ lab 10, IAM service account ↔ lab 2/8. Không có emulator tốt cho VPC/Compute Engine của GCP ngoài control plane của floci-gcp [KC: danh sách emulator chính thức], nên lab 6–7 phiên bản GCP sẽ là kiểm tra cấu hình [SL].

## 6. Câu hỏi mở và rủi ro

### Rủi ro chính

1. **IAM không được thực thi mặc định** trên Floci, MiniStack, LocalStack Hobby [KC]. Người học có thể tưởng policy đúng vì lệnh vẫn chạy. Giảm thiểu: chạy lab IAM trên moto với enforcement bật, và checker luôn kiểm tra nội dung policy.
2. **Networking không có data plane**: route table, NACL, SG được lưu nhưng không lọc lưu lượng thật [KC với MiniStack: tài liệu không nói là có; SL cho các dự án khác]. Học đúng cấu hình nhưng không trải nghiệm được lỗi kết nối.
3. **Độ chín của Floci/MiniStack**: cả hai lớn mạnh nhanh sau khi LocalStack Community dừng (03/2026); chưa có đánh giá độc lập; nhiều fork trùng tên [KC]. Có thể gặp hành vi sai khác AWS. Giảm thiểu: giữ backend có thể thay được và ghi lại sai khác trong ghi chú lab.
4. **Thay đổi giấy phép** là rủi ro đã thành hiện thực một lần (LocalStack). Giảm thiểu: chỉ phụ thuộc wire protocol AWS, ghim phiên bản image Docker.
5. **Tài nguyên macOS**: EC2/Lambda chạy container nên cần Docker Desktop (hoặc tương đương) và RAM đáng kể khi chạy nhiều instance [SL].

### Câu hỏi còn mở

1. Bạn có kinh nghiệm ngôn ngữ nào? Báo cáo giả định Python (phù hợp boto3, moto, MiniStack). Nếu bạn quen Node.js hay Go thì chỉ lab engine thay đổi, backend giữ nguyên.
2. Ưu tiên nhóm dịch vụ nào trước? Lộ trình hiện đi IAM → storage → networking → compute → database → serverless.
3. Chỉ CLI hay cần cả giao diện web? Báo cáo đề xuất CLI trước; có thể thêm dashboard tiến độ sau.
4. Việc học có do công ty tài trợ hoặc phục vụ công việc không? Nếu có, điều khoản "phi thương mại" của LocalStack Hobby có thể không áp dụng được; Floci/MiniStack/moto (MIT/Apache) không có ràng buộc này [KC về giấy phép].
5. Cần thử thực tế: `gcloud` có hoạt động với floci-gcp qua `api_endpoint_overrides` không; Floci/MiniStack có hỗ trợ `iam simulate-principal-policy` không (nếu có sẽ làm checker IAM tốt hơn).

## 7. Bước tiếp theo

1. Chạy spike nửa ngày: `docker compose` với Floci, chạy thử các lệnh chính của lab 2, 4, 6, 7, 10; làm lại với MiniStack; ghi lại sai khác.
2. Chạy thử lab 3 trên moto với `INITIAL_NO_AUTH_ACTION_COUNT` để xác nhận `AccessDenied` hoạt động với policy có prefix resource.
3. Nếu spike ổn, lập plan bằng `/ak:plan` cho `labctl` (Provider interface, lab YAML schema, 5 lab đầu), dựa trên báo cáo này.

## 8. Nguồn

Tất cả truy cập ngày 2026-10-27.

- LocalStack pricing: https://www.localstack.cloud/pricing
- LocalStack licensing & bảng dịch vụ theo gói: https://docs.localstack.cloud/aws/licensing/
- LocalStack blog, thay đổi giá 2026 (đăng 27/02/2026, cập nhật 24/07/2026): https://blog.localstack.cloud/2026-upcoming-pricing-changes/
- Floci: https://github.com/floci-io/floci
- floci-gcp: https://github.com/floci-io/floci-gcp
- MiniStack: https://github.com/ministackorg/ministack, https://ministack.org/
- moto repo: https://github.com/getmoto/moto
- moto trên PyPI (bản 5.2.4): https://pypi.org/project/moto/
- moto implementation coverage: https://raw.githubusercontent.com/getmoto/moto/master/IMPLEMENTATION_COVERAGE.md
- moto server mode: https://docs.getmoto.org/en/latest/docs/server_mode.html
- moto IAM-like access control: https://docs.getmoto.org/en/latest/docs/iam.html
- AWS SDK/CLI service-specific endpoints (`AWS_ENDPOINT_URL`): https://docs.aws.amazon.com/sdkref/latest/guide/feature-ss-endpoints.html
- gcloud emulators reference: https://docs.cloud.google.com/sdk/gcloud/reference/emulators
- gcloud `api_endpoint_overrides`: https://docs.cloud.google.com/sdk/gcloud/reference/config/set
- Pub/Sub emulator: https://docs.cloud.google.com/pubsub/docs/emulator
- Datastore mode / Firestore emulator: https://docs.cloud.google.com/datastore/docs/emulator
- fake-gcs-server: https://github.com/fsouza/fake-gcs-server
- Bối cảnh bên thứ ba (không dùng làm nguồn chính): https://dev.to/peytongreen_dev/your-localstack-ci-is-broken-here-are-your-three-options-41o8, https://agentdeals.dev/localstack-alternatives, https://java.testcontainers.org/modules/gcloud
