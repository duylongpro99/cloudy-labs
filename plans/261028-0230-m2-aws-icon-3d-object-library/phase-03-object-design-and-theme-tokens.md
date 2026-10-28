---
phase: 3
title: "Thiết kế object và token sáng/tối"
status: completed
priority: P1
effort: "3h"
dependencies: [2]
---

# Phase 3: Thiết kế object và token sáng/tối

## Goal

Định nghĩa hình dạng cuối của từng vai trò object (khối, badge khay, badge gắn) và bộ màu cho hai chủ đề, đọc rõ ở góc isometric và hài hoà với khay đã dựng ở M0.

## Files to Create / Modify

- Create: `web/src/scene/aws-objects/object-specs.ts`. Kích thước, độ cao đế, vị trí glyph cho mỗi `role`.
- Create: `web/src/scene/aws-objects/object-theme.ts`. Token màu cho `light` và `dark`, theo nhóm danh mục AWS.
- Modify: token chủ đề chung của cảnh (theo dạng của `spikes/m0-render/src/scene/theme.ts`) để tham chiếu `object-theme.ts`.

## Thiết kế đề xuất

| Vai trò | Hình | Áp dụng cho |
|---|---|---|
| `block` | Đế khối vuông bo góc nhẹ, màu danh mục; glyph ép đùn nằm trên mặt đỉnh, màu sáng tương phản | EC2, NAT, IGW, Route Table, Key Pair |
| `tray-badge` | Ô vuông nhỏ dày mỏng đặt ở góc gần của khay, cạnh nhãn khay; glyph trắng ép đùn trên ô | Region, VPC, Subnet public/private |
| `attach-badge` | Badge tròn nhỏ gắn ở cạnh trên của khối chủ | Security Group (trên instance), Elastic IP (trên NAT/instance) |
| `outline-only` | Không có object, chỉ có đường viền | AZ |

Màu danh mục lấy từ chính file SVG: Compute `#ED7100`, Networking `#8C4FFF`, Security `#DD344C`; màu nhóm theo bảng F3.7. Chủ đề tối:
- Tăng độ sáng màu danh mục khoảng 10–15% (giống cách đã làm ở `spikes/m0-render`).
- Đổi glyph sang màu nền tối (`#0F141A`) hoặc trắng, chọn theo tương phản.
- Kiểm tra tương phản giữa glyph và đế đạt tối thiểu 3:1 ở cả hai chủ đề.

## Tasks & Steps

1. Dựng thử 3 biến thể tỉ lệ đế/glyph cho `block`: glyph phủ 60%, 75% và 85% mặt đỉnh. Chụp ở zoom mặc định và zoom gần, rồi chọn một.
2. Chốt kích thước badge sao cho không che nhãn khay và không đè lên khối gần nhất trong lưới bố cục của M0 (`CELL = 2,2`).
3. Viết token, tính tỉ lệ tương phản bằng một hàm nhỏ có test.
4. Ghi quyết định và ảnh so sánh vào `plans/261028-0230-m2-aws-icon-3d-object-library/notes/object-design.md`.

## Verification

- Test tương phản: mọi cặp glyph/đế ở cả hai chủ đề đạt ≥ 3:1.
- Ảnh so sánh 3 biến thể có trong `notes/`, kèm lý do chọn.

## Rủi ro và rollback

- Glyph nổi trên mặt đỉnh có thể khó đọc khi zoom xa. Nếu vậy, Phase 4 thêm LOD: khi zoom thấp thì ẩn glyph và chỉ giữ đế màu, tương tự cách nhãn node ẩn ở M0.
- Rollback: giữ màu M0 và bỏ hai file token.
