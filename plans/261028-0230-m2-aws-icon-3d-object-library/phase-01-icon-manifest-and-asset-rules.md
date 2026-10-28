---
phase: 1
title: "Manifest icon và quy tắc tài sản"
status: completed
priority: P1
effort: "1.5h"
dependencies: []
---

# Phase 1: Manifest icon và quy tắc tài sản

## Goal

Chốt mỗi loại tài nguyên F2.4 dùng file SVG nào trong `aws-icon-pkg/`, chép đúng các file đó vào repo bằng script, và đưa gói gốc ra khỏi git.

## Files to Create / Modify

- Modify: `.gitignore`, thêm `aws-icon-pkg/`.
- Create: `web/src/scene/aws-objects/manifest.ts`. Ánh xạ `kind → { role, source, sizeClass, fallback? }`.
- Create: `scripts/import-aws-icons.mjs`. Đọc manifest, chép từng SVG từ `aws-icon-pkg/` vào `web/src/scene/aws-objects/icons/`, báo lỗi nếu file nguồn không tồn tại.
- Create: `web/src/scene/aws-objects/icons/NOTICE.md`. Ghi nguồn (AWS Architecture Icons, bản 07312026), ngày tải, và ghi chú rằng các icon đã bị sửa đổi.

## Bảng ánh xạ đề xuất

| Loại (F2.4) | Vai trò | File nguồn | Ghi chú |
|---|---|---|---|
| Region | badge khay | `Architecture-Group-Icons_07312026/Region_32.svg` | |
| VPC | badge khay | `Architecture-Group-Icons_07312026/Virtual-private-cloud-VPC_32.svg` | |
| Subnet public | badge khay | `Architecture-Group-Icons_07312026/Public-subnet_32.svg` | |
| Subnet private | badge khay | `Architecture-Group-Icons_07312026/Private-subnet_32.svg` | |
| Availability Zone | chỉ viền | — | Theo quy ước AWS: AZ là đường viền gạch, không có icon |
| Internet Gateway | khối | `Resource-Icons_07312026/Res_Networking-Content-Delivery/Res_Amazon-VPC_Internet-Gateway_48.svg` | |
| NAT Gateway | khối | `.../Res_Amazon-VPC_NAT-Gateway_48.svg` | |
| Route Table | khối | `.../Res_Amazon-Route-53_Route-Table_48.svg` | Phương án khác: `Res_Amazon-VPC_Router_48.svg` (path nhẹ hơn nhiều: 1,6 KB so với 14 KB). Chọn ở bước 2 sau khi xem số tam giác |
| Security Group | badge gắn lên instance | — | Không có trong gói. Theo quy ước AWS, SG là viền đỏ quanh tài nguyên. Phương án: badge khiên tự vẽ cùng phong cách (màu `#DD344C`), cộng viền đỏ quanh các instance gắn SG |
| Key Pair | khối nhỏ | `Resource-Icons_07312026/Res_Security-Identity/Res_AWS-Identity-Access-Management_Long-Term-Security-Credential_48.svg` | Không có icon "Key Pair" riêng; icon credential dài hạn của IAM gần nghĩa nhất |
| EC2 Instance | khối | `Resource-Icons_07312026/Res_Compute/Res_Amazon-EC2_Instance_48.svg` | |
| Elastic IP | badge gắn lên NAT/instance | `Resource-Icons_07312026/Res_Compute/Res_Amazon-EC2_Elastic-IP-Address_48.svg` | |

## Tasks & Steps

1. Thêm `aws-icon-pkg/` vào `.gitignore`, xác nhận bằng `git check-ignore aws-icon-pkg`.
2. Viết `manifest.ts` theo bảng trên. Mỗi mục có `kind`, `role` (`block` | `tray-badge` | `attach-badge` | `outline-only`), `source` (đường dẫn tương đối trong gói) hoặc `selfDrawn: true`.
3. Viết `import-aws-icons.mjs`. Script chép file, giữ tên gốc, ghi `NOTICE.md`, và trả mã lỗi khác 0 nếu thiếu file.
4. Vẽ SVG khiên cho Security Group theo lưới 48×48, một path, một màu, giống cấu trúc của icon tài nguyên AWS để đi qua cùng pipeline.

## Verification

- `node scripts/import-aws-icons.mjs` thoát với mã 0 và chép đủ số file trong manifest.
- Test `manifest.test.ts`: mọi loại F2.4 có trong manifest, và mọi `source` trỏ tới file có trong `icons/`.
- `git status` không còn liệt kê `aws-icon-pkg/`.

## Rủi ro và rollback

- Nếu AWS phát hành bộ icon mới đổi tên file, chỉ phải sửa manifest. Script sẽ báo đúng file nào thiếu.
- Rollback: xoá `icons/`, `manifest.ts`, script và dòng `.gitignore`.
