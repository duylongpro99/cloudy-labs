---
phase: 4
title: "Web: form EC2, rule SG, gắn SG, tải .pem"
status: completed
priority: P1
effort: "8h"
dependencies: [3]
---

# Phase 4: Web: form EC2, rule SG, gắn SG, tải .pem

## Goal

Người học kéo SG, Key Pair, Instance từ palette vào cảnh, thêm rule inbound từ panel thuộc tính của SG, kéo cạnh SG → Instance, và tải `<tên>.pem` sau khi tạo key pair; mọi thứ vẫn chỉ đổi cảnh khi graph mới tới (F4.5).

## Files to Create / Modify

- Modify: `web/src/builder/builder-api.ts` (kiểu `LabInfo` thêm `images`, `instanceTypes`, `userData`; `Expect` thêm dạng `includes`; `Preview` thêm `practiceExpect`)
- Modify: `web/src/builder/form-model.ts` (`createDraft` cho 3 op create mới; `attributeDraft` cho rule SG khoá `groupId`, để trống `protocol`/`port`/`cidr` với gợi ý)
- Modify: `web/src/builder/connect-rules.ts` (SG → instance)
- Modify: `web/src/builder/drop-targets.ts` (`KIND_LABEL` thêm `security-group`, `key-pair`, `instance`)
- Modify: `web/src/builder/build-form.tsx` (select cho `securityGroupId`, `keyName`, `imageId`, `instanceType`, `protocol`; textarea cho `userData` và `description`; gợi ý không chặn cho UserData)
- Modify: `web/src/builder/command-panel.tsx` (cuộn lệnh dài; nút "Tải .pem")
- Modify: `web/src/builder/use-builder.ts` (`expectMet` hiểu `includes`)
- Modify: `web/src/builder/use-scene-builder.ts` và `web/src/scene/property-panel.tsx` (nút "Thêm rule inbound" trên SG)
- Modify: các test `*.test.ts` tương ứng; `web/src/builder/test-fixtures.ts`

## Tasks & Steps

- [x] `createDraft`:
  - `create-security-group`: `vpcId` khoá theo VPC được thả; `description` gợi ý "Lab web server"; tên theo `suggestName`.
  - `create-key-pair`: chỉ `name`.
  - `run-instances`: `subnetId` khoá; `imageId`, `instanceType` lấy phần tử đầu của `lab.images`/`lab.instanceTypes`; `securityGroupId` là SG đầu tiên cùng VPC (rỗng nếu chưa có, validate sẽ giải thích); `keyName` là key pair đầu tiên; `userData` là `lab.userData`.
- [x] Draft cho attribute có trường tự do: thay `fixedDraft` khoá mọi thứ trừ `destination` bằng danh sách trường tự do theo op (`destination` cho route; `protocol`, `port`, `cidr` cho rule SG). Gợi ý mặc định: `tcp`, `80`, `0.0.0.0/0`.
- [x] `connectOp`: SG → instance thành `modify-instance-attribute` với `{instanceId, groupId}`; báo sớm khi SG đã gắn vào instance đó (cạnh `attached` có sẵn).
- [x] `build-form.tsx`: lựa chọn của `securityGroupId` chỉ gồm SG cùng VPC với subnet; `keyName` gồm mọi key pair; textarea UserData font mono, cao khoảng 8 dòng. Gợi ý (không chặn) khi nội dung khớp `0\.0\.0\.0:80|--bind 0\.0\.0\.0|http\.server 80(?!.*--bind)`: "Trên Floci, IMDS đã chiếm 0.0.0.0:80 trong instance; bind vào IP private" kèm link `docs/emulator-differences.md`.
- [x] Nút "Tải .pem" trong command panel khi op là `create-key-pair`, exit 0 và stdout có `KeyMaterial`: dựng `Blob` từ `KeyMaterial`, tải về `<KeyName>.pem`. Gợi ý `chmod 400`. Không lưu key ở `localStorage`.
- [x] `expectMet`: `{node, prop, includes}` đạt khi `node.props[prop]` là mảng có phần tử chứa đủ các cặp khoá-giá trị của `includes` (với `source` thì so trong `sources`).
- [x] Nút "Thêm rule inbound" trên panel thuộc tính SG mở form attribute; panel cũng liệt kê rule hiện có (đã có trong `props.ingress`).

## Verification

- `cd web && pnpm test && pnpm typecheck`
- Test: `createDraft` cho 3 op; `connectOp` SG → instance (đúng, đã gắn, khác kind); `expectMet` với `includes`; gợi ý UserData bật/tắt đúng mẫu; nút .pem chỉ hiện khi stdout có `KeyMaterial`.
- `node scripts/check-builder.mjs` vẫn xanh (không hồi quy Lab 6).
