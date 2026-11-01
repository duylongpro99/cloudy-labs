---
phase: 10
title: "Dịch vụ đợt 3: phần còn lại Floci hỗ trợ"
status: completed
priority: P2
effort: "50h"
dependencies: [6]
---

# Phase 10: dịch vụ đợt 3

## Goal

Mọi service còn lại trong danh mục mà Floci có API đều có mục registry. Service và API Floci thiếu được đánh dấu `missing` để coverage báo `blocked` đúng lý do. Sau phase này, `coverage --catalog` không còn lab `gap`.

## Phạm vi

- **Floci có API.** Số trong ngoặc là số lab nhắc tới; **[Red team]** giờ ước tính đặt sau dấu `·`.
  - CloudFront (11) · 3, DMS (11) · 4;
  - CodePipeline, CodeDeploy, CodeBuild, CodeArtifact (11) · 6;
  - API Gateway v1/v2 (10) · 4, CloudTrail (9) · 2, SNS (9) · 2, SQS (9) · 2, DataSync (7) · 3;
  - ElastiCache (7, Redis thật) · 5, Athena/Glue (6) · 3, ECS (6) · 5, EKS (4) · 5, ECR (4) · 2;
  - Network Firewall (4) · 2, Config (4) · 2, Elastic Beanstalk (4) · 4, Cognito (4) · 2, Transfer (3) · 2, Budgets (3) · 2;
  - Global Accelerator, Organizations, STS, WAFv2, ACM, Kinesis, Step Functions, GuardDuty, Inspector, Security Hub (mỗi cái ≤ 2 lab) · tổng 10, khoảng 1 giờ mỗi cái, chỉ cần `list`.

  Tổng khoảng 80 giờ nếu làm đủ kind phụ. Phase này giới hạn ở 50 giờ:
  - kind tối thiểu là tài nguyên chính của service;
  - op builder gồm create, delete và một modify phổ biến nhất;
  - kind phụ chỉ thêm khi CSV hoặc nội dung lab cần.
- **Floci thiếu.** Đánh dấu `floci.status: missing`, không có op:
  - FSx (18);
  - Site-to-Site VPN, Customer Gateway, VGW (11);
  - Direct Connect (6);
  - Storage Gateway (4);
  - X-Ray (3);
  - Snow Family (2);
  - Amplify (1);
  - CodeCommit.

  API thiếu ở mức op đã nằm trong `catalog-overrides.yaml` (Phase 6, Phase 8).
- **[Red team]** Service global (CloudFront, Organizations, WAF global, Global Accelerator) có `scope: global` và nằm dưới node `global` của root `account` (Phase 3).

## Files to Create / Modify

- Create: các file `server/src/cloudy_labs/registry/<service>.yaml` cho từng service ở trên, gồm cả file cho service `missing` (chỉ có `floci.status` và lý do).
- Modify: `registry/catalog-overrides.yaml`, `contract-results.json`, `docs/coverage.md`, `docs/emulator-differences.md`, icon trong `web/src/scene/aws-objects/icons/` và `NOTICE.md`.

## Tasks & Steps

1. Làm như Phase 8, bước 1–6, cho từng service có API. Ghi giờ thực tế.
2. Viết mục `missing` cho service thiếu, kèm link docs Floci tại tag đang ghim.
3. Chạy `labctl coverage --catalog`; ghi kết quả cuối vào `notes/coverage-progress.md`.
4. Soát các lab còn `gap`. Mỗi lab được xử lý bằng một trong ba cách:
   - thêm hoặc sửa mục registry;
   - thêm mục `catalog-overrides.yaml` (API Floci thiếu), có đối chiếu với mục lục;
   - sửa `extract.py` khi chứng minh được là trích sai, **kèm test fixture**.

   **[Red team]** Không có lối thoát nào khác. Không được xếp lab vào `blocked` hay `ready` bằng tay mà không có bằng chứng như trên.

## Verification

