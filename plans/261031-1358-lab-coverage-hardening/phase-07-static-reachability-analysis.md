---
phase: 7
title: "Phân tích reachability tĩnh"
status: completed
priority: P1
effort: "34h"
dependencies: [1, 2, 8]
---

# Phase 7: phân tích reachability tĩnh

## Goal

Cho một cặp nguồn–đích, cùng cổng và giao thức, hệ thống trả lời ba câu: gói tin có tới được không, đi qua những hop nào, và bị chặn ở đâu. Câu trả lời được tính từ cấu hình thật trong emulator. Check được dùng kết quả này để chấm sau khi bảng tình huống chuẩn và một lần đầu-cuối trên Floci đều đạt. Web vẽ được đường đi.

## Bối cảnh

- 73 lab mạng và replication chỉ có control plane trên Floci. Route table, NACL, NAT, peering và TGW được lưu nhưng không tác động lên traffic. SG chỉ chặn được trên Linux khi bật cờ, trong khi máy người dùng là macOS (báo cáo nghiên cứu, Part B).
- Người dùng chọn tự mô phỏng reachability, và cho dùng nó để chấm sau khi bảng chuẩn và lần đầu-cuối đạt (2026-10-31).
- **[Red team] Phụ thuộc Phase 8.** Phase 8 thêm kind NACL, peering, TGW và endpoint, cùng các props reachability: SG egress, route đầy đủ với target và trạng thái, association gồm cả main route table. Phase 7 chỉ bắt đầu sau Phase 8.
- **Đổi PRD §5.** Câu "Giả lập lưu lượng mạng hay data plane của VPC" sửa thành: "Giả lập traffic thật. Nền tảng chỉ phân tích reachability tĩnh từ cấu hình, giống VPC Reachability Analyzer, và luôn ghi rõ là kết quả phân tích." Nguyên tắc 3 (không dữ liệu giả) giữ nguyên: không có hoạt ảnh gói tin chạy.

## Thiết kế

- Module thuần `server/src/cloudy_labs/reachability/`. Đầu vào là `ResourceGraph` có đủ props reachability; module không gọi emulator.
- **[Red team] Graph riêng, đầy đủ.** `reachable()` không dùng graph đang hiển thị, vì collector theo lab có thể đã thu hẹp tập kind. Nó gọi collector với tập kind mạng đầy đủ, giới hạn ở các VPC liên quan tới nguồn, đích, peering và TGW. `CheckContext` (`checks.py:23`, hiện chỉ có client) được thêm hàm `collect(kinds, vpc_ids)`; `engine.py:88` truyền hàm đó vào.
- **Nguồn và đích:** instance, ENI, Lambda trong VPC, RDS, endpoint ELB, `internet` (`0.0.0.0/0`), một IP hoặc CIDR, hoặc VPC endpoint của một service (S3, DynamoDB).
- **Mô hình** theo tài liệu AWS. Mỗi luật có test trích nguồn tài liệu AWS.
  1. **SG:** stateful.
     - Outbound của SG nguồn phải cho phép, và inbound của SG đích phải cho phép.
     - Rule có thể tham chiếu SG khác hoặc prefix list.
     - Chiều về luôn được phép.
  2. **NACL:** stateless.
     - Xét subnet nguồn (outbound) và subnet đích (inbound) theo thứ tự rule number tăng dần. Rule đầu tiên khớp quyết định.
     - Chiều về phải được phép trên cổng ephemeral (1024–65535).
  3. **Route table** của subnet: lấy association, nếu không có thì dùng main route table. Chọn route theo longest prefix match.
     - `local` → trong VPC.
     - `igw-` → Internet; nguồn cần IP public hoặc EIP.
     - `nat-` → NAT trong subnet public, rồi tiếp tục theo route của subnet NAT.
     - `pcx-` → VPC peer; không bắc cầu.
     - `tgw-` → route table của TGW attachment.
     - `vpce-` (gateway endpoint) → S3 hoặc DynamoDB.
     - Route ở trạng thái `blackhole` → chặn.
  4. **Chiều Internet vào:** đích cần IP public hoặc EIP, và subnet có route `0.0.0.0/0` tới IGW; sau đó xét NACL rồi SG.
  5. **[Red team] Giới hạn vòng lặp.** Phân tích giữ tập đã đi qua theo `(resource_id, chiều)` và giới hạn 32 hop. Khi gặp lại một bước đã đi qua hoặc vượt giới hạn, kết quả là hop `deny` với reason `loop-detected`.
  6. Mỗi bước sinh một hop `{resource_id, kind, verdict: allow|deny|forward, rule, reason}`. Hop `deny` đầu tiên là điểm chặn.
- **Check helper** trong `checks.py`:
  - `ctx.reachable(src, dst, port, proto="tcp") -> Reachability(ok, hops, blocked_at, label="analysed")`;
  - `CheckResult.resource_ids` gồm các hop, để panel check tô sáng đúng đường đi.
