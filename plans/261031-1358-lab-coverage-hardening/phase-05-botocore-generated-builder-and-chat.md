---
phase: 5
title: "Builder và chat sinh từ botocore"
status: completed
priority: P1
effort: "48h"
dependencies: [4]
---

# Phase 5: builder và chat sinh từ botocore

## Goal

Mọi thao tác create, modify, connect, attribute và delete của loại tài nguyên trong registry có sẵn trong builder và chat. Form, lệnh CLI và phần validate chung được sinh từ service model của botocore. 16 op hiện có giữ nguyên argv, UX và luật dạy học qua override. Mọi chốt an toàn hiện có được giữ ở lớp chung.

## Hiện trạng

- `builder/ops.py`: 16 op viết tay. Mỗi op có lớp `Params` pydantic, lambda `args`, `gesture` (`create|connect|attribute`, `:21`) và `creates`/`containers`/`source`/`targets`.
- **[Red team] Các chi tiết argv viết tay mà máy sinh không tái tạo được:**
  - tag dạng shorthand (`:158-161`);
  - `--count 1` (`:183-184`);
  - `create-route` chọn tham số theo tiền tố target (`:222-223`);
  - `--map-public-ip-on-launch` dạng cờ trần (`:232`);
  - `currentGroups` trong `server_fields` (`:247-250`).
- **[Red team] Các chỗ phụ thuộc lớp `Params`:**
  - `expectation()` và `practice_expectation()` khớp theo lớp Params (`:284-312`);
  - `validate.py:124-271` là một `match` theo lớp Params;
  - `suggest.py` dùng cả hai.
- **[Red team] Chốt an toàn hiện có:**
  - `validate.py:31-32,133-136` chặn tiền tố `file://`;
  - regex NAME và DESCRIPTION ở `:23-29`;
  - allowlist `PROPS` của chat ở `chat/prompt.py:55-56,111,136`.
- Web có các bảng theo tên op:
  - `form-model.ts:58-106` (`createDraft`);
  - `connect-rules.ts:22-39`;
  - `build-form.tsx` (`FIELD_LABEL`, `choices`, `MULTILINE`, `PLACEHOLDER`).
- Chat:
  - `prompt.py:17-43` `OP_NOTES` viết tay;
  - `:46-53` câu "Other services (S3, IAM, RDS, Lambda, ...) are not available" sẽ sai khi có service mới;
  - `suggest.py:114-136` kiểm op thuộc palette, rồi validate.
- `runner.py` chạy argv không qua shell, timeout 60 giây. Giữ nguyên.

## Thiết kế

- Registry thêm `ops` cho mỗi `ResourceType`:
  ```yaml
  ops:
    - id: create-db-instance         # [Red team] kebab-case = xform_name(api, '-'); ổn định
      api: CreateDBInstance          # tên operation trong botocore
      gesture: create                # create | modify | connect | attribute | delete
      fields: [DBInstanceIdentifier, Engine, DBInstanceClass, AllocatedStorage, MasterUsername,
               MasterUserPassword, DBSubnetGroupName, VpcSecurityGroupIds, MultiAZ, PubliclyAccessible]
      defaults: {Engine: mysql, DBInstanceClass: db.t3.micro, AllocatedStorage: 20}
      container: {param: DBSubnetGroupName, from: rds-db-subnet-group}
      choices: {Engine: [mysql, postgres, mariadb, aurora-mysql, aurora-postgresql]}
      validator: rds.instance_class  # hook tuỳ chọn, cho luật dạy học
      result_id: DBInstance.DBInstanceIdentifier
      expect: {kind: rds-db-instance, match: {name: DBInstanceIdentifier}}   # [Red team]
      server_fields: []              # [Red team] tham số server tự điền từ graph
      argv: null                     # [Red team] override cho 16 op cũ
      note: "Creates a managed DB instance. ..."   # đi vào prompt chat
  ```
- **[Red team] 16 op cũ giữ argv viết tay.** Hàm argv hiện tại được chuyển nguyên vào override `argv` (tên hàm trong `HOOKS`). Yêu cầu giống từng byte chỉ áp cho 16 op này. Op sinh mới được so sánh trên params đã parse theo botocore, không so chuỗi.
- **[Red team] `expect` thay `expectation()` khớp theo lớp.** Một hàm chung `expectation(op, params)` và `practice_expectation(op, params)` đọc `expect` của registry. Gesture `attribute` giữ nguyên ngữ nghĩa (đổi thuộc tính, không tạo node).
- **Sinh form** từ shape input của operation:
  - Kiểu:
    - string → ô nhập;
    - enum → select;
    - boolean → công tắc;
    - integer → số;
    - list of string → nhiều giá trị;
    - structure hoặc list of structure → trình soạn JSON có kiểm shape.
  - Bắt buộc: lấy từ `required` của shape.
  - Ô hiện mặc định: `fields`. Các tham số còn lại nằm sau "Nâng cao".
  - Tooltip: lấy từ `documentation` của shape, đã bỏ thẻ HTML.
