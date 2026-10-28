---
phase: 4
title: "Kiểm tra giấy phép phụ thuộc"
status: completed
priority: P1
effort: "1h"
dependencies: [3]
---

# Phase 4: Kiểm tra giấy phép phụ thuộc

## Goal

Xác nhận mọi phụ thuộc dự kiến của XLabs, kể cả phụ thuộc gián tiếp, có giấy phép cho phép phân phối thương mại cùng một sản phẩm MIT (quyết định A8, A11).

## Files to Create / Modify

- Create: `spikes/m0-licenses/npm-licenses.json`. Kết quả `pnpm licenses list --json` chạy trên `spikes/m0-render/`.
- Create: `spikes/m0-licenses/python-licenses.json`. Kết quả `pip-licenses --format=json` chạy trong một venv tạm, đã cài các gói Python dự kiến: fastapi, uvicorn, boto3, pyyaml, httpx, aiohttp, anthropic, openai, moto.
- Create: `plans/261027-1353-m0-spike-emulator-and-render-validation/notes/license-summary.md`. Bảng tổng hợp, có đánh dấu các giấy phép cần chú ý.

## Phân loại

| Nhóm | Giấy phép | Xử lý |
|---|---|---|
| Cho phép | MIT, ISC, BSD-2/3, Apache-2.0, 0BSD, Unlicense, CC0, OFL-1.1 (font) | Ghi công trong `THIRD_PARTY_NOTICES` sau này |
| Cần xem xét | MPL-2.0, LGPL, CC-BY | Chỉ được dùng không sửa đổi. Ghi rõ điều kiện |
| Chặn | GPL, AGPL, SSPL, BUSL, Elastic, phi thương mại, không rõ giấy phép | Tìm phương án thay thế |

Ngoài phụ thuộc trong lockfile, kiểm tra thêm:
- Floci, MiniStack và moto: đọc file LICENSE ở đúng tag đã ghim trong Phase 1 và Phase 2.
- Font dùng trong Phase 3.
- AWS Architecture Icons: không phân phối kèm sản phẩm. Ghi lại để xác nhận lại quyết định F3.8.

## Tasks & Steps

1. Chạy `pnpm licenses list --json` trong `spikes/m0-render/` và lưu kết quả.
2. Tạo venv tạm bằng `uv`, cài các gói Python dự kiến cùng `pip-licenses`, xuất JSON rồi xoá venv.
3. Đọc LICENSE của các image emulator và font.
4. Phân loại tất cả theo bảng trên và viết `plans/261027-1353-m0-spike-emulator-and-render-validation/notes/license-summary.md`. Mọi gói thuộc nhóm "Chặn" hoặc "không rõ" phải có phương án thay thế.

## Verification

- `license-summary.md` liệt kê 0 gói thuộc nhóm "Chặn" mà chưa có phương án thay thế.
- Mọi gói "không rõ" đều đã được tra tay và có nguồn dẫn.

## Rủi ro và rollback

- Có thể có những gói gián tiếp không khai báo giấy phép trong metadata. Khi đó tra repo của gói đó.
- Rollback: xoá `spikes/m0-licenses/`.
