# Kết quả nghiệm thu M7 (2026-11-01)

Chạy trên Apple M1 Pro, Docker Desktop, Floci và moto theo `server/src/cloudy_labs/emulator/compose.yaml`. Mỗi lần chạy, máy còn các container khác không thuộc dự án (load average khoảng 5–6).

| Kiểm tra | Lệnh | Kết quả |
|---|---|---|
| Unit server | `cd server && uv run pytest -q` | 905 passed, 136 deselected (docker, llm) |
| Lint server | `uv run ruff check src tests` | sạch |
| Web | `cd web && pnpm test`, `pnpm typecheck` | 599 passed (28 file); typecheck sạch |
| Contract registry trên Floci | `uv run pytest -q -m docker tests/test_registry_contract_docker.py` | Lần chạy cuối (load dưới 6): 104/105 kind đạt. Chỉ `db-cluster-parameter-group` trượt vì thời gian (create 2,59 s, ngưỡng 2,0 s). Hai lần trước: 103/105, mỗi lần trượt ở hai kind khác nhau, cũng chỉ vì thời gian (`tgw-route-table`, `efs-file-system`, `efs-mount-target`, `glue-crawler`). `contract-results.json` và `docs/coverage.md` lấy từ lần chạy cuối. Ngưỡng giữ nguyên. |
| Lab 6/7 qua builder | `uv run pytest -q -m docker tests/test_builder_e2e_docker.py` | 4 passed; `labctl check` 7/7 |
| Bench 200 node (NFR2) | `BENCH_RESULTS_DIR=… pnpm dev` + `node scripts/run-chrome-bench.mjs` | Chrome, 16 cấu hình: p95 khung hình 9,0–9,5 ms, 120 fps (trần vsync), kể cả 20 ghost và bộ kind trộn; idle 0 khung hình. Số liệu ở [bench/](./bench/). |
| Rò nội dung labaws | `cd server && uv run python scripts/check-content-leak.py` | exit 0, so với `labs/lab-001/content/lab.md`. Lần đầu báo trùng 8 từ ở `plan.md` và Phase 11: đó là slug URL của lab. Slug đã được thay bằng `lab-001`. |
| Catalog | `uv run labctl coverage --catalog … --json` | 530 lab: ready 1, ready-with-caveats 468, blocked 61, gap 0 |

## Lab-001 RDS (Phase 11 bước 1–4)

Nội dung lab nằm ở `labs/lab-001/content/lab.md` (gitignored). File này chỉ ghi lệnh, kết luận và số đo.

| Bước | Lệnh | Kết quả |
|---|---|---|
| Coverage trước khi soạn | `uv run labctl coverage lab-001` | Bản nháp báo gap `unknown-command: aws rds wait`. Extractor chưa hiểu lệnh `wait`. Đã sửa: `wait <waiter>` ánh xạ sang API mà waiter của botocore gọi (`db-instance-available` → `DescribeDBInstances`). |
| Coverage sau `--accept` | `uv run labctl coverage lab-001 --accept` | `ready-with-caveats`. 12 dòng lý thuyết được đánh dấu bỏ qua (Oracle, SQL Server, Lightsail), chỉ lưu số dòng. Caveat chính: `flag-only` (Multi-AZ, failover), `aurora-plain-engine`, `aurora-cluster-sg-ignored`, `rds-storage-type-gp2` (mới). |
| Self-managed trên EC2 (bước 2) | `extract.commands` trên trang lab | Không áp dụng: trang chỉ chạy lệnh describe/delete của RDS và SG cùng `failover-db-cluster`, không chạy `run-instances` hay cài package. Không thêm caveat `self-managed-install`. |
| Lần 1: builder | `/api/run` của `labctl serve` (subnet group, SG, ingress 3306 từ 10.1.0.0/16, MySQL gp3 20→100 GiB, cluster aurora-mysql, writer và reader, secret), rồi `aws rds failover-db-cluster` | `labctl check lab-001`: 12/12 đạt, cộng 1 INFO (`rds-mysql-gp3`). Thử âm tính: thêm 0.0.0.0/0 cổng 3306 làm `db-sg-not-open-to-world` FAIL (11/12). Thu hồi rule thì về lại 12/12. |
| Lần 2: terminal | `labctl reset lab-001`, rồi chỉ dùng AWS CLI. Ingress 3306 lần này lấy từ `--source-group` của SG app. | 12/12 đạt, cộng 1 INFO. Twin: 13/13 node của target bind vào tài nguyên thật, 0 ghost. |
| Reset | `labctl reset lab-001` rồi `labctl check` | 1/12 đạt (chỉ `network-ready`, do setup dựng). Không còn DB instance. |
| Lần 3: chat (2026-11-01) | `labctl start lab-001`, rồi 6 câu hỏi tiếng Việt viết lại từ task của `lab.yaml` qua `/api/chat` (model `ds/deepseek-v4-pro`), chạy mỗi chuỗi qua `/api/run`. Bước bị validate từ chối hoặc chạy lỗi thì gửi lại cho chat một lượt, như người học làm. | 12/12 đạt, cộng 1 INFO. Câu Aurora cần một lượt hỏi lại. Lần chạy trước còn có hai lỗi do model: mô tả secret có dấu tiếng Việt (validate chặn, đúng luật ký tự của AWS), và chuỗi Aurora thiếu `create-db-cluster` (`DBClusterNotFoundFault` khi chạy). 7 prompt gửi đi chỉ trùng trang lab đúng một cụm 8 từ, là tên tài nguyên `lab-001-dbsubnet-group`, không có câu văn nào của trang. |

