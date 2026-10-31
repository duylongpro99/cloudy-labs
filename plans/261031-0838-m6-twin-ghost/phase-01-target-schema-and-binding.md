---
phase: 1
title: "Schema target, hàm gắn ghost và target cho fixture"
status: completed
priority: P1
effort: "7h"
dependencies: []
---

# Phase 1: schema `target`, hàm gắn ghost và target cho fixture

## Goal

`lab.yaml` có `target` được validate chặt, và một hàm thuần gắn từng node target vào id thật dựa trên kết quả check và graph.

## Files to Create / Modify

- Modify: `server/src/cloudy_labs/labs/schema.py` — model `TargetNode`, `Target`; `Lab.target: Target = Target()`; validate tham chiếu check trong `Lab._references`.
- Create: `server/src/cloudy_labs/twin.py` — `PARENT_KINDS`, `Binding`, `bind_target(target, results, graph)`.
- Modify: `server/tests/fixtures/labs/fixture-lab-06/lab.yaml` — thêm `target` (VPC, 2 AZ, 2 subnet public, 2 subnet private, IGW, EIP, NAT, 2 route table).
- Modify: `server/tests/fixtures/labs/fixture-lab-06/checks.py` — `nat_in_public_subnet` trả thêm allocation id của EIP khi đạt.
- Modify: `server/tests/fixtures/labs/fixture-lab-07/lab.yaml` — task `network`, check `network-ready`, `target` (VPC, AZ, subnet public, IGW, SG web, key pair, instance).
- Modify: `server/tests/fixtures/labs/fixture-lab-07/checks.py` — `network_ready` trả id VPC, subnet public, IGW.
- Create: `server/tests/test_twin_binding.py`.
- Modify: `server/tests/test_schema.py` — case `target` hợp lệ và không hợp lệ.

## Tasks & Steps

1. `TargetNode(_Strict)`: `id` (slug), `kind` (`graph.schema.Kind` trừ `region`), `label`, `parent: str | None`, `checks: list[str] = []`. `Target(_Strict)`: `nodes: list[TargetNode] = []`.
2. `PARENT_KINDS` trong `twin.py` (và dùng lại ở schema): `vpc`, `igw`, `key-pair`, `elastic-ip` ← `region`; `az`, `route-table`, `security-group` ← `vpc`; `subnet-*` ← `az`; `nat`, `instance` ← `subnet-*`. Lấy đúng từ `collector.py`; IGW chưa gắn nằm ở region nhưng trong target luôn khai báo dưới `vpc`.
   - Kiểm lại: IGW đã gắn có cha là VPC trong graph (`collector.py:142`). Target cho phép `igw` dưới `vpc`.
3. Validate trong `Lab`: id target duy nhất; `parent` tồn tại và đúng `PARENT_KINDS`; không vòng; `checks` trỏ check có thật; `az` không có check; node khác `az` có ít nhất một check. Lỗi nêu id node.
4. `bind_target` theo đúng thuật toán ở `plan.md` (mục Gắn ghost). Đầu vào `results: list[CheckResult]`, `graph: ResourceGraph`. Trả `Binding(bound: dict[str, str], ghosts: list[GhostNode])`, `GhostNode` có `id, kind, label, parent, checks`, trong đó `parent` là id ghost hoặc id thật đã giải. Deterministic: cùng đầu vào, cùng đầu ra.
5. Viết target cho hai fixture. Chạy `labctl` load lab để chắc schema nhận.
6. Sửa hai checker fixture như trên. Không đổi điều kiện đạt hay trượt của check nào khác.

## Verification

- `cd server && uv run pytest tests/test_twin_binding.py tests/test_schema.py -q`
- Test binding tối thiểu (dùng golden graph lab-06 có sẵn và `CheckResult` dựng tay):
  - không check nào qua → mọi node là ghost, cha giải đúng;
  - mọi check qua → `ghosts` rỗng, `bound` đủ, subnet AZ thứ nhất nằm trong AZ đứng đầu theo chữ cái;
  - check qua nhưng id không có trong graph → ghost giữ nguyên;
  - hai ghost cùng kind cùng check → lấy hai id khác nhau;
  - AZ có con gắn vào hai AZ thật khác nhau → AZ vẫn là ghost.
- `uv run pytest -q` toàn bộ server vẫn xanh (checker fixture đã sửa).
