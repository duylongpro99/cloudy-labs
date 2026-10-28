# Số tam giác của glyph ép đùn (Phase 2), 2026-10-28

Sinh bằng `node web/scripts/glyph-stats.mjs <ứng viên…>`. Thông số: `depth` 0,12 so với cạnh lớn nhất, không bevel, đã bỏ thuộc tính `uv`. Ngân sách: ≤ 2.000 tam giác cho mỗi glyph; số in đậm là vượt ngân sách.

| Loại | File | Kích thước path | curveSegments 2 | curveSegments 3 | curveSegments 4 | curveSegments 6 | Đang dùng |
|---|---|---|---|---|---|---|---|
| region | `Region_32.svg` | 0.6 KB | 140 | 176 | 212 | 284 | 4 |
| vpc | `Virtual-private-cloud-VPC_32.svg` | 3.0 KB | 424 | 592 | 760 | 1096 | 4 |
| subnet-public | `Public-subnet_32.svg` | 0.9 KB | 200 | 264 | 328 | 456 | 4 |
| subnet-private | `Private-subnet_32.svg` | 0.9 KB | 200 | 264 | 328 | 456 | 4 |
| igw | `Res_Amazon-VPC_Internet-Gateway_48.svg` | 1.5 KB | 244 | 340 | 436 | 628 | 4 |
| nat | `Res_Amazon-VPC_NAT-Gateway_48.svg` | 2.7 KB | 456 | 604 | 752 | 1048 | 4 |
| route-table | `Res_Amazon-VPC_Router_48.svg` | 1.1 KB | 220 | 272 | 324 | 428 | 4 |
| security-group | `Security-Group-Shield_48.svg` | 0.2 KB | 84 | 100 | 116 | 148 | 4 |
| key-pair | `Res_AWS-Identity-Access-Management_Long-Term-Security-Credential_48.svg` | 3.8 KB | 652 | 884 | 1116 | 1580 | 4 |
| instance | `Res_Amazon-EC2_Instance_48.svg` | 0.7 KB | 384 | 400 | 416 | 448 | 4 |
| elastic-ip | `Res_Amazon-EC2_Elastic-IP-Address_48.svg` | 0.6 KB | 120 | 156 | 192 | 264 | 4 |
| ứng viên: Res_Amazon-Route-53_Route-Table_48.svg | `Res_Amazon-Route-53_Route-Table_48.svg` | 13.1 KB | **2460** | **3496** | **4532** | **6604** | — |

## Quyết định

- **Route Table dùng `Res_Amazon-VPC_Router_48.svg`.** Ứng viên Route 53 Route-Table vượt ngân sách ở mọi mức, kể cả `curveSegments` 2 (2.460 tam giác, gấp khoảng 7 lần VPC Router). VPC Router (mũi tên rẽ nhánh) cũng đúng nghĩa định tuyến trong VPC hơn icon của Route 53.
- **Giữ `curveSegments` 4 cho mọi icon.** Icon nặng nhất là Key Pair với 1.116 tam giác, còn dưới ngân sách. Không icon nào cần chỉnh riêng.
- Ước tính phần glyph của cảnh 200 node (179 khối, cộng badge khay và badge gắn): khoảng 90 nghìn tam giác. Số đo thật nằm trong `perf-results.md`.

## Kiểm tra lỗi hình học

`web/src/scene/aws-objects/svg-to-geometry.test.ts` kiểm cho từng icon:
- Bounding box sau chuẩn hoá có cạnh lớn nhất bằng 1, đáy ở y = 0, đỉnh ở y = 0,12, và được căn tâm.
- Mọi tam giác không suy biến có chiều quay khớp pháp tuyến, tức không bị đảo mặt sau phép lật trục của SVG. Mặt đỉnh hướng +Y, mặt đáy hướng −Y.
- Lỗ evenodd còn rỗng: tâm của khung chip EC2 rỗng còn viền khung đặc, và một vòng vuông tổng hợp rỗng ở giữa.
- Ảnh không bị lật gương: cạnh trên của SVG nằm ở −Z.
- Icon nhóm bỏ ô màu nền, chỉ giữ glyph.

Không icon nào cần xử lý lỗ riêng. Từ three r185, `SVGLoader.createShapes` đã bị deprecate; code dùng `ShapePath.toShapes()`, hàm này đọc `fill-rule` mà loader lưu trên path.
