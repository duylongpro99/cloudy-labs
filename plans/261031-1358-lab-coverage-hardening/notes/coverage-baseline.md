# Mốc coverage danh mục (trước Phase 8)

Chạy ngày 2026-10-31 trên Floci 2.3.0 (`sha256:e0b292df4dc9…`). Contract test của 9 kind EC2 đều đạt. Lệnh:

```sh
cd server && uv run labctl coverage --catalog ../plans/reports/researcher-261031-1358-labaws-catalog-and-floci-coverage.csv
```

Độ tin cậy bị giới hạn bởi metadata công khai (namespace API, tiêu đề, mục lục). Trang lab thật có thể cần nhiều hơn.

## Tổng theo kết luận (530 lab)

| Kết luận | Số lab |
|---|---|
| blocked | 59 |
| gap | 407 |
| ready-with-caveats | 63 |
| ready | 1 |

Lab `ready` duy nhất là lab-27 (chỉ gọi `sts`). Caveat của nhóm `ready-with-caveats`: `control-plane-only` (theo cột `floci_fit`), `reachability-analysed`, `no-api-metadata` (CSV không ghi namespace nào) và `namespace-level`.

## Lý do hàng đầu

| Lý do | Số lab |
|---|---|
| registry chưa có kind của rds | 118 |
| registry chưa có kind của s3 | 73 |
| registry chưa có kind của lambda | 53 |
| registry chưa có kind của cloudwatch | 28 |
| registry chưa có kind của iam | 21 |
| registry chưa có kind của cloudformation | 21 |
| registry chưa có kind của dynamodb | 20 |
| Floci thiếu FSx | 18 |
| registry chưa có kind của ssm / efs | 17 / 17 |
| registry chưa có kind của elbv2 / secretsmanager / kms | 16 / 16 / 16 |
| Floci thiếu Site-to-Site VPN | 11 |
| mục lục nêu Load Balancer, Transit Gateway, Network ACL | 10 / 8 / 6 |

## Hai quy tắc thêm khi chạy mốc này

Red-team finding #4 nói: chấm ở mức namespace thì lab thiếu op vẫn ra `ready`. Lần chạy đầu cho 38 lab `ready`, trong đó có lab EBS volume, VPC endpoint, PrivateLink, Spot và IPv6. Registry chưa có kind nào cho các thứ đó. Vì vậy chế độ danh mục thêm hai quy tắc:

- Tên tài nguyên trong tiêu đề hoặc mục lục mà chỉ botocore biết, thuộc service lab gọi, thành `gap` (`no-kind-for-resource`).
- Lab chỉ có bằng chứng "registry có kind nào đó của service này" nhận caveat `namespace-level`, không bao giờ là `ready`.

Hệ quả: số `gap` ở mốc này là cận dưới. Nhiều lab EC2 nằm ở `ready-with-caveats/namespace-level` vẫn có thể thiếu kind (EBS volume, endpoint). Chỉ nội dung lab cục bộ (`labctl coverage <lab>`) mới xác nhận được.