### Đối chiếu với phần kiểm tra của lab

| Lab kiểm | Trên Floci 2.3.0 |
|---|---|
| Engine mysql, trạng thái available | Khớp. Instance available ngay, không phải chờ. |
| Một AZ (`MultiAZ` false) | Khớp. |
| Storage gp3 | Không khớp. Floci luôn báo `gp2` khi tạo và khi modify. Check `rds-mysql-gp3` chỉ ở mức INFO; kích thước 20 GiB và `MaxAllocatedStorage` 100 thì được chấm. |
| Aurora failover đổi writer | Khớp ở mức cờ: `failover-db-cluster` đổi `IsClusterWriter` giữa hai instance, không có failover thật. |
| SG của Aurora cluster | Floci bỏ qua (`sg-00000000`). Chấm SG ở RDS instance và chính SG đó. |

Giới hạn của builder gặp lúc làm: op ingress SG chỉ nhận CIDR, chưa nhận SG nguồn. Builder chưa có op failover, nên bước này dùng terminal.

Đã bổ sung sau (2026-11-01): op ingress nhận `sourceGroupId` (SG nguồn cùng VPC, thay cho CIDR) và registry có op `failover-db-cluster` (chọn reader làm writer, để trống thì RDS tự chọn). Chạy lại lab-001 hoàn toàn qua builder, ingress 3306 từ `lab-001-sg-app` và failover sang `lab-001-aurora-reader`: `labctl check lab-001` 12/12 đạt, cộng 1 INFO (`rds-mysql-gp3`).

Lần chạy bằng chat còn tìm ra một lỗi code, đã sửa: sau khi tạo secret, prop `lastChanged` của node secret là `datetime` của botocore, nên `/api/chat` trả 500 ở câu kế tiếp (`json.dumps` không ghi được `datetime`). Prompt giờ ghi `datetime` dạng ISO, giống `/ws`.

Đã sửa sau (2026-11-01): `DBClusterIdentifier` của `create-db-instance` giờ là tham chiếu tới một `db-cluster`. Validate của chat từ chối instance trỏ tới cluster không có trong cảnh và không do bước nào trước đó tạo, nên chuỗi thiếu `create-db-cluster` bị chặn trước khi chạy.

## Lab-020: VPC ba AZ với NAT theo từng AZ (2026-11-01)

Nội dung lab nằm ở `labs/lab-020/content/lab.md` (gitignored). File người dùng đặt ở `labs/lab-020/lab020.md` không bị ignore, nên đã được chuyển vào `content/`. Lab này dùng để kiểm lại M3 (VPC qua builder) và M6 (twin) bằng một lab labaws thật.

Phần bước làm trên console của trang không tạo NAT Gateway, nhưng sơ đồ kiến trúc, bảng đặt tên và phần kiểm tra của trang đều yêu cầu mỗi AZ một NAT và route `0.0.0.0/0` của app subnet đi tới NAT cùng AZ. `lab.yaml` vì vậy có task `zonal-nat` và chấm route theo từng AZ. Trên Floci, NAT không tốn phí.