- **Tham chiếu tài nguyên:** tham số có tên khớp `id` của một kind trong registry (ví dụ `VpcSecurityGroupIds` ↔ `security-group`) sẽ thành select lấy từ graph hiện tại và được validate là id có thật. Bảng khớp sinh từ registry, cộng `refs` khai báo tay khi tên không khớp.
- **Sinh argv** theo quy ước AWS CLI:
  - `aws <service> <xform_name(api, '-')>`;
  - tham số thành `--kebab-case`;
  - boolean thành `--flag` / `--no-flag`;
  - list of scalar: các giá trị cách nhau;
  - structure: chuỗi JSON. **[Red team] Không bao giờ sinh shorthand;**
  - **[Red team]** blob hoặc file (`ZipFile` của Lambda) thành `fileb://<đường dẫn do server chọn>`. Đường dẫn chỉ tới mẫu có sẵn trong `builder/lambda_samples/` theo id mẫu, và người dùng không nhập được đường dẫn.
  - Cuối lệnh luôn có `--profile lab --output json`.
- **[Red team] Bước 0: sanitiser bắt buộc**, chạy trước mọi validate. Nó duyệt mọi chuỗi, mọi phần tử list và mọi lá trong JSON lồng nhau:
  - từ chối giá trị bắt đầu bằng `file://` hoặc `fileb://`, không phân biệt hoa thường, kể cả sau khoảng trắng;
  - từ chối phần tử list bắt đầu bằng `-`, vì phần tử đó có thể bị hiểu thành cờ;
  - giữ allowlist ký tự NAME và DESCRIPTION cho các tham số tên và mô tả.
- **Validate chung**, theo thứ tự:
  1. sanitiser;
  2. `botocore.validate.ParamValidator` trên shape;
  3. tham chiếu tồn tại trong graph;
  4. **[Red team]** đích của modify hoặc delete không phải tài nguyên `protected`;
  5. container đúng loại theo `parent` của registry;
  6. hook `validator` nếu có.

  Mỗi lỗi giữ dạng thông điệp dạy học như hiện tại.
- **Chuyển 16 op cũ:** thành mục registry kèm override `argv`. Luật trong `validate.py` (CIDR trong VPC, không chồng lấn, SG không mở 22 cho `0.0.0.0/0`...) thành hook `validator`. `ec2_choices.py` thành `choices` động. `test_builder_validate.py` giữ nguyên kỳ vọng.
- **[Red team] Mọi chỗ dùng tên op** được cập nhật trong cùng phase:
  - `builder-panel.tsx`, `command-panel.tsx`, `use-builder.ts`;
  - test chat;
  - `lab.yaml` của fixture;
  - `server/tests/fixtures/chat/questions.yaml`;
  - `web/scripts/check-builder.mjs`.

  Id op giữ dạng kebab-case hiện có. Tên field mà chat thấy đổi sang tên tham số botocore (PascalCase); ghi điều này trong `docs/labctl.md` (mục chat).
- **Web:**
  - `build-form.tsx` render từ `describe()` mới (field, kiểu, enum, required, docs, ref kind);
  - `createDraft` lấy `defaults` từ registry;
  - `connect-rules.ts` tra registry: op `connect` khai báo `source` và `targets`;
  - palette hiện kind có op `create` trong `builder.palette` của lab.
- **Delete:** thêm cử chỉ xoá (menu chuột phải trên node) cho op `delete`. Node `protected` không có menu này. Người học vẫn thấy lệnh trước khi chạy.
- **Chat:**
  - catalog lấy từ ops của các kind trong palette lab;
  - `note` thay `OP_NOTES`;
  - câu giới hạn emulator sinh từ registry;
  - params gửi kiểu thật (enum, required) thay cho `"string"`.
  - **[Red team]** Props gửi sang LLM chỉ gồm `chat_props`, mặc định rỗng. Có deny-list cứng trên tên prop (`Environment`, `Password`, `Secret`, `Outputs`, `Parameters`, `UserData`); registry khai báo `chat_props` trùng deny-list thì không nạp được.

## Files to Create / Modify

