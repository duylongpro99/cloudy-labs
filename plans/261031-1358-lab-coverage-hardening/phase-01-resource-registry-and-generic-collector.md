---
phase: 1
title: "Registry loại tài nguyên và collector chung"
status: completed
priority: P1
effort: "38h"
dependencies: []
---

# Phase 1: registry loại tài nguyên và collector chung

## Goal

Mỗi loại tài nguyên được mô tả bằng đúng một mục dữ liệu. Collector, schema graph và twin đọc mục đó thay cho các bảng cứng. 12 kind hiện có cho ra golden graph giống hệt từng byte.

## Hiện trạng

- `graph/schema.py:14-33`: `Kind` (12 literal), `EdgeKind` (4 literal) và `PARENT_KINDS`. `:60` `emulator: Literal["floci"]`. `:81-83` bắt buộc có đúng một root `region`.
- `graph/collector.py`: `DESCRIBE` ở `:22-32` (9 lệnh EC2) và `build_graph` ở `:92-234`. `collect` dùng đúng một client `ec2` (`:297`).
- `labs/schema.py:45,82-85`: `BuilderKind` và `TargetKind` là literal riêng. `PARENT_KINDS` được dùng ở `labs/schema.py:9,112`.
- **[Red team] Các ca đặc biệt của collector hiện tại.** Registry phải diễn tả được hết, hoặc dùng hook có tên:

  | # | Ca đặc biệt | Vị trí | Cách diễn tả |
  |---|---|---|---|
  | 1 | `describe_vpc_attribute` theo từng VPC (DNS) | `:259-272` | stage `enrich` theo node |
  | 2 | `userData` theo từng instance | `:275-287` | `enrich` |
  | 3 | Cổng docker của instance | `:306-309` | hook `ec2.docker_ports` |
  | 4 | Lọc trạng thái đã xoá (`terminated`, `deleted`...) | `:36-37,147,186` | `filter` |
  | 5 | SG: chỉ ingress, rule bị làm phẳng | `:166-174` | props với JMESPath; egress thêm ở Phase 8 |
  | 6 | Cạnh EIP → NAT | `:145-154,213` | `edges` với `path` |
  | 7 | IP public loopback | `:193-196` | hook `ec2.public_ip` |
  | 8 | IP private ngoài CIDR | `:197-200` | hook `ec2.private_ip_guard` |
  | 9 | Chọn cha của IGW (VPC gắn đầu tiên) | `:141-143` | `parent` với `path` |
  | 10 | Id dự phòng | `:178,211` | `id` là danh sách path |
  | 11 | Route: bỏ `local`, bỏ target không có | `:115-118,217-226` | `filter` + `edges.optional` |
  | 12 | Subnet public/private | `_is_public` | hook `ec2.subnet_visibility` |
  | 13 | AZ là node tổng hợp `{vpc}/{az}` | `build_graph` | hook `ec2.az_groups` |
  | 14 | SG và EIP gắn vào host | `build_graph` | hook `ec2.attach_to_host` |

## Thiết kế

- Tạo thư mục mới `server/src/cloudy_labs/registry/`. Mỗi service có một file YAML. Registry được nạp và validate bằng pydantic (`extra="forbid"`) lúc khởi động.
- Một mục `ResourceType`:
  ```yaml
  - kind: rds-db-instance            # slug, duy nhất toàn registry
    service: rds                     # tên client boto3
    label: RDS DB instance
    list:
      method: describe_db_instances
      items: DBInstances
      paginate: true
      scope: null                    # [Red team] {parent_kind: vpc, param: Filters.vpc-id} cho list theo cha
    enrich:                          # [Red team] gọi thêm theo từng item
      - {method: describe_db_proxy_targets, per: item, params: {DBProxyName: DBProxyName}, merge_as: Targets}
    filter: {path: DBInstanceStatus, not_in: [deleting]}   # [Red team]
    id: [DBInstanceIdentifier]       # thử lần lượt
    name: DBInstanceIdentifier
    parent:                          # thử lần lượt, cái đầu tiên có giá trị thắng
      - {path: DBSubnetGroup.Subnets[0].SubnetIdentifier, kind: subnet}
      - {kind: region}
    edges:
      - {path: VpcSecurityGroups[].VpcSecurityGroupId, kind: attached, to: security-group, reverse: true}
      - {path: DBClusterIdentifier, kind: member-of, to: rds-db-cluster, optional: true}
    props: [Engine, EngineVersion, DBInstanceClass, MultiAZ, DBInstanceStatus, Endpoint.Address]
    chat_props: [Engine, DBInstanceClass, MultiAZ, DBInstanceStatus]   # [Red team] mặc định rỗng
    caveats:                         # [Red team] coverage đọc từ đây
      - {prop: MultiAZ, code: flag-only, text: "Floci lưu cờ Multi-AZ nhưng không có standby thật"}
    protected: null                  # [Red team] JMESPath; node khớp bị ẩn khỏi graph và builder
    view: {role: block, category: database, icon: Arch_Amazon-RDS_48.svg, order: 40}
    floci: {status: supported}       # supported | control-plane-only | missing
  ```