| Bước | Lệnh | Kết quả |
|---|---|---|
| Coverage | `uv run labctl coverage lab-020 --accept` | `ready-with-caveats`. Hai dòng nhắc "subnet group" bị gắn nhầm với dax/memorydb, đã đánh dấu bỏ qua. Danh sách caveat có cả apigatewayv2, dynamodb, eks và elb, do phần lý thuyết của trang nhắc tới các dịch vụ đó; bài lab không dùng chúng. |
| Lần 1: builder | 38 lệnh `/api/run`: VPC, DNS hostnames, 9 subnet, IGW, route table public, 3 Elastic IP và 3 NAT, 3 route table app, route table data, DB subnet group | `labctl check lab-020` 14/14. Twin: 26/26 node của target gắn vào tài nguyên thật, 0 ghost, mỗi node đúng AZ. |
| Reset | `labctl reset lab-020` | Chỉ còn VPC mặc định và subnet group `default`; không còn NAT hay Elastic IP. |
| Lần 2: terminal | Chỉ dùng AWS CLI, cố ý cho route table app-b đi qua NAT của AZ a, rồi `replace-route` sang NAT b | Lúc sai: 13/14, `app-route-b` FAIL và báo subnet AZ b ra ngoài qua NAT ở AZ a. Sau khi sửa: 14/14. Twin 26/26, 0 ghost. |
| Lần 3: chat | 7 câu tiếng Việt viết lại từ task của `lab.yaml` qua `/api/chat` (model `ds/deepseek-v4-pro`), mỗi chuỗi chạy qua `/api/run` | 14/14. 6 câu đạt ngay. Câu route table app cần hỏi lại một lần: model ghi tham chiếu thành chuỗi `"{ref:1}"` thay vì object, validate chặn cả ba `create-route`. 8 prompt gửi đi trùng trang lab ở 8 cụm 8 từ: tên tài nguyên kèm CIDR, danh sách ba AZ của Sydney và một cụm mô tả route table data trong câu hỏi; không có đoạn văn nào của trang. |
| Rò nội dung | `uv run python scripts/check-content-leak.py` | exit 0. Lần đầu báo một cụm ở task VPC của `lab.yaml` (tên VPC kèm CIDR), đã viết lại. Các idiom AWS trùng trang (route mặc định, tên AZ, filter CLI tìm IGW theo VPC) được ghi hash trong `labs/lab-020/leak-review.json`. |

Lần đầu soạn target, twin gắn sai: `App b` vào subnet data của AZ a, NAT a vào NAT của AZ b. Nguyên nhân là mỗi node subnet liệt kê check chung cho cả chín subnet, và NAT được khai báo trước subnet. Bản cuối dùng check riêng cho từng AZ (`nat-a/b/c`, `app-route-a/b/c`) và khai báo NAT sau subnet.

### Đối chiếu với phần kiểm tra của lab

| Lab kiểm | Trên Floci 2.3.0 |
|---|---|
| 9 subnet, 3 AZ ID (`apse2-az1/2/3`), 251 IP trống mỗi subnet | Khớp. Subnet báo `AvailabilityZoneId`. |
| Route table app riêng cho từng AZ, route data chỉ có `local` | Khớp. Route table mới chỉ có route `local`. |
| DB subnet group trải 3 AZ | Khớp. |
| Egress đi qua NAT cùng AZ | Chấm tĩnh trên route table. Floci không chuyển gói tin thật qua NAT. |

## Lab-900: EC2 web với security group và UserData (2026-11-01)

Lab tự soạn để kiểm lại M4 (EC2 qua builder), M5 (chat) và M6 (twin) bằng một lab có EC2. Trang lab nằm ở `labs/lab-900/content/lab.md` (gitignored). Lab gồm một VPC với hai public subnet ở `ap-southeast-1a/1b`, một IGW, một route table public, security group `lab900-web-sg` (80 cho mọi nơi, 22 cho một `/32`), key pair `lab900-key`, và hai instance AL2023 bắt buộc IMDSv2, mỗi instance chạy UserData trả trang có instance id của nó. `lab.yaml` có 14 check, trong đó `web-1-page` và `web-2-page` gọi HTTP thật tới instance.

Trên Mac Apple Silicon, builder chỉ cho AMI `ami-amazonlinux2023-arm64` với `t4g.micro`/`t4g.small`; Floci cũng từ chối AMI arm64 đi với `t3.micro`, như AWS. Check instance vì vậy nhận cả `t3.micro` và `t4g.micro`.

