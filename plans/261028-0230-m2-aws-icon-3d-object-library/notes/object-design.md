# Thiết kế object và token màu

Nguồn sự thật là code trong `web/src/scene/aws-objects/`: `object-specs.ts` (kích thước, vị trí) và `object-theme.ts` (màu, tương phản). File này ghi lại lý do của các con số ở đó.

## Độ phủ glyph: chọn 0,75

So sánh 0,6, 0,75 và 0,85 trong gallery (`?view=gallery&coverage=…`), ở zoom mặc định và zoom 60. Ảnh: [coverage-compare.png](./coverage-compare.png), [gallery-light-zoom60.jpg](./gallery-light-zoom60.jpg).

| Độ phủ | Nhận xét |
|---|---|
| 0,6 | Glyph quá nhỏ ở zoom tổng quan, chi tiết route table và key pair khó đọc |
| **0,75** | Glyph đọc được ở zoom tổng quan, vẫn còn viền đế quanh glyph. Badge tròn gắn ở góc chỉ che một phần nhỏ |
| 0,85 | Glyph chạm phần bo góc của đế, và badge tròn (SG, EIP) ở góc che nhiều glyph hơn |

## Kích thước (đơn vị thế giới, lưới M0 có `CELL = 2,2`)

| Vai trò | Hình | Kích thước |
|---|---|---|
| `block` | Hộp bo góc (bán kính 0,08) | Cạnh 1,4. Cao: EC2 0,9; NAT và IGW 0,6; Route Table và Key Pair 0,4 |
| `tray-badge` | Ô vuông mỏng | Cạnh 0,9, cao 0,1. Nằm ở dải nhãn gần của khay; nhãn khay dịch phải 1,15 để nhường chỗ |
| `attach-badge` | Đĩa tròn | Bán kính 0,3, cao 0,14. Nằm trên mặt đỉnh của khối chủ, ở góc gần camera (+X, +Z); badge thứ hai lấy góc (−X, +Z) |
| `outline-only` | Không có object | AZ chỉ là đường viền đứt nét |

Glyph đặt trên mặt đỉnh, có cạnh bằng `side × 0,75`. Độ dày ép đùn bằng 12% cạnh glyph. `objectHeight()` trả về độ cao mặt trên cùng, dùng để gắn cạnh nối và nhãn.

Khối cạnh 1,4 trong ô 2,2 để lại khe 0,8. Badge gắn nằm hoàn toàn trên mặt đỉnh nên không đè sang khối bên cạnh.

## Màu và tương phản

Màu danh mục lấy từ SVG gốc. Chủ đề tối dùng màu sáng hơn và glyph màu nền tối `#0F141A`. Chủ đề sáng dùng glyph trắng. `object-theme.test.ts` kiểm tra mọi cặp đạt ≥ 3:1 theo công thức WCAG.

| Nhóm | Sáng (đế / glyph trắng) | Tỉ lệ | Tối (đế / glyph `#0F141A`) | Tỉ lệ |
|---|---|---|---|---|
| Compute | `#ED7100` | 3,02 | `#F58A2B` | 7,53 |
| Networking, VPC | `#8C4FFF` | 4,49 | `#A57BFF` | 6,06 |
| Security | `#DD344C` | 4,50 | `#EC6478` | 5,87 |
| Region, subnet riêng | `#00A4A6` | 3,06 | `#2CC7C9` | 8,91 |
| Subnet công khai | `#7AA116` | 3,03 | `#9BC93A` | 9,52 |

Ở chủ đề sáng, compute, region và subnet công khai chỉ vừa qua ngưỡng 3:1. Đó là màu gốc của AWS. Nếu cần tương phản cao hơn thì phải làm tối màu đế, tức là lệch khỏi màu nhận diện. Glyph trắng trông hơi xám do đổ bóng; chấp nhận được.

Ảnh: [gallery-light.jpg](./gallery-light.jpg), [gallery-dark.jpg](./gallery-dark.jpg), [scene-light.jpg](./scene-light.jpg), [scene-dark.jpg](./scene-dark.jpg), [scene-light-zoom40.jpg](./scene-light-zoom40.jpg), [scene-selected.jpg](./scene-selected.jpg).

## Rủi ro: LOD

Ở zoom tổng quan của cảnh 200 node, glyph vẫn nhận ra được nhờ màu đế và hình khối. Chưa cần LOD. Nếu cảnh lớn hơn làm glyph thành nhiễu, cách xử lý là ẩn instanced mesh glyph khi zoom dưới ngưỡng, giống `LABEL_MIN_ZOOM` của nhãn. Việc này chỉ thêm một cờ `visible` cho mỗi loại, không đổi số draw call ở zoom gần.

## Hoạt ảnh và trạng thái nghỉ

- Hoạt ảnh xuất hiện (easeOutBack 450 ms, so le 4 ms) chỉ chạy cho id mới với layer. Id đã hiện giữ nguyên kích thước khi danh sách placement đổi; id bị gỡ sẽ được quên, nên nếu thêm lại thì nó chạy hoạt ảnh lại. Code: `entrance.ts`.
- Xung trên cạnh nối đứng yên khi cảnh nghỉ (`frameloop="demand"`, 0 khung hình lúc idle). Người dùng chấp nhận ngày 2026-10-28.

