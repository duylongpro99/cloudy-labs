# Coverage danh mục sau dịch vụ đợt 1, 2 và 3

## Sau đợt 3

Chạy ngày 2026-10-31 trên Floci 2.3.0, cùng lệnh với [mốc](coverage-baseline.md).

| Kết luận | Mốc | Sau đợt 1 | Sau đợt 2 | Sau đợt 3 |
|---|---|---|---|---|
| blocked | 59 | 61 | 61 | 61 |
| gap | 407 | 273 | 121 | 0 |
| ready-with-caveats | 63 | 195 | 347 | 468 |
| ready | 1 | 1 | 1 | 1 |

Đợt 3 thêm 51 kind cho các service biên, tin nhắn, triển khai, di chuyển dữ liệu và quản trị. Kịch bản Floci đợt 3 được ghi vào `server/tests/fixtures/graph/floci-describe-wave-3/`, cho golden `wave-3.graph.json` gồm 123 node và 88 cạnh, không có cảnh báo.

Không còn lab `gap` nào. Mỗi lab `blocked` đều nêu đúng service hoặc API Floci 2.3.0 thiếu:

| Lý do | Số lab |
|---|---|
| FSx | 18 |
| Site-to-Site VPN | 11 |
| Direct Connect | 6 |
| EBS snapshot | 5 |
| Storage Gateway, CodeCommit | 4 / 4 |
| placement group, RDS Oracle, RDS SQL Server, X-Ray | 3 mỗi loại |
| Snow Family | 2 |

Một lab có thể mang nhiều lý do.

Bước 4 của phase không cần mục `catalog-overrides.yaml` mới. Lab `gap` cuối cùng hết khi thêm kind. API thiếu ở mức op được báo thẳng từ `floci-ops-2.3.0.json` khi kiểm một lab.

Service Floci thiếu không có file registry riêng: chúng đã ra `blocked` qua `floci-ops` và nghiên cứu danh mục. Một kind không có `list` sẽ bị coi là kind cấu trúc.

## Sau đợt 2

Chạy ngày 2026-10-31 trên Floci 2.3.0, cùng lệnh với [mốc](coverage-baseline.md).

| Kết luận | Mốc | Sau đợt 1 | Sau đợt 2 |
|---|---|---|---|
| blocked | 59 | 61 | 61 |
| gap | 407 | 273 | 121 |
| ready-with-caveats | 63 | 195 | 347 |
| ready | 1 | 1 | 1 |

Đợt 2 thêm 14 file registry: cloudwatch, logs, events, scheduler, backup, cloudformation, dynamodb, kms, ssm, secretsmanager, efs, elbv2, autoscaling và route53. Tổng cộng 27 kind mới.

- Kịch bản Floci đợt 2 được ghi vào `server/tests/fixtures/graph/floci-describe-wave-2/`: 122 call, 54 node, 33 cạnh, không có cảnh báo. Golden là `wave-2.graph.json`; test là `test_collector_replay_wave_2.py`.
- Bản ghi không chứa giá trị parameter hay secret nào, và có test kiểm điều này.

Không còn lab `gap` nào vì thiếu cả một service của đợt 1 hoặc 2. Còn hai kind lẻ, chuyển sang Phase 10:

- Route 53 health check: 1 lab.
- RDS event subscription: 1 lab, chung lý do với dms, docdb, neptune và redshift.

Mọi lý do `gap` còn lại thuộc các service của Phase 10. Nhiều nhất là cloudfront (11), dms (11), apigateway (10), cloudtrail (9), sqs (9) và sns (8).

## Sau đợt 1

Chạy ngày 2026-10-31 trên Floci 2.3.0, cùng lệnh với [mốc](coverage-baseline.md). Contract test chạy đủ 36 kind và đều đạt (`registry/contract-results.json`); [coverage.md](../../../docs/coverage.md) đã sinh lại từ lần chạy đó.

## Tổng theo kết luận (530 lab)

| Kết luận | Mốc | Sau đợt 1 | Thay đổi |
|---|---|---|---|
| blocked | 59 | 61 | +2 |
| gap | 407 | 273 | −134 |
| ready-with-caveats | 63 | 195 | +132 |
| ready | 1 | 1 | 0 |

Hai lab mới chuyển sang `blocked` là lab-077 (blue/green deployment của RDS) và lab-019 (replace root volume task). Floci 2.3.0 không có các API này, nên mỗi lab có một override riêng trong `catalog-overrides.yaml`.

Không còn lab `gap` nào chỉ vì thiếu ec2, vpc, rds, s3, lambda hoặc iam. Mọi lab `gap` còn lại đều cần ít nhất một service ngoài đợt 1.

## Lý do hàng đầu còn lại

| Lý do | Số lab |
|---|---|
| registry chưa có kind của cloudwatch | 28 |
| registry chưa có kind của cloudformation | 21 |
| registry chưa có kind của dynamodb | 20 |
| Floci thiếu FSx | 18 |
| registry chưa có kind của ssm / efs | 17 / 17 |
| registry chưa có kind của elbv2 / secretsmanager / kms | 16 / 16 / 16 |
| registry chưa có kind của route53 | 14 |
| registry chưa có kind của events | 13 |
| Floci thiếu Site-to-Site VPN | 11 |
| registry chưa có kind của cloudfront / backup / dms | 11 / 11 / 11 |

Một lab có thể mang nhiều lý do, nên tổng các dòng lớn hơn số lab `gap`.

## Khối lượng theo service

| File registry | Kind | Op builder | Contract | Caveat |
|---|---|---|---|---|
| ec2.yaml (gồm VPC mở rộng, EBS) | 22 (mốc 9) | 32 | 20 | 1 |
| rds.yaml | 9 | 10 | 7 | 6 |
| s3.yaml | 2 | 11 | 2 | 2 |
| lambda.yaml | 5 | 5 | 2 | 0 |
| iam.yaml | 5 | 11 | 5 | 1 |

Đợt 1 cũng thêm icon cho mỗi kind mới và ghi lại kịch bản Floci của wave-1 (75 node, 52 cạnh), dùng làm golden cho replay.

## Số giờ thực tế

Phase yêu cầu ghi số giờ thực tế cho từng service, nhưng số đó **không đo được**. Các service được làm xen kẽ trong cùng một phiên, và mỗi lần sửa registry lại kéo theo việc ghi lại fixture, sinh lại golden và chạy lại contract test chung. Cả phase kéo dài khoảng 13:10Z đến 14:30Z, tính theo thời điểm đổi trạng thái trong plan. Con số này là thời gian của một agent, không phải giờ người làm, nên không so trực tiếp với ước tính 40h.

## Hệ quả cho Phase 9–10

- Thêm một kind tốn ít công khi Floci có đủ API và registry có sẵn cơ chế cần (list theo parent, enrich, edge, contract). Phần tốn công là mọi thứ phải đồng bộ sau đó: ghi lại fixture trên Floci mới, golden, export registry sang web và chạy đủ contract.
- Phase 9 nên làm theo lô mỗi service, rồi mới ghi lại fixture và chạy contract một lần cho cả lô.
- Mỗi API mới cần được thử trên Floci trước khi viết kind. Đợt 1 phát hiện 2 lab bị chặn chỉ khi chạy catalog.
- Thứ tự gợi ý theo số lab còn chờ: cloudwatch, cloudformation, dynamodb, ssm, efs, elbv2, secretsmanager, kms.
- FSx, Site-to-Site VPN và Direct Connect bị chặn vì Floci không có. Làm kind cho chúng không gỡ được lab nào.