| Bước | Lệnh | Kết quả |
|---|---|---|
| Coverage | `uv run labctl coverage lab-900 --accept` | `blocked`: dòng kiểm tra tuỳ chọn của trang gọi `aws ec2 get-console-output`, mà Floci 2.3.0 không có (`UnsupportedOperation`). Hai dòng gắn nhầm dịch vụ (cloudfront, workspaces-web) đã đánh dấu bỏ qua. Các bước bắt buộc của lab đều chạy được. |
| Lần 1: builder | Chỉ `/api/run`: VPC, subnet, IGW, route table, SG kèm 2 rule, key pair, 2 instance với `builder.userData` | 13/14. Chỉ `imdsv2-required` FAIL vì op `run-instances` của builder không có trường metadata options. Hai trang trả qua `127.0.0.1:30000/30001` và có đúng instance id. Twin: 11/11 node gắn vào tài nguyên thật, 0 ghost. |
| Lần 2: terminal | Chỉ AWS CLI, `run-instances --metadata-options HttpTokens=required`. Web-1 dùng UserData của trang (`dnf install httpd` rồi `systemctl enable --now httpd`), web-2 dùng `builder.userData` | Web-1 không có trang sau 4 phút (13/14); thông điệp check nói rõ instance không có `index.html` và cổng 80 chỉ có IMDS. Terminate web-1 rồi chạy lại với `builder.userData`: 14/14. Twin 11/11, 0 ghost. |
| Reset | `labctl reset lab-900` | 0/14, không còn container instance của lab. |
| Lần 3: chat | 5 câu tiếng Việt viết lại từ task của `lab.yaml` qua `/api/chat`, mỗi chuỗi chạy qua `/api/run` | 13/14, chỉ `imdsv2-required` FAIL như builder: chat chỉ chọn op trong danh mục builder. 4 câu đạt ngay. Câu VPC cần hỏi lại một lần vì validate chặn một bước ở câu trả lời đầu (script không lưu chi tiết bước bị chặn). Câu chạy instance dùng đúng AMI arm64, `t4g.micro`, SG, key và UserData gợi ý của lab. 6 prompt gửi đi trùng trang ở 14 cụm 8 từ: 13 cụm là URL và header IMDSv2 nằm trong `builder.userData` (system prompt gửi kèm UserData gợi ý của lab), 1 cụm là tên VPC kèm CIDR. Không có đoạn văn nào của trang. |
| Coverage, sau khi có `--optional` | `uv run labctl coverage lab-900 --accept --optional 434` | `ready-with-caveats`. Dòng `get-console-output` thành caveat `optional-step-unsupported`. `aws sso login` ở phần chuẩn bị giờ được đọc là việc của CLI, không còn là lời gọi API. |
| Lần 4: builder, có IMDSv2 | Như lần 1, `run-instances` thêm `httpTokens: required` | 14/14. `describe-instances` cho thấy cả hai instance có `HttpTokens=required`. |
| Lần 5: chat, có IMDSv2 | 5 câu như lần 3 | 14/14, cả 5 câu qua validate ngay lần đầu; `run-instances` của hai instance có `--metadata-options HttpTokens=required`. Hai lượt chạy trước đó dừng giữa chừng: một lượt vì provider LLM không trả lời trong 60 giây, một lượt vì model bỏ bước `create-vpc` và bịa VPC id (validate chặn, lần hỏi lại cũng sai). |
| Lần 6: chat, có chặn id bịa | 5 câu như lần 3, ba lượt | Lượt đầu: guardrail bắt một lần model viết ref dạng chuỗi (`vpcId='{"ref": 1}'`), server hỏi lại và câu trả lời thứ hai qua validate; cả 5 câu chạy được, 12/14 vì script chỉ chờ trang web 90 giây. Server giờ đọc ref dạng chuỗi là ref, không cần hỏi lại. Lượt hai dừng ở câu 5 vì provider quá 60 giây. Lượt ba, chờ trang 240 giây: 14/14, không câu nào cần hỏi lại. |
| Rò nội dung | `uv run python scripts/check-content-leak.py` | exit 0. Vòng lặp tên instance trong `checks.py` được viết lại thành hằng `WEB_NAMES`. Các idiom AWS trùng trang (URL và header IMDSv2, subnet ghi theo AZ kèm CIDR, đường dẫn SSM của AMI AL2023, filter CLI tìm IGW, rule mở tcp 80) được ghi hash trong `labs/lab-900/leak-review.json`. |

### Khoảng trống còn lại

| Khoảng trống | Ảnh hưởng |
|---|---|
| Floci lưu `HttpTokens=required` nhưng vẫn trả IMDSv1 | Check chấm trên `MetadataOptions`; người học không thấy IMDSv1 bị chặn như trên AWS. |
| Chat đôi khi bỏ bước tạo tài nguyên và bịa id | Server tự gửi lại một lần, nêu tên id bịa; id bịa còn lại thành problem kể cả ở bước deferred, nên không Run được. Không bảo đảm model sửa đúng ở lần hai. |
| Instance Floci không có systemd, IMDS chiếm cổng 80 | UserData `httpd` + `systemctl` của trang không chạy; hint của task `instances` chỉ sang `builder.userData`. |
| Floci không có `GetConsoleOutput` | Bước kiểm tra tuỳ chọn của trang không chạy được; coverage ghi caveat thay vì `blocked` vì dòng đó được đánh dấu `--optional`. |