- Create: `server/src/cloudy_labs/builder/shapes.py`. Đọc shape botocore, sinh mô tả field và sinh argv.
- Create: `server/src/cloudy_labs/builder/sanitize.py`. Sanitiser bước 0.
- Create: `server/src/cloudy_labs/builder/generic_validate.py`. Validate chung và gọi hook.
- Create: `server/src/cloudy_labs/builder/lambda_samples/` (code mẫu nhỏ, tự viết).
- Modify: `server/src/cloudy_labs/builder/ops.py` (op từ registry, `expectation` chung), `validate.py` (luật cũ thành hook), `ec2_choices.py`, `runner.py`.
- Modify: `server/src/cloudy_labs/registry/ec2.yaml` (thêm `ops` cho 16 op cũ), `registry/hooks.py`.
- Modify: `server/src/cloudy_labs/chat/prompt.py`, `chat/suggest.py`, `server/tests/fixtures/chat/questions.yaml`.
- Modify: `server/tests/fixtures/labs/fixture-lab-06/lab.yaml`, `fixture-lab-07/lab.yaml`, `fixture-vpc/lab.yaml` (nếu tên op đổi).
- Modify: `web/src/builder/build-form.tsx`, `form-model.ts`, `connect-rules.ts`, `palette.tsx`, `builder-api.ts`, `use-scene-builder.ts`, `builder-panel.tsx`, `command-panel.tsx`, `use-builder.ts`, `web/scripts/check-builder.mjs`.
- Create: `web/src/builder/json-field.tsx`, `web/src/builder/delete-menu.tsx`.
- Modify tests: `test_builder_ops.py`, `test_builder_validate.py`, `test_chat_prompt.py`, `test_chat_suggest.py`, `build-form.test.ts`, `form-model.test.ts`, `connect-rules.test.ts`, `builder-api.test.ts`.
- Create: `server/tests/test_builder_shapes.py`, `server/tests/test_builder_sanitize.py`.
- Modify: `docs/labctl.md` (mục chat).

## Tasks & Steps

1. Viết `sanitize.py` trước, theo kiểu TDD. Test các ca:
   - `file://` trong chuỗi, trong list, trong JSON lồng sâu, viết hoa, có khoảng trắng đầu;
   - phần tử list `--endpoint-url`;
   - tên sai allowlist.
2. Viết `shapes.py`. Test:
   - 16 op cũ qua override cho argv giống từng byte với argv hiện tại;
   - op sinh mới so sánh trên params đã parse: `CreateDBInstance`, `CreateFunction` (`fileb://` từ mẫu), `PutBucketPolicy` (JSON), `AuthorizeSecurityGroupIngress` (list of structure, không shorthand).
3. Viết validate chung và `expectation` chung. Chuyển luật cũ thành hook; `test_builder_validate.py` không đổi kỳ vọng.
4. Chuyển 16 op sang registry, rồi xoá các lớp `Params` viết tay. Cập nhật mọi chỗ dùng tên op.
5. Chặn `protected`: test xoá `cloudy-labs-admin` bị từ chối, cả qua builder và qua chat.
6. Web: form từ mô tả, trình soạn JSON, select tham chiếu, xoá.
7. Chat:
   - catalog, note và câu giới hạn sinh từ registry;
   - `chat_props` và deny-list.
   - Chạy `test_chat_live.py` nếu người dùng có provider; nếu không thì ghi lại là chưa chạy.
8. Chạy e2e builder Lab 6/7 fixture.

## Verification

- `cd server && uv run pytest tests/test_builder_sanitize.py tests/test_builder_shapes.py tests/test_builder_ops.py tests/test_builder_validate.py tests/test_chat_prompt.py tests/test_chat_suggest.py -q`
- `uv run pytest -m docker tests/test_builder_e2e_docker.py -q`
- `cd web && npm test && npm run typecheck`, rồi chạy `e2e-builder-lab-06.mjs` và `e2e-builder-lab-07.mjs`.
- Test: mục registry `test-only` có op `create` thì builder hiện trong palette, sinh form và lệnh đúng, chat thấy op đó, không sửa code.

## Risk / Rollback

- AWS CLI có vài tham số tuỳ biến không theo shape, ví dụ `--user-data` (CLI tự base64) và `--cli-input-json`. Ghi các ngoại lệ này trong `shapes.py` kèm test; không đoán.
- Trình soạn JSON là điểm UX yếu cho người mới. Override `fields` có thể tách structure thành các ô con cho op phổ biến (rule SG, route).
- Đổi tên field chat có thể làm câu trả lời LLM cũ (đã lưu) không khớp. Chat không lưu lịch sử giữa phiên, nên chấp nhận được.
