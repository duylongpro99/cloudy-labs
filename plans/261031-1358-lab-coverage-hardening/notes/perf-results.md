# Hiệu năng sau khi cảnh đọc registry

Đo ngày 2026-10-31. Máy: Apple M1 Pro, Chrome 156 (ANGLE Metal), canvas 1280×800 CSS px, fixture 200 node của `web/src/bench`. Mỗi lượt khoảng 10 s. Ngưỡng NFR2: ≥ 50 fps, nghĩa là frame p95 ≤ 20 ms.

| Lượt | Post / ghost | Chủ đề / DPR | fps TB | frame ms p50 / p95 / max | Ghi chú |
|---|---|---|---|---|---|
| chrome-flat-dark-dpr1-run1 | flat | dark / dpr 1 | 120 | 8.3 / 9.4 / 16.7 | 111 draw call, 203552 tam giác |
| chrome-flat-dark-dpr2-run1 | flat | dark / dpr 2 | 120 | 8.3 / 9.6 / 15.1 | 111 draw call, 203552 tam giác |
| chrome-flat-light-dpr1-run1 | flat | light / dpr 1 | 120 | 8.3 / 9.2 / 13.3 | 111 draw call, 203552 tam giác |
| chrome-flat-light-dpr2-run1 | flat | light / dpr 2 | 120 | 8.3 / 9.4 / 15.9 | 111 draw call, 203552 tam giác |
| chrome-full-dark-dpr1-run1 | full | dark / dpr 1 | 120 | 8.3 / 9.3 / 9.5 | 189 draw call, 212369 tam giác |
| chrome-full-dark-dpr2-run1 | full | dark / dpr 2 | 120 | 8.3 / 9.2 / 10.9 | 189 draw call, 212369 tam giác |
| chrome-full-light-dpr1-run1 | full | light / dpr 1 | 120 | 8.3 / 9.2 / 9.5 | 189 draw call, 212369 tam giác |
| chrome-full-light-dpr2-ghosts20-run1 | full + 20 ghost | light / dpr 2 | 120 | 8.3 / 9.2 / 10 | 211 draw call, 240273 tam giác |
| chrome-full-light-dpr2-run1 | full | light / dpr 2 | 120 | 8.3 / 9.2 / 9.5 | 189 draw call, 212369 tam giác |
| chrome-idle-run1 | idle | — | — | — | 0 frame trong 10 s |
| chrome-lite-dark-dpr1-run1 | lite | dark / dpr 1 | 120 | 8.3 / 9.3 / 15.3 | 114 draw call, 203555 tam giác |
| chrome-lite-dark-dpr2-run1 | lite | dark / dpr 2 | 120 | 8.3 / 9.3 / 12.4 | 114 draw call, 203555 tam giác |
| chrome-lite-light-dpr1-run1 | lite | light / dpr 1 | 120 | 8.3 / 9.3 / 13.1 | 114 draw call, 203555 tam giác |
| chrome-lite-light-dpr2-run1 | lite | light / dpr 2 | 120 | 8.3 / 9.3 / 12.2 | 114 draw call, 203555 tam giác |

Kết luận: mọi lượt đạt khoảng 120 fps (giới hạn vsync), p95 ≤ 9.6 ms, tức đạt NFR2. Khi rảnh, cảnh không vẽ lại frame nào. Thêm 20 ghost mục tiêu làm draw call tăng từ 189 lên 211.

Kết quả JSON thô nằm trong `web/bench-results/` (gitignored). Bộ kết quả trước khi đổi sang registry được giữ ở `web/bench-results-before-registry-*`.

## Collector theo lab (tập kind đóng)

Đo ngày 2026-10-31, Floci 2.3.0 trên Docker Desktop (Apple M1 Pro), region ap-southeast-2. Trạng thái: 1 VPC, 4 subnet, 1 SG, 1 key pair, 1 Elastic IP, cộng VPC mặc định. Mỗi dòng 20 lần `collect()` sau một lần làm nóng.

| Tập kind | Số kind thu | Node | p50 | p95 | max |
|---|---|---|---|---|---|
| Toàn registry | 11 | 24 | 31 ms | 62 ms | 64 ms |
| fixture-lab-06 | 9 | 23 | 26 ms | 53 ms | 54 ms |
| fixture-lab-07 | 9 | 23 | 24 ms | 49 ms | 58 ms |

Hiện registry chỉ có kind EC2, và các service được gọi song song, nên tập đóng chỉ bớt khoảng 15%. Lợi ích thật đến khi Phase 8–10 thêm service: một lab EC2 sẽ không gọi RDS, S3, Lambda… ở mỗi lần refresh.

Tập kind của một lab gồm: kind trong palette (alias đã mở rộng), kind trong target, mọi kind reachability khi lab có kind mạng, và kind hub đã thấy (từ graph hoặc từ sự kiện ghi của api-tap). Lab không nêu kind nào thì thu toàn registry. Đổi lab thì xoá kind đã thấy.

## Cảnh 200 node có kind đợt 1

Đo ngày 2026-10-31, cùng máy và trình duyệt như trên. Biến thể `kinds=mixed` của `syntheticGraph`: cứ 4 instance thì 3 cái đổi thành một kind block có icon của RDS, S3, Lambda hoặc IAM, xoay vòng. Badge SG và EIP chỉ giữ trên kind host. Tổng vẫn 200 node trên cảnh.

| Lượt | Hậu kỳ | Theme / DPR | fps | frame p50 / p95 / max (ms) | Ghi chú |
|---|---|---|---|---|---|
| chrome-full-light-dpr2-mixed-run1 | full | light / dpr 2 | 120 | 8.3 / 9.3 / 9.5 | 238 draw call, 245917 tam giác |
| chrome-full-dark-dpr2-mixed-run1 | full | dark / dpr 2 | 119 | 8.3 / 9.3 / 14.4 | 238 draw call, 245917 tam giác |

Kết luận: đạt NFR2 (≥ 50 fps) với các kind mới. Draw call tăng từ 189 lên 238 vì mỗi icon mới là một vật liệu riêng. Lượt đo chạy trước khi thêm kind `s3-multipart-upload`; kind này chỉ là một icon nữa trong vòng xoay.