- **[Red team] Chấm bằng reachability** được bật bằng một cờ trong `reachability/__init__.py` (`GRADING_ENABLED`). Cờ chỉ chuyển sang `True` sau khi bảng chuẩn xanh và `notes/reachability-e2e.md` ghi lần đầu-cuối đạt. Trước đó `ctx.reachable` vẫn chạy, nhưng check dùng nó trả kết quả `info`, không trả `pass` hay `fail`. Panel luôn hiện nhãn "đã phân tích".
- **API và web:**
  - `POST /api/reachability {src, dst, port, proto}`.
  - **[Red team]** Endpoint đi qua `guard_request` như các POST khác. Input được validate: `src` và `dst` là node id có trong graph, hoặc IP/CIDR hợp lệ theo `ipaddress.ip_network`; `port` trong khoảng 0–65535; `proto` thuộc `tcp|udp|icmp|-1`. Phân tích chạy trong `asyncio.to_thread`.
  - Web có chế độ "Phân tích đường đi": chọn hai node, nhập cổng, rồi xem kết quả. Các hop được nối bằng một đường tĩnh đánh số; hop chặn có màu đỏ và hiện rule gây chặn.
  - Luôn có nhãn "Phân tích cấu hình, không phải traffic thật".
- Ngoài phạm vi: DNS, ELB health check, SG enforcement thật trên Linux, rule của Network Firewall (chỉ hiển thị là có tồn tại).

## Files to Create / Modify

- Create: `server/src/cloudy_labs/reachability/__init__.py`, `model.py` (hop, kết quả), `sg.py`, `nacl.py`, `routes.py`, `analyze.py`.
- Modify: `server/src/cloudy_labs/checks.py` (`CheckContext.collect`, `reachable`), `engine.py`, `server/app.py` (endpoint).
- Create: `server/tests/test_reachability.py`, kèm bảng tình huống chuẩn trong `server/tests/fixtures/reachability/*.yaml`.
- Create: `server/tests/fixtures/reachability/floci/`, chứa output Floci đã ghi lại bằng script của Phase 3.
- Create: `web/src/reachability/reachability-panel.tsx`, `reachability-layer.tsx`, kèm test.
- Modify: `docs/product-requirements.md` (§5, thêm F6.5 reachability), `docs/emulator-differences.md`, `docs/labctl.md`.

## Tasks & Steps

1. Viết bảng tình huống chuẩn trước, theo kiểu TDD.
   - Mỗi tình huống gồm một truy vấn, kết quả mong đợi và link tài liệu AWS.
   - **[Red team]** Graph của tình huống được sinh bằng cách chạy collector trên output Floci đã ghi lại, không viết tay.
   - Tình huống tối thiểu:
     - instance public vào và ra Internet, đủ và thiếu từng điều kiện;
     - instance private ra Internet qua NAT;
     - NACL chặn cổng ephemeral ở chiều về;
     - thứ tự rule NACL (deny số nhỏ thắng allow số lớn);
     - SG tham chiếu SG;
     - SG egress chặn;
     - subnet không có association, dùng main route table;
     - peering không bắc cầu;
     - TGW với hai route table;
     - gateway endpoint S3;
     - route blackhole;
     - RDS private chỉ nhận từ SG của app;
     - **[Red team]** vòng lặp TGW ↔ peering, và vòng lặp route qua NAT.
2. Cài từng module cho tới khi bảng xanh.
3. `CheckContext.collect`, check helper, endpoint (guard và validate input), panel và lớp vẽ trên web.
4. Chạy một tình huống đầu-cuối trên Floci thật: dựng bằng CLI, rồi `reachable` trả đúng. Ghi vào `notes/reachability-e2e.md`, rồi bật `GRADING_ENABLED`.
5. Sửa PRD và docs.

## Verification

- `cd server && uv run pytest tests/test_reachability.py -q`
- Test endpoint: thiếu header guard bị từ chối; `src` lạ, `port` 70000 và CIDR sai đều trả 422.
- `cd web && npm test && npm run typecheck`
- Đầu-cuối trên Floci: `notes/reachability-e2e.md` ghi lệnh dựng, truy vấn và kết quả.

## Risk / Rollback

- Mô hình sai sẽ làm check chấm sai, vi phạm nguyên tắc "chấm bài đáng tin". Giảm thiểu:
  - chỉ chấm sau khi bảng chuẩn và lần đầu-cuối đạt;
  - mọi luật có nguồn tài liệu AWS;
  - fixture lấy từ output Floci thật.
- Rollback: tắt `GRADING_ENABLED`, khi đó check reachability trở về `info`.

## Lệch so với thiết kế

- Props `hasPublicIp` và props TGW được thêm ở phase này, nên golden lab-06-07 và wave-1 đổi (ngoài Phase 3 và 8).
- Floci làm mất target của route tới TGW. Fixture đặt target trở lại bằng `fixtures/reachability/patches.yaml`; trên Floci thật, analyzer báo `route-target-unknown` thay vì đoán.
- Không có `collect(kinds, vpc_ids)`: graph mạng được thu đủ cho cả region, không thu hẹp theo VPC.
- Chưa có endpoint ELB. Chiều về chỉ được kiểm cho peering, TGW và Internet. NACL của subnet gắn TGW chưa được mô hình. NACL của subnet NAT chỉ được xét ở chiều ra.
- Rule NACL được xét theo kiểu tồn tại (có một cổng hoặc dải nào khớp). Địa chỉ của RDS và Lambda được lấy gần đúng bằng CIDR của subnet.
- `progress.db` có thêm cột `info`. Migration tự sao lưu DB thành `progress.db.v<n>.bak`.
- Thêm module `web/src/reachability/reachability-api.ts` cho kiểu dữ liệu và lời gọi API.
- `GRADING_ENABLED = True` sau [notes/reachability-e2e.md](notes/reachability-e2e.md).
