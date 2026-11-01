---
phase: 3
title: "Region, root account và emulator theo lab"
status: completed
priority: P1
effort: "26h"
dependencies: [2]
---

# Phase 3: region, root account và emulator theo lab

## Goal

Lab khai báo region (mặc định `ap-southeast-2`) hoặc nhiều region, cùng emulator. Mọi thành phần dùng đúng region và emulator đó: profile `lab`, provider, collector, builder, checker, twin, cache AZ. Graph có một root `account`, dưới đó là các `region` và nhóm `global`.

## Hiện trạng

- `config.py:13` `REGION = "us-east-1"`. Hằng số này được dùng ở:
  - `providers/aws.py:62,74`;
  - `emulator/aws_profile.py:39`;
  - `graph/collector.py:99,120,237`.
- **[Red team]** Có 42 file nguồn và test chứa `us-east-1`, nằm trong `server/src`, `server/tests`, `web/src` và `web/scripts`. Danh sách đầy đủ lấy bằng `grep -rl us-east-1 server web/src web/scripts` ở bước 1 và dán vào `notes/region-files.md`.
- `Lab` không có trường region; `extra="forbid"`.
- **[Red team] Root:** `graph/schema.py:81-83` bắt buộc có đúng một root `region`. `twin.py:55` lấy root bằng `next()` trên các node không cha. Web giả định một root ở `graph-to-scene.ts:19-24`, `api-fly-layer.tsx:71` và `layout.ts:75`.
- **[Red team] Emulator:**
  - Collector (`collector.py:296`) và profile `lab` (`aws_profile.py:33-43`) luôn trỏ Floci và ghi cứng key `test`. Chỉ checker và engine đi theo `lab.emulator`.
  - Moto bật IAM sau reset và đổi key admin `cloudy-labs-admin` mỗi lần reset; key nằm trong `moto-credentials.json`.
  - api-tap chạy trong container, nghe ở `0.0.0.0:4566`. `TAP_UPSTREAM` nằm trong closure, chỉ đọc lúc khởi động. Nếu thêm một endpoint quản trị để đổi upstream lúc chạy thì endpoint đó lộ ra mọi interface, nên không làm.
- `region_zones` được cache một lần duy nhất (`server/app.py:133`).
- `load_lab` (`loader.py:56-57`) ghép `(root or labs_dir()) / lab_id` mà không validate slug.

## Thiết kế

- **Schema lab:**
  - `Lab.region: str = "ap-southeast-2"`, validate theo danh sách region của botocore;
  - `Lab.regions: list[str]` cho lab cross-region, mặc định `[region]`, phải chứa `region`;
  - `config.DEFAULT_REGION = "ap-southeast-2"`, dùng khi chưa có lab mở.
- **[Red team] Slug:** `load_lab` và `content import` (Phase 4) validate slug theo `^[a-z0-9][a-z0-9-]{0,80}$`. Đường dẫn sau khi `resolve()` phải `is_relative_to(labs_dir())`.
- **[Red team] Root `account`** (quyết định 8):
  - Graph có đúng một root kind `account`, id là account id của emulator.
  - Con của nó là một node `region` cho mỗi phần tử của `lab.regions`, và một node `global` (vai trò `group`).
  - Schema đổi luật "một root region" thành "một root account; region và global là con trực tiếp của account".
  - `account`, `region` và `global` là kind trong `ec2.yaml`, nhóm "khung". `global` chỉ là dữ liệu ở phase này; Phase 8 thêm kind IAM vào đó.
  - `twin.py` bind theo `target.region` tường minh (mặc định `lab.region`), không dùng `next()`.
  - Web (`graph-to-scene.ts`, `api-fly-layer.tsx`, `layout.ts`) xử lý root `account`: các region đặt cạnh nhau, `global` nằm một bên.
  - Collector chạy mỗi region một lượt, cùng cô lập lỗi theo service của Phase 1. Kind có `scope: global` (IAM, CloudFront, Route 53, Organizations) chỉ thu một lần.
- **[Red team] Định tuyến emulator: mỗi emulator một tap.**
  - Mỗi tap có upstream cố định:
    - `api-tap-floci`: cổng 4566 → Floci 4567;
    - `api-tap-moto`: cổng 4568 → moto 5050.
  - Không có endpoint quản trị.
  - Hub nghe sự kiện từ cả hai tap.
  - `labctl start <lab>` ghi lại profile `lab`, gồm `region` và `endpoint_url` của tap theo emulator của lab. `labctl reset` và `down` không đổi region.
