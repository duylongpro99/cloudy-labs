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

Còn mở: validate không kiểm `DBClusterIdentifier` của `create-db-instance` có trỏ tới cluster có thật hoặc tới một bước trước hay không, nên chuỗi thiếu `create-db-cluster` chỉ lộ ra lúc chạy.
