# Thử các lệnh EC2 của M4 trên Floci

Ngày thử: 2026-10-30. Floci trong stack `labctl up`, aws CLI 2.36.31 với profile `lab`, máy arm64.

| Lệnh | Kết quả |
|---|---|
| `create-security-group --tag-specifications ...` | exit 0, trả `{"GroupId": ...}`; Name tag và tag lab có trong `describe-security-groups` |
| `create-security-group` trùng tên trong cùng VPC | `InvalidGroup.Duplicate`, như AWS |
| `authorize-security-group-ingress --ip-permissions '[{"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]'` | exit 0, trả `SecurityGroupRules` |
| Cùng rule đó lần hai | **exit 0 và thêm rule trùng.** AWS thật trả `InvalidPermission.Duplicate`. Validate của builder phải tự chặn |
| Rule protocol `-1` | exit 0; `describe` không có `FromPort`/`ToPort` (collector ghi `from`/`to` là `null`) |
| Rule `icmp` với `FromPort`/`ToPort` `-1` | exit 0; `describe` giữ `-1`/`-1` |
| `create-key-pair --key-name k1 --tag-specifications ...` | exit 0, stdout có `KeyMaterial`. **Tag bị bỏ qua**: `describe-key-pairs` trả `Tags: []`. Không ảnh hưởng: collector lấy nhãn key pair từ `KeyName` |
| `create-key-pair` trùng tên | `InvalidKeyPair.Duplicate`, như AWS |
| `run-instances --image-id ami-amazonlinux2023-arm64 --instance-type t4g.micro --subnet-id ... --security-group-ids ... --count 1 --key-name k1 --user-data <nhiều dòng> --tag-specifications ...` | exit 0, `Instances.0.InstanceId`, state `pending`, rồi `running` |
| `modify-instance-attribute --instance-id ... --groups <sg cũ> <sg mới>` | exit 0; `describe-instances` liệt kê đủ hai SG. **Hỗ trợ, cạnh SG → instance giữ trong M4** |
| `modify-instance-attribute --groups sg-nope` | `InvalidGroup.NotFound` |
| `create-subnet` chồng lấn subnet có sẵn (câu hỏi mở từ M3) | `InvalidSubnet.Conflict`, như AWS |

Cổng host: instance có SG mở cổng 80 lúc chạy được Floci publish qua `floci-aws-ec2-fwd-i-<id>-80` (`0.0.0.0:30000->80/tcp`), SSH qua chính container instance (`2200->22`). Check `web-server-answers` đọc cổng này bằng `graph/host_ports.py`.
