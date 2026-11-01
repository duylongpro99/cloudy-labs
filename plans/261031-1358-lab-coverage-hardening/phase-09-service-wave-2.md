---
phase: 9
title: "Dịch vụ đợt 2: tần suất trung bình"
status: completed
priority: P2
effort: "40h"
dependencies: [6]
---

# Phase 9: dịch vụ đợt 2

## Goal

Các service được nhắc trong 9–30 lab có mục registry, icon, op và contract test, theo đúng quy trình của Phase 8.

## Phạm vi

Số trong ngoặc là số lab nhắc tới, theo cột `api_namespaces` của CSV. **[Red team]** Giờ ước tính theo từng service: khoảng 2 giờ cho service chỉ cần `list`, và 4–6 giờ cho service cần list theo cha hoặc chạy container thật.

| Service | Kind chính | Caveat dự kiến | Giờ |
|---|---|---|---|
| CloudWatch (30) + Logs (5) | alarm, dashboard, log group, metric filter | metric chỉ có số do lab đẩy vào | 4 |
| EFS (24) | file system, mount target (trong subnet, list theo cha), access point | | 4 |
| CloudFormation (21) | stack (`DescribeStackResources` qua `enrich`) | `chat_props` không gồm `Outputs`, `Parameters` | 4 |
| DynamoDB (20) | table, GSI (props), stream (cạnh); global table (caveat `control-plane-only`) | | 3 |
| KMS (19) | key, alias | | 2 |
| SSM (17) | parameter, document | Run Command cần agent trong container EC2, kiểm ở contract; `chat_props` không gồm giá trị parameter | 4 |
| ELBv2 (16) | load balancer (trải các subnet), target group, listener và rule (list theo cha) | HTTP listener forward tới instance, kiểm ở contract | 6 |
| Secrets Manager (16) | secret, rotation (props) | `chat_props` không gồm giá trị secret | 2 |
| Route 53 (14) | hosted zone, record set (list theo cha); `scope: global` | DNS chỉ có cho private zone | 3 |
| Backup (13) | vault, plan, selection | job không chạy thật thì ghi caveat | 3 |
| EventBridge (13) + Scheduler | bus, rule, target (cạnh), schedule | | 3 |
| Auto Scaling (9) | group (trải subnet), launch template (cạnh), policy | | 2 |

Phần còn lại (khoảng 0–4 giờ) để chỉnh theo số đo của Phase 8.

- Lưu ý CloudFormation: tài nguyên do stack tạo đã hiện qua kind của chính nó. Node stack chỉ thêm cạnh `managed-by`, không lồng lại để tránh trùng.

## Files to Create / Modify

- Create: `server/src/cloudy_labs/registry/cloudwatch.yaml`, `logs.yaml`, `efs.yaml`, `cloudformation.yaml`, `dynamodb.yaml`, `kms.yaml`, `ssm.yaml`, `elbv2.yaml`, `secretsmanager.yaml`, `route53.yaml`, `backup.yaml`, `events.yaml`, `scheduler.yaml`, `autoscaling.yaml`.
- Modify: `registry/hooks.py` (chỉ khi cần; ghi lý do), `registry/catalog-overrides.yaml` (API thiếu tìm thấy ở bước 1).
- Modify: `contract-results.json`, `docs/coverage.md`, `docs/emulator-differences.md`, icon trong `web/src/scene/aws-objects/icons/` và `NOTICE.md`.
- Create: fixture describe tương ứng trong `server/tests/fixtures/graph/floci-describe/<service>/`, ghi bằng script.

## Tasks & Steps

Làm như Phase 8, bước 1–6, cho từng service trong bảng. Ghi giờ thực tế vào `notes/coverage-progress.md`.

## Verification

- `uv run pytest -q` và `uv run pytest -m docker tests/test_registry_contract_docker.py -q`.
- `labctl coverage --catalog`: không còn lab `gap` do service đợt 1–2.
- Test: `chat_props` của CloudFormation, SSM và Secrets Manager không chứa prop nào trong deny-list.

## Lệch so với thiết kế

- Fixture Floci của đợt 2 nằm ở thư mục riêng `server/tests/fixtures/graph/floci-describe-wave-2/`, golden `wave-2.graph.json`. Fixture đợt 1 và lab 6/7 giữ nguyên.
- Cạnh `reads-stream` (Lambda đọc stream DynamoDB) đặt ở kind DynamoDB, không ở Lambda. Một số test dựng registry chỉ gồm service đợt 1; cạnh trỏ từ kind cũ sang kind mới làm registry đó không hợp lệ.
- Contract đổi theo hành vi Floci đã đo:
  - CloudWatch bỏ `put-metric-data`, vì Floci đánh giá alarm khoảng một phút sau. Dùng `set-alarm-state` sang `ALARM`.
  - SSM bỏ `label-parameter-version`, vì nhãn không có trong `DescribeParameters`.
  - Secrets Manager dùng `RecoveryWindowInDays: "7"`.
  - ELB thêm security group thứ hai để `set-security-groups` thật sự đổi đồ thị.
- Sanitizer có thêm luật tên dạng đường dẫn theo service (log group, SSM parameter, KMS alias, Secrets Manager) và danh sách subnet `VPCZoneIdentifier`. Token idempotency (ví dụ `ClientToken` của EFS) không còn bị coi là trường bắt buộc.
- Collector kéo cả kind cha của `list.scope` khi chỉ xin kind con.
- Icon record set của Route 53 dùng icon Document; icon Route Table vượt ngân sách 2000 tam giác.
- Action của Auto Scaling không có `Instances`, để `RunInstances` vẫn ứng với kind instance.
- Chưa làm, ghi lại làm giới hạn:
  - Chưa có cạnh ASG→subnet, vì chưa có hook tách `VPCZoneIdentifier`.
  - Tên Route 53 giữ dấu chấm cuối, nên `create-hosted-zone` không kiểm nhãn.
  - Dashboard và event pattern không được parse JSON. Cạnh nối theo tên chưa phân biệt region. `expect.label` dạng có dấu chấm chưa hỗ trợ.
  - Không có kind `ssm-document`. Floci không thực thi vault lock của Backup.
- Route 53 health check và RDS event subscription chuyển sang Phase 10.
- Kết quả: contract test chạy đủ 61 kind và đều đạt. Server có 669 test đạt, web 445 test đạt.