- `kind: subnet` trong `parent` là bí danh của `subnet-public` và `subnet-private`.
- **[Red team] Hook** là các hàm Python có tên trong một dict tĩnh `HOOKS` ở `registry/hooks.py`. YAML tham chiếu bằng tên (`hook: ec2.subnet_visibility`). Không dùng `importlib`, không nạp theo chuỗi module. Khi tên hook không có trong dict, registry không nạp được. Chỉ thêm hook mới khi dữ liệu không diễn tả được, và ghi lý do trong docstring.
- **[Red team] `protected`:** principal nội bộ như `cloudy-labs-admin` của moto bị ẩn khỏi graph. Phase 5 dùng cùng luật để từ chối modify và delete.
- `Kind` và `EdgeKind` thành `str`, validate theo registry trong `ResourceGraph`. `PARENT_KINDS`, `TargetKind` và `BuilderKind` cũng lấy từ registry. `emulator` thành `Literal["floci", "moto"]`.
- Collector chung:
  1. Gom các `ResourceType` cần thu, nhóm theo `service`.
  2. Gọi `list` trong thread pool, mỗi service một client. Kind có `scope` gọi sau khi đã có kind cha.
  3. Chạy `enrich`, `filter` và `protected`.
  4. Tạo node, giải cha, rồi giải cạnh.
  5. Loại node có cha bị thiếu, như trước.
- **[Red team] Cô lập lỗi theo service.** Khi một service lỗi (timeout, `UnknownOperation`, 5xx), mọi kind của service đó bị bỏ khỏi graph và `graph.warnings` có một mục `{service, error}`. Các service khác vẫn ra bình thường. Graph không bao giờ hỏng toàn bộ vì một service.
- Tham số `kinds` của `collect` giới hạn tập loại cần thu. Mặc định là toàn bộ registry; Phase 6 thu hẹp theo lab.
- **[Red team] Không quét Resource Explorer**, không có kind `unknown` phía server (quyết định 7). Web có node dự phòng cho kind nó không biết (Phase 2).

## Files to Create / Modify

- Create: `server/src/cloudy_labs/registry/__init__.py`. Gồm `load_registry()`, `ResourceType` và `Registry` (tra theo kind, theo service, `parent_kinds()`, `edge_kinds()`).
- Create: `server/src/cloudy_labs/registry/hooks.py`. Dict `HOOKS` gồm `subnet_visibility`, `az_groups`, `attach_to_host`, `docker_ports`, `public_ip`, `private_ip_guard`.
- Create: `server/src/cloudy_labs/registry/ec2.yaml`. Chứa 12 kind hiện có, đúng thứ tự và thuộc tính đang có.
- Modify: `server/src/cloudy_labs/graph/schema.py`. Kind và edge validate theo registry; thêm `warnings`; `emulator` có `moto`; `PARENT_KINDS` lấy từ registry.
- Modify: `server/src/cloudy_labs/graph/collector.py`. Collector chung, `collect(kinds=None)` và cô lập lỗi. Giữ `build_graph` cũ thành `legacy_build_graph` cho test đối chiếu; xoá ở cuối phase.
- Modify: `server/src/cloudy_labs/labs/schema.py`, `server/src/cloudy_labs/twin.py`. Bỏ literal, dùng registry.
- Create: `server/tests/test_registry.py`, `server/tests/test_collector_differential.py`.
- Modify: `server/tests/test_collector.py`, `test_graph_schema.py`, `test_schema.py`.

## Tasks & Steps

1. Viết model `ResourceType` và `Registry`, kèm các luật validate:
   - kind duy nhất;
   - `parent.kind`, `edges.to` và `scope.parent_kind` trỏ kind có thật;
   - không có vòng cha;
   - hook có trong `HOOKS`;
   - `chat_props` là tập con của `props`;
   - icon được khai báo (file được kiểm ở Phase 2).
2. Chuyển 12 kind EC2 sang `ec2.yaml`, theo bảng ca đặc biệt ở trên. Viết JMESPath cho id, cha và cạnh. Gói `jmespath` đã có sẵn qua botocore.
3. Viết collector chung: `scope`, `enrich`, `filter`, `protected` và cô lập lỗi.
4. **[Red team] Test đối chiếu.**
   - Chạy `legacy_build_graph` và collector mới trên `fixtures/graph/floci-describe/*`, cộng các fixture biến thể: id dự phòng, route có target không còn, instance `terminated`, IP public loopback.
   - Hai bên phải cho ra graph bằng nhau.
   - Golden `lab-06-07.graph.json` phải giống hệt từng byte.
5. Test cô lập lỗi: giả lập client RDS ném lỗi; graph vẫn có kind EC2 và có `warnings`.
6. Test registry thử: thêm `test-only.yaml` trong thư mục fixture. Graph phải nhận kind mới mà không sửa code.
7. Xoá `legacy_build_graph` khi test đối chiếu xanh.

## Verification

- `cd server && uv run pytest tests/test_registry.py tests/test_collector.py tests/test_collector_differential.py tests/test_graph_schema.py tests/test_schema.py tests/test_twin_binding.py -q`
- `uv run pytest -q`: toàn bộ server xanh; golden graph và twin không đổi (`git diff --exit-code server/tests/fixtures/graph/`).
- `uv run pytest -m docker tests/test_twin_docker.py -q` vẫn đạt.

## Risk / Rollback

- Một số quan hệ EC2 có thể không diễn tả được bằng JMESPath, ví dụ route → IGW/NAT với nhãn CIDR. Khi đó dùng hook và ghi lý do vào docstring.
- Rollback: phase nằm gọn trong một nhánh commit. Golden không đổi nên revert an toàn.