- **[Red team] Credential của moto:**
  - Profile `lab` khi chạy moto dùng `credential_process = labctl credentials moto`. Lệnh này đọc `moto-credentials.json` và in JSON theo định dạng `credential_process`.
  - Key không bao giờ được ghi vào `~/.aws/config` hay `credentials`, và không được in ra log.
  - Floci giữ key `test`, như hiện tại.
- Provider, collector, builder và twin lấy region và emulator từ `current_lab()`. Khi không có lab mở thì dùng mặc định.
- **[Red team] Cache AZ** theo khoá `(emulator, region)`.
- `compose.yaml`: `FLOCI_DEFAULT_REGION: ap-southeast-2`, cộng service `api-tap-moto`.
- **[Red team] Fixture Floci** được ghi lại ở `ap-southeast-2` bằng script commit `server/scripts/record-floci-fixtures.py`, không sửa tay. Test tra id bằng lookup trên fixture (tên tag, CIDR) thay cho id ghi cứng.

## Files to Create / Modify

- Modify: `server/src/cloudy_labs/config.py`, `labs/schema.py`, `labs/loader.py` (slug), `providers/aws.py`, `emulator/aws_profile.py`, `emulator/compose.yaml`, `engine.py`, `cli.py` (`credentials moto`), `graph/collector.py`, `graph/schema.py` (root `account`), `twin.py`.
- Modify: `server/src/cloudy_labs/server/app.py` (cache AZ), `server/hub.py` (hai tap), `server/twin_runner.py`, `builder/runner.py`, `tap/api_tap.py`.
- Modify: `server/src/cloudy_labs/registry/ec2.yaml` (kind `account`, `global`).
- Create: `server/scripts/record-floci-fixtures.py`.
- Modify: `web/src/scene/layout.ts`, `web/src/graph/graph-to-scene.ts`, `web/src/scene/api-fly-layer.tsx`, `web/src/scene/fixture.ts`, `web/src/builder/test-fixtures.ts`, `web/scripts/check-builder.mjs`, `e2e-builder-lab-06.mjs`, `e2e-builder-lab-07.mjs`.
- Modify: mọi file trong `notes/region-files.md`.
- Modify: golden `lab-06-07.graph.json`, `lab-06-07.twin.json`. Root đổi thành `account` và region đổi. Ghi chú trong commit.
- Modify: fixture lab 06/07 (CIDR và AZ theo `ap-southeast-2a/b/c`).
- Modify: `docs/labctl.md`, `docs/emulator-differences.md`.
- Create: `server/tests/test_region.py`, `server/tests/test_moto_credentials.py`.

## Tasks & Steps

1. Lập danh sách 42 file chứa `us-east-1`, lưu vào `notes/region-files.md`.
2. Thêm trường vào schema và validate slug. Viết test cho region sai, cho `regions` không chứa `region`, và cho slug `../x`.
3. Thay mọi chỗ dùng `REGION` bằng region của lab. Thêm một test grep: không còn `us-east-1` trong `server/src` ngoài danh sách region hợp lệ.
4. Root `account`: schema, collector nhiều region, twin bind theo region, web layout. Test graph hai region cộng `global`.
5. Hai tap, profile theo emulator và `credential_process` của moto. Test: sau `labctl reset` key moto đổi, `aws iam list-users --profile lab` vẫn chạy được; key không xuất hiện trong file config.
6. Ghi lại fixture Floci bằng script; sửa test sang lookup.
7. Cập nhật golden và các script e2e web.
8. Chạy lại e2e Lab 6/7 fixture ở `ap-southeast-2`.

## Verification

- `cd server && uv run pytest -q` và `uv run pytest -m docker -q`.
- `cd web && npm test && npm run typecheck`, rồi chạy `e2e-builder-lab-06.mjs` và `e2e-builder-lab-07.mjs`.
- Thủ công: `labctl start fixture-lab-06`, rồi `aws ec2 describe-availability-zones --profile lab` trả `ap-southeast-2a/b/c`.
- Lab thử với `emulator: moto` tạo IAM user bằng builder; cảnh hiện user đó từ moto; `cloudy-labs-admin` không hiện.
- `grep -r "AKIA\|aws_secret_access_key" ~/.aws/config` không có key moto. Chỉ in số lần khớp, không in giá trị.

## Risk / Rollback

- AZ của Floci ở `ap-southeast-2` có thể khác danh sách thật. Ghi vào `emulator-differences.md`.
- Đổi root làm đổi golden và id trong test web. Đổi trong một commit riêng để dễ revert.
