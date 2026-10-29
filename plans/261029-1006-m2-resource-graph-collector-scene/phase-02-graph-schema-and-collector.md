---
phase: 2
title: "Schema resource graph và collector"
status: completed
priority: P1
effort: "5h"
dependencies: []
---

# Phase 2: Schema resource graph và collector

## Goal

Một hàm `collect(provider) -> ResourceGraph` đọc mọi tài nguyên F2.4 từ Floci thành graph có schema, xác định (cùng trạng thái cho cùng JSON), và xử lý đủ 5 điểm của spike mục 2 (F2.1, F2.4).

## Files to Create / Modify

- Create: `server/src/cloudy_labs/graph/__init__.py`, `graph/schema.py` (pydantic), `graph/collector.py`, `graph/host_ports.py` (tra cổng host của instance qua Docker)
- Create: `server/tests/test_graph_schema.py`, `server/tests/test_collector.py`
- Create: `server/tests/fixtures/graph/floci-describe/*.json` (output `describe-*` lấy từ `spikes/m0-emulators/out/floci/`, sau bước cuối của Lab 6 + 7)
- Create: `server/tests/fixtures/graph/lab-06-07.graph.json` (golden, web đọc lại ở Phase 4)

## Tasks & Steps

1. **Schema** (`schema.py`), dùng camelCase khi xuất JSON:
   - `Node{id, kind, label, props: dict}`. `kind` thuộc đúng tập `AwsKind` của web: `region, vpc, az, subnet-public, subnet-private, igw, nat, route-table, security-group, key-pair, instance, elastic-ip`. Đối chiếu với `web/src/scene/aws-objects/manifest.ts` lúc làm.
   - `Contains{parent, child}`: cây Region ⊃ VPC ⊃ AZ ⊃ Subnet ⊃ Instance/NAT; IGW, route table, SG nằm trong VPC; key pair và EIP chưa gắn nằm trong Region.
   - `Edge{id, kind, from, to, label}` với `kind`: `route` (route table → IGW/NAT, `label` là CIDR đích), `association` (route table → subnet), `attached` (SG → instance, EIP → NAT/instance), `uses-key` (instance → key pair).
   - `ResourceGraph{version, takenAt, emulator, status: "ok" | "emulator-down", nodes, contains, edges, warnings: list[str]}`.
   - Validator: mỗi `child` có đúng một parent, cây có một gốc `region`, mọi `from/to` trỏ tới node có thật.
2. **Collector** (`collector.py`), mỗi loại một hàm thuần nhận dict output của boto3 để test được không cần Docker:
   - Gọi `describe_vpcs, describe_subnets, describe_internet_gateways, describe_nat_gateways, describe_route_tables, describe_security_groups, describe_key_pairs, describe_instances, describe_addresses` qua `direct_endpoint` (đi thẳng Floci, không tạo sự kiện ở tap).
   - AZ: chỉ tạo node AZ cho các cặp (VPC, AZ) có subnet; id dạng `<vpc-id>/<az>`.
   - Subnet public khi route table gắn với nó (hoặc main route table của VPC nếu không gắn tường minh) có route `0.0.0.0/0` tới `igw-*`.
   - Bỏ NAT ở trạng thái `deleted`, instance ở `terminated`/`shutting-down`; giữ `pending`, `stopped` với `props.state`.
   - **Điểm spike 1:** đặt instance theo `SubnetId`, không theo IP. Nếu `PrivateIpAddress` nằm ngoài CIDR subnet thì thêm vào `warnings` và `props.privateIpOutOfCidr = true`.
   - **Điểm spike 2:** `PublicIpAddress == "127.0.0.1"` thì thay bằng `props.hostPorts` lấy từ `host_ports.py`: `docker ps --filter label=io.floci.resource-id=<id> --format '{{json .Ports}}'`, lọc dải 30000–30999. Docker không có thì bỏ qua, không lỗi.
   - **Điểm spike 3:** khoá instance bằng `InstanceId`; không đưa `ReservationId` vào graph.
   - **Điểm spike 4:** `props.userDataReady` không suy được từ API; thêm `props.note` "UserData có thể còn chạy tới vài phút sau running" khi instance có UserData và `LaunchTime` trong 6 phút gần nhất.
   - `label`: tag `Name` nếu có, nếu không thì id.
   - Sắp xếp `nodes`, `contains`, `edges` theo id trước khi trả về, để JSON xác định.
   - Floci không trả lời (`EndpointConnectionError`, timeout 2 s) thì trả graph `status="emulator-down"` rỗng.
3. **Test:**
   - `test_graph_schema.py`: validator bắt node mồ côi, hai parent, edge treo.
   - `test_collector.py`: dựng graph từ fixture `floci-describe/`; kiểm cấu trúc đầy đủ của Lab 6 + 7; subnet public/private đúng; instance có `privateIpOutOfCidr` khi IP sai; `hostPorts` khi IP là `127.0.0.1` (giả lập `host_ports`); hai lần collect cùng input cho JSON giống hệt từng byte; đảo thứ tự output của boto3 vẫn cho cùng JSON.
   - Test ghi golden: `lab-06-07.graph.json` chỉ được sinh lại khi chạy với `UPDATE_GOLDEN=1`; bình thường so sánh và báo lệch.

## Verification

- `cd server && uv run pytest tests/test_graph_schema.py tests/test_collector.py`
- Mở `lab-06-07.graph.json` và đối chiếu bằng mắt với sơ đồ Lab 6 + 7 trong `lab-06-07.sh`.

## Risk & Rollback

Output spike có thể thiếu một vài lệnh `describe-*` cần cho fixture. Khi đó chạy lại `lab-06-07.sh` trên Floci 2.3.0 và lưu output mới vào `fixtures/graph/floci-describe/`. Phase này chỉ thêm module mới nên rollback là xoá `graph/`.
