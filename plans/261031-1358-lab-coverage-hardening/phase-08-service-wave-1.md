---
phase: 8
title: "Dịch vụ đợt 1: VPC mở rộng, EBS, RDS/Aurora, S3, Lambda, IAM"
status: completed
priority: P1
effort: "40h"
dependencies: [6]
---

# Phase 8: dịch vụ đợt 1

## Goal

Các service xuất hiện nhiều nhất trong danh mục có đủ mục registry, icon, op builder và contract test đạt. Thứ tự theo số lab nhắc tới: ec2 182, rds 122, s3 81, lambda 54, iam 21. Phase này cũng cung cấp kind và props mà Phase 7 (reachability) cần.

## Phạm vi

- **EC2/VPC mở rộng:**
  - Network ACL và entry;
  - VPC endpoint (gateway và interface);
  - VPC peering;
  - flow log;
  - Transit Gateway, attachment và TGW route table;
  - ENI;
  - EBS volume và attachment;
  - launch template;
  - prefix list.
- **[Red team] Floci thiếu**, đánh dấu `floci.status: missing` ở mức op và đưa vào `catalog-overrides.yaml`:
  - EBS `CreateSnapshot` và `CopySnapshot`;
  - `CreateDhcpOptions`;
  - `CreateEgressOnlyInternetGateway`;
  - `CreatePlacementGroup`;
  - engine RDS Oracle.

  Thử lại từng API trên Floci ở bước 1 để xác nhận trước khi đánh dấu.
- **[Red team] Hợp đồng props reachability** trong `ec2.yaml`, đổi golden graph:
  - SG: thêm rule **egress** bên cạnh ingress, giữ cấu trúc có tham chiếu SG và prefix list thay vì làm phẳng;
  - route table: danh sách route đầy đủ gồm `local`, mỗi route có `destination`, `target` và `state` (`active` | `blackhole`);
  - association: subnet ↔ route table, có cờ `main`;
  - NACL: entry có `rule_number`, `egress`, `protocol`, `port_range`, `cidr`, `action`.

  Golden `lab-06-07.graph.json` đổi vì props mới. Ghi chú trong commit; props cũ giữ nguyên tên.
- **RDS/Aurora:**
  - DB subnet group;
  - DB instance, gồm read replica có cạnh `replica-of`;
  - DB cluster (Aurora) với member writer và reader;
  - DB parameter group và cluster parameter group, option group;
  - DB snapshot, cluster snapshot;
  - RDS Proxy.

  Caveat trong `caveats` của registry:
  - `MultiAZ`: `flag-only`, nghĩa là Multi-AZ và failover chỉ là cờ;
  - Aurora chạy trên container MySQL hoặc Postgres thường;
  - read replica cross-region: `control-plane-only`.
- **S3:** bucket. Cấu hình con hiện dạng props và badge, không phải node riêng: versioning, encryption, public access block, policy, lifecycle, replication (caveat `control-plane-only`), notification, website.
  - Thao tác cấu hình là op `modify` (`PutBucketVersioning`...).
  - Số object hiện là props, đếm bằng `ListObjectsV2` có giới hạn, chạy qua `enrich`.
- **Lambda:** function (trong VPC thì nằm trong subnet, nếu không thì trong region), alias, version, event source mapping (cạnh tới SQS, DynamoDB stream, Kinesis), layer.
  - `CreateFunction` cần zip. Builder có ô chọn mẫu code dựng sẵn; server tạo zip từ `builder/lambda_samples/` (Phase 5).
  - `chat_props` không gồm `Environment`.
- **IAM:** role, user, group, managed policy, instance profile, cùng cạnh attach và `assume-role`.
  - **[Red team]** IAM là global. Kind IAM có `scope: global` và nằm dưới node `global` của root `account` (Phase 3). Phase này không đổi root.
  - **[Red team]** Principal admin nội bộ `cloudy-labs-admin` của moto được khai báo `protected` trong `iam.yaml`.
  - Caveat: Floci không thực thi policy. Lab cần `AccessDenied` thật chọn `emulator: moto` (Phase 3).
- **[Red team] Icon:** lấy từ `aws-icon-pkg` (Resource-Icons nếu có, nếu không thì Architecture-Service-Icons), chép bằng `import-aws-icons.mjs` vào `web/src/scene/aws-objects/icons/`, rồi build lại web. Ghi vào `NOTICE.md`.

## Files to Create / Modify

- Modify: `server/src/cloudy_labs/registry/ec2.yaml`, `registry/catalog-overrides.yaml`.
- Create: `server/src/cloudy_labs/registry/rds.yaml`, `s3.yaml`, `lambda.yaml`, `iam.yaml`.
- Modify: `server/src/cloudy_labs/registry/hooks.py` (chỉ khi dữ liệu không diễn tả được; ghi lý do).
- Modify: `server/src/cloudy_labs/registry/contract-results.json`, `docs/coverage.md` (sinh lại).
- Modify: golden `server/tests/fixtures/graph/lab-06-07.graph.json` (props reachability).
- Modify: `web/src/scene/aws-objects/icons/` (icon chép bằng script), `icons/NOTICE.md`.
- Modify: `docs/emulator-differences.md` (caveat từng service).
- Create: fixture describe trong `server/tests/fixtures/graph/floci-describe/<service>/`, ghi bằng `record-floci-fixtures.py`.

## Tasks & Steps

1. Với mỗi service, thử API trên Floci bằng CLI để lấy output thật. Ghi fixture bằng script vào `server/tests/fixtures/graph/floci-describe/<service>/`. Xác nhận lại các API bị nghi là thiếu.
2. Viết mục registry gồm:
   - `list`, `scope`, `enrich`, `filter`, id, cha, cạnh;
   - `props`, `chat_props`, `caveats`, `protected`, `view`;
   - `ops` (`fields`, `defaults`, `container`, `expect`);
   - `fixture` cho contract test.
3. Thêm props reachability cho EC2; cập nhật golden; test collector trên fixture.
4. Chạy contract test. Contract trượt vì Floci thì ghi `floci.status` và lý do. Contract trượt vì registry thì sửa.
5. Soát bằng mắt trong gallery, ở hai chủ đề.
6. Chạy `labctl coverage --catalog`; ghi số lab `gap` còn lại và **[Red team]** số giờ thực tế cho mỗi service vào `notes/coverage-progress.md`, để chỉnh effort Phase 9–10.

## Verification

- `cd server && uv run pytest -q` và `uv run pytest -m docker tests/test_registry_contract_docker.py -q`.
- `uv run labctl coverage --catalog ...`: không còn lab `gap` nào có lý do là service đợt 1. Lab có DHCP, egress-only IGW, placement group, Oracle hoặc EBS snapshot ra `blocked`.
- Test: xoá `cloudy-labs-admin` qua builder bị từ chối; node này không hiện trong graph.
- Bench 200 node gồm các kind mới: ≥ 50 fps.

## Risk / Rollback

- Một số quan hệ cần gọi thêm API theo từng tài nguyên, ví dụ `get_bucket_versioning` cho từng bucket. Giới hạn bằng `enrich` chỉ cho kind trong tập thu của lab (Phase 6, mục 5) và cache theo `content_hash`.
- Đổi golden vì props reachability: commit riêng, có ghi chú.