- `uv run pytest -q` và `uv run pytest -m docker tests/test_registry_contract_docker.py -q`.
- `uv run labctl coverage --catalog ...`: `gap` = 0. Mọi lab `blocked` đều chỉ ra service hoặc API Floci thiếu.
- `git log -p -- server/src/cloudy_labs/coverage/extract.py`: mọi commit sửa file đều có test đi kèm.

## Lệch so với thiết kế

- Service Floci thiếu (FSx, VPN, Direct Connect, Storage Gateway, X-Ray, Snow, Amplify, CodeCommit) **không có file registry `missing`**. Chúng đã ra `blocked` đúng lý do qua `floci-ops-2.3.0.json` và nghiên cứu danh mục. Thêm vào registry một kind không có `list` thì kind đó bị coi là kind cấu trúc.
- **Không thêm mục `catalog-overrides.yaml` nào.** `gap` về 0 chỉ nhờ thêm kind. Ở chế độ một lab, API Floci thiếu được báo thẳng từ `floci-ops` (`floci-missing-api`).
- Kịch bản đợt 3 ghi lời gọi `list`/`describe` của **cả registry**, không chỉ kind đợt 3, vì cạnh đợt 3 trỏ về kind của đợt trước. Mỗi bản ghi giữ danh sách kind đã ghi (`kinds.json`); replay chỉ dựng các kind đó, nên kind thêm về sau không làm hỏng fixture cũ.
- Builder:
  - Lệnh CLI của CodeDeploy là `aws deploy`, của Config là `aws configservice`.
  - Tham số `Endpoint` của `sns subscribe` đổi thành `--notification-endpoint`.
  - Phần trích lệnh của coverage có bảng ánh xạ ngược, kèm test.
- Hook mới:
  - `common.last_segment` lấy tên ở cuối ARN hoặc URL (SQS, SNS).
  - `common.s3_uri_bucket` lấy bucket từ URI `s3://`, cho DataSync location, Athena workgroup, Glue database và crawler.
- Registry xuất `signingName` của từng service, đúng tên service mà api-tap báo (`monitoring`, `elasticloadbalancing`, `apigateway`...). Web chỉ ghép danh từ của action với kind cùng service. Nếu không, `CreateRouteTable` ứng với cả route table lẫn route của HTTP API.
- `_scene_problems` tìm container theo kind trước, theo tên sau, vì tên chỉ duy nhất trong một kind: một ECR repository có thể trùng tên với Beanstalk application.
- Sanitizer thêm luật tên cho `SolutionStackName` của Beanstalk và `DomainName` của ACM (có wildcard).
- `test_coverage.py` dựng registry con và bỏ cạnh trỏ ra ngoài tập con. Nhờ đó RDS event subscription giữ được cạnh `notifies` tới SNS topic.
- `labctl down` liệt kê container service Floci tạo mà không gắn owner (ECR, Athena, ElastiCache, EKS) kèm lệnh `docker rm -f`, không tự xoá chúng.
- Giới hạn đã ghi ở [emulator-differences.md](../../docs/emulator-differences.md):
  - CloudFront và WAF chỉ được contract tạo và xoá, vì sửa cần `ETag`/`LockToken`.
  - WAF scope `CLOUDFRONT` không được vẽ.
  - OU lồng nhau không được vẽ.
  - ECS, CodeBuild, CodeArtifact và CodePipeline không mang tag lab. Beanstalk không có `TagResource`.
  - Query Athena luôn `FAILED`.
  - DMS, DataSync, Glue crawler, Transfer và RDS event subscription chỉ có control plane.
  - Inspector và Security Hub không tắt được.
- Số giờ thực tế không đo được, cùng lý do với đợt 1 ([coverage-progress.md](notes/coverage-progress.md#số-giờ-thực-tế)).

Contract registry (2026-11-01): 103/105 kind đạt. Hai kind trượt chỉ vì vượt ngưỡng 2,0 s khi máy tải cao (2,09 s và 2,33 s). Kind trượt đổi giữa các lần chạy, ngưỡng giữ nguyên. Chi tiết ở [notes/e2e-results.md](./notes/e2e-results.md).
