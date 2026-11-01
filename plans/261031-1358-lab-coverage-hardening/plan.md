---
title: "Tăng cường nền tảng để phủ lab tuỳ ý của labaws.site"
description: "Chuyển mọi chỗ khai báo cứng loại tài nguyên sang một registry khai báo; builder sinh từ botocore; region theo lab; hiển thị lý thuyết lab cục bộ; phân tích reachability tĩnh; và lệnh labctl coverage trả lời 'lab này chạy được chưa' mà không cần hỏi lại."
status: in-progress
priority: P1
effort: 358h
branch: master
tags: [feature, backend, frontend, architecture, coverage, m7]
blockedBy: [261031-0838-m6-twin-ghost]
blocks: []
created: 2026-10-31
---

# Tăng cường nền tảng để phủ lab tuỳ ý của labaws.site

## Overview

Người dùng muốn nền tảng phủ đủ trước khi làm lab thật. Lý do: không phải hỏi lại "project đã cover lab này chưa" mỗi lần làm một lab. Plan này thay mốc M7 trong [roadmap](../../docs/roadmap.md). Mục tiêu cũ của M7 là thêm lab theo danh sách tạm. Mục tiêu mới là phủ theo danh mục thật của labaws.site.

Bằng chứng đã có:

- [Danh mục labaws.site và độ phủ Floci 2.3.0](../reports/researcher-261031-1358-labaws-catalog-and-floci-coverage.md), kèm [CSV 530 lab](../reports/researcher-261031-1358-labaws-catalog-and-floci-coverage.csv).
  - 530 lab, khoảng 40 dịch vụ. Tất cả dùng ap-southeast-2, 510 lab làm trên Console.
  - Theo CSV, 34 lab bị chặn vì Floci chưa có FSx, Site-to-Site VPN/CGW/VGW, Direct Connect, Storage Gateway, X-Ray, Snow hoặc Amplify. 73 lab chỉ có control plane.
  - Trong các namespace Floci có, vẫn thiếu vài API: EBS `CreateSnapshot`/`CopySnapshot`, `CreateDhcpOptions`, egress-only IGW, `CreatePlacementGroup`, engine RDS Oracle, CodeCommit. CSV không bắt được các API này (nó chỉ ghi namespace), nên Phase 6 bổ sung danh sách thiếu ở mức op.
- Thử trực tiếp RDS trên Floci 2.3.0 (2026-10-31). Subnet group, instance postgres/mysql, cờ `--multi-az`, cluster aurora-postgresql/mysql, snapshot, parameter group và `reboot --force-failover` đều chạy. Mỗi DB là một container thật.
- Scout code (2026-10-31): một loại tài nguyên đang được khai báo ở khoảng 15 chỗ.
  - Python: `Kind`, `TargetKind`, `BuilderKind`, `PARENT_KINDS`, `DESCRIBE`, `build_graph`, `_OPS`, `validate`, `OP_NOTES`, `PROPS`.
  - TypeScript: `AwsKind`, `REQUIRED_KINDS`/`EDGE_KINDS` (`graph/types.ts`), `MANIFEST`, `isGroup`, `KIND_ORDER`, `KIND_LABEL`, `HOST_KINDS`, `ACTION_KINDS`, `FIELD_LABEL`, `createDraft`, `connectOp`.
  - Không có đường dự phòng cho loại lạ: server từ chối, còn `parseGraph` trên web ném lỗi và cảnh ngừng vẽ.
  - Graph chỉ có một root, và root phải là `region` (`graph/schema.py:81-83`). Twin lấy node không cha đầu tiên làm region (`twin.py:55`).
  - Region cố định `us-east-1` (`config.py:13`), xuất hiện trong 42 file nguồn và test.
  - `/api/lab` không trả hint; hint không đến được người học.
  - Collector và profile `lab` luôn nhìn vào Floci, kể cả khi lab chọn moto. Moto bật IAM sau reset và đổi key admin mỗi lần reset.

## Contract

### Outcome

Với bất kỳ lab nào trong danh mục labaws.site:

- `labctl coverage` trả về một trong bốn kết luận: `ready`, `ready-with-caveats`, `gap` hoặc `blocked`.
  - Kèm danh sách lỗ hổng theo từng lớp: emulator, graph, 3D, builder, chat, twin, reachability.
  - Caveat lấy từ registry.
- Sau Phase 10 không còn lab `gap` trong danh mục. Lab nào chưa chạy được thì đều là `blocked` vì Floci thiếu, có lý do cụ thể.

### Quyết định của người dùng (2026-10-31)

1. Lab chạy ở **ap-southeast-2**, theo lab.
2. **Có hiển thị phần lý thuyết** trong app: **mỗi heading H2 một tab**, không có bảng vai trò mục.
3. **Builder sinh từ botocore**: form và lệnh sinh từ service model, cộng override. 16 op hiện có giữ argv viết tay qua override.
4. **Nội dung labaws.site chỉ dùng cá nhân, không commit.** Repo chỉ chứa YAML, checker, target và registry do mình viết. Hint của lab labaws cũng nằm trong `content/`. Nội dung lab không đi vào prompt chat.
5. **Lab dùng dịch vụ hoặc API Floci chưa có thì coverage báo `blocked`** kèm lý do. Không tự viết service giả.
6. **Tự mô phỏng reachability**: phân tích tĩnh từ cấu hình thật. Check được dùng để chấm sau khi bảng tình huống chuẩn và một lần đầu-cuối ghi lại trên Floci đều đạt. Quyết định này đổi PRD §5 (xem Phase 7).
7. **Không quét tài nguyên lạ lúc chạy** (bỏ Resource Explorer). Báo cáo coverage trước lab là nơi phát hiện lỗ hổng. Web chỉ có node dự phòng cho kind nó không biết.
8. **Hỗ trợ nhiều region ngay**. Graph có một root `account`; dưới đó là các `region` của lab và một nhóm `global` cho IAM, CloudFront, Route 53...
9. **Lab replication** (S3 CRR/SRR, RDS read replica cross-region, DynamoDB global table) được chấm theo cấu hình, với caveat `control-plane-only`.

### Constraints

- Emulator vẫn là nguồn sự thật. Reachability là kết quả phân tích cấu hình, ghi rõ là "phân tích". Không có hoạt ảnh traffic giả (PRD nguyên tắc 3).
- Mọi thao tác builder và chat vẫn quy về một lệnh `aws ... --profile lab` hiện ra trước, chỉ chạy khi người học bấm Run.
- Các chốt an toàn hiện có của builder và chat được giữ ở lớp chung, áp cho mọi kind:
  - chặn `file://` và `fileb://`;
  - allowlist ký tự cho tên;
  - allowlist props gửi sang LLM;
  - từ chối ghi đè credential.
- Lab 6/7 fixture và mọi test hiện có vẫn xanh sau từng phase. Golden graph và twin chỉ đổi ở phase nói rõ là đổi: Phase 3 (root `account`, region) và Phase 8 (props reachability).
- Thêm một loại tài nguyên mới cần một mục registry, một SVG trong thư mục icon đã bundle, rồi build lại web. Chỉ viết thêm hook Python khi dữ liệu không diễn tả được, và ghi lý do.
- Nội dung lab tải về (`labs/*/content/`) không bao giờ vào git. Có test kiểm `.gitignore` và một kiểm tra n-gram chống lọt nội dung vào file được track.
- NFR2 giữ nguyên: ≥ 50 fps với 200 node, cả hai chủ đề.

### Non-goals

- Viết service giả cho dịch vụ hoặc API Floci chưa có.
- Giả lập traffic thật hay hoạt ảnh luồng dữ liệu.
- Quét tài nguyên lạ lúc chạy (Resource Explorer).
- Viết YAML, checker và target cho 530 lab. Plan này làm nền; mỗi lab vẫn là một lần soạn riêng, nhưng không còn câu hỏi "đã cover chưa".
- Thay thế AWS Console. Builder chỉ phủ các loại tài nguyên trong registry.
- Commit hay phân phối nội dung labaws.site, hoặc gửi nội dung đó sang provider LLM.

### Acceptance criteria

1. `labctl coverage --catalog <csv>` phân loại đủ 530 lab vào bốn kết luận.
   - Lab `blocked` có lý do là service hoặc API Floci thiếu. Nguồn là cột `floci_missing` và danh sách thiếu ở mức op (`catalog-overrides.yaml`, đối chiếu tay với mục lục).
   - Sau Phase 10, `gap` = 0.
   - Mọi thay đổi `extract.py` hay overrides phải kèm test fixture.
   - Ghi rõ độ tin cậy bị giới hạn bởi metadata công khai.
2. `labctl coverage labs/<slug>` (khi có `content/` cục bộ) trả kết luận nháp theo từng lớp, cộng danh sách đề cập chưa nhận diện được. Mỗi đề cập ghi heading và số dòng, không trích văn bản. Sau một lượt người xem lại danh sách đó, kết luận là cuối cùng.
3. Mọi loại tài nguyên trong registry có contract test chạy trên Floci thật:
   - tạo qua lệnh builder sinh ra;
   - xuất hiện trong graph đúng cha và cạnh, với độ trễ được đo và ghi lại;
   - xoá được.

   `docs/coverage.md` sinh từ `contract-results.json`. File đó được đóng dấu digest image Floci; `coverage` báo lỗi khi digest không khớp image đang ghim.
4. Thêm một kind thử `test-only` (một mục registry, một SVG, build lại web) thì graph, cảnh, builder, chat và twin đều nhận. Mỗi lớp có test tự động, và không sửa file TS hay Python nào khác.
5. `parseGraph` và `parseTwin` trên web không bao giờ ném lỗi vì kind hay edge kind lạ. Kind lạ hoặc thiếu icon hiện thành node dự phòng.
6. Lab đặt `region` (mặc định `ap-southeast-2`) hoặc `regions` thì profile, collector, builder, checker, twin và cache AZ đều dùng đúng region. Graph có root `account`, các region và `global`. Lab chọn `emulator: moto` thì cảnh, builder và profile (ký bằng credential moto hiện hành) đều nhìn vào moto.
7. Panel lab hiển thị lý thuyết (mỗi H2 một tab) và hint từ `content/` cục bộ. Thiếu `content/` thì app vẫn chạy, chỉ hiện task. Không có nội dung labaws trong file được track hay trong prompt chat.
8. `reachable(src, dst, port, proto)` trả đúng trên bộ tình huống chuẩn: SG, NACL có thứ tự rule, route table, IGW, NAT, peering, TGW, VPC endpoint, blackhole và vòng lặp. Fixture sinh từ output Floci đã ghi lại. Web vẽ được đường đi hoặc điểm chặn.
9. Builder chung giữ các chốt an toàn:
   - `file://` và `fileb://` bị từ chối ở mọi lá chuỗi, kể cả trong JSON;
   - chat chỉ nhận `chat_props`;
   - principal nội bộ (admin của moto) không xoá hay sửa được.

   Mỗi chốt có test.
10. Lab-001 RDS (`lab-001-chon-rds-aurora-hay-self-managed-database`) được soạn từ nội dung người dùng dán vào và chạy trọn: builder, chat, twin và check đều đạt. `coverage` báo `ready-with-caveats`, caveat Multi-AZ lấy từ registry.
11. Lab 6/7 fixture chạy lại đầu-cuối vẫn đạt; 50 fps với 200 node vẫn đạt.

## Phases

| # | Phase | Status | Effort |
|---|-------|--------|--------|
| 1 | [Registry loại tài nguyên và collector chung](./phase-01-resource-registry-and-generic-collector.md) | Completed | 38h |
| 2 | [Web đọc registry, node dự phòng](./phase-02-web-registry-driven-scene.md) | Completed | 28h |
| 3 | [Region, root account và emulator theo lab](./phase-03-per-lab-region-and-emulator.md) | Completed | 26h |
| 4 | [Nội dung lab cục bộ: lý thuyết và hint](./phase-04-local-lab-content-and-hints.md) | Completed | 14h |
| 5 | [Builder và chat sinh từ botocore](./phase-05-botocore-generated-builder-and-chat.md) | Completed | 48h |
| 6 | [Công cụ coverage và contract test](./phase-06-coverage-tooling-and-contract-tests.md) | Completed | 32h |
| 7 | [Phân tích reachability tĩnh](./phase-07-static-reachability-analysis.md) | Completed | 34h |
| 8 | [Dịch vụ đợt 1: VPC mở rộng, EBS, RDS/Aurora, S3, Lambda, IAM](./phase-08-service-wave-1.md) | Completed | 40h |
| 9 | [Dịch vụ đợt 2: tần suất trung bình](./phase-09-service-wave-2.md) | Completed | 40h |
| 10 | [Dịch vụ đợt 3: phần còn lại Floci hỗ trợ](./phase-10-service-wave-3.md) | Completed | 50h |
| 11 | [Nghiệm thu với lab-001 RDS và cập nhật tài liệu](./phase-11-lab-001-acceptance-and-docs.md) | In Progress (chờ nội dung lab-001) | 8h |

Thứ tự phụ thuộc. Phase 2, 3, 4 và 5 cùng sửa `server/app.py` và `labs/schema.py`, nên chạy tuần tự, không song song.

- 1 → 2 → 3 → 4 → 5 → 6.
- 8 cần 6.
- 7 cần 1, 2 và 8, vì nó cần kind NACL, peering, TGW, endpoint và props reachability.
- 9 và 10 cần 6. Đây là dữ liệu registry, icon, contract test và hook khi cần. Hook đã được tính vào effort theo từng service.
- 11 cần tất cả.

Effort tính theo từng service:

- khoảng 2 giờ cho service chỉ có một lệnh list;
- khoảng 4–6 giờ cho service cần gọi theo tài nguyên cha, hoặc chạy container thật (ECS, EKS, ElastiCache, Beanstalk).

Đo tốc độ thực tế ở Phase 8; Phase 9–10 điều chỉnh theo số đo đó.

## Kiến trúc đích

```text
registry/*.yaml (một mục mỗi loại tài nguyên)
   │  service, list (+ scope theo cha), enrich, filter, id/label, cha, cạnh, props, chat_props,
   │  caveats, protected, icon, vai trò, ops (+ argv override, expect, server_fields)
   ├─► server: Kind động ─► collector chung (cô lập lỗi theo service) ─► ResourceGraph
   │      root account ─► region(s) ─► VPC...      └─► global ─► IAM, CloudFront...
   ├─► /api/registry (kinds + edgeKinds) ─► web: parser không ném lỗi, manifest, layout, theme, palette
   ├─► builder: botocore shape ─► form + argv + sanitiser ─► validate chung (+ hook) ─► chat catalog
   ├─► twin: TargetKind từ registry, bind theo target.region
   ├─► reachability: graph mạng đầy đủ của các VPC liên quan ─► đường đi / điểm chặn ─► check + lớp vẽ
   └─► labctl coverage: registry × floci-ops × catalog-overrides × contract-results(digest) × nội dung lab
```

## Rủi ro

- **Refactor nền móng làm vỡ M2–M6.** Giảm thiểu:
  - Phase 1 giữ `build_graph` cũ làm oracle cho test đối chiếu, rồi mới xoá.
  - Golden chỉ đổi ở Phase 3 và Phase 8, có ghi chú.
  - Chạy lại e2e Lab 6/7 fixture cuối mỗi phase.
- **Form sinh từ botocore quá dài.** Registry chỉ định `fields` hiện mặc định; phần còn lại nằm sau "Nâng cao".
- **Hiệu năng collector với khoảng 40 dịch vụ.**
  - Collector thu theo một tập kind đóng: palette ∪ target ∪ kind reachability cần ∪ kind vừa thấy.
  - Một service lỗi chỉ bỏ kind của nó và ghi `graph.warnings`.
  - Số đo ghi ở Phase 6.
- **Floci đổi hành vi khi nâng phiên bản.** Contract test có đóng dấu digest; nâng Floci phải chạy lại.
- **Reachability sai so với AWS** làm check chấm sai. Giảm thiểu:
  - Mỗi luật trích tài liệu AWS.
  - Fixture sinh từ output Floci đã ghi lại.
  - Chỉ dùng trong check sau khi bảng chuẩn và đầu-cuối đều đạt.
- **Nội dung labaws lọt vào git hoặc sang LLM.** Giảm thiểu:
  - Hint labaws nằm trong `content/`.
  - Coverage chỉ ghi heading và số dòng.
  - Có kiểm tra n-gram.
  - Prompt chat không chứa nội dung lab.
- **Trích yêu cầu từ văn bản Console nhận nhầm.** Coverage cho kết luận nháp cộng danh sách chưa nhận diện để người xem lại một lượt. Có bài test độ chính xác trên 5 lab dán cục bộ (Phase 6).

## Câu hỏi còn mở

Không còn câu hỏi mở. Ba câu hỏi về region thứ hai, replication và reachability đã được người dùng trả lời (quyết định 6, 8 và 9).

## Red Team Review

### Session — 2026-10-31

**Findings:** 15 sau khi gộp từ 37 (15 accepted, 0 rejected)
**Severity breakdown:** 4 Critical, 8 High, 3 Medium

Báo cáo gốc: `plans/reports/red-team-261031-1421-{assumption-destroyer,scope-critic,failure-mode,security}.md`.

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | Argv "giống từng ký tự" bất khả; xoá `Params` làm vỡ `expectation()`, `validate()`, `suggest.py`, gesture `attribute` | Critical | Accept | Phase 5 |
| 2 | `parseGraph`/`parseTwin` ném lỗi với kind và edge kind lạ | Critical | Accept | Phase 2, AC5 |
| 3 | Moto: profile ghi cứng key `test`, key admin đổi mỗi reset; endpoint đổi upstream của api-tap không dùng được hoặc không an toàn | Critical | Accept | Phase 3, AC6 |
| 4 | Catalog "gap = 0" tự chấm ở mức namespace; lab thiếu op vẫn ra `ready` | Critical | Accept | Phase 6, 8, AC1 |
| 5 | Schema một `list` + 3 hook không diễn tả nổi collector hiện tại và kind theo cha; chưa định nghĩa khi một service lỗi | High | Accept | Phase 1 |
| 6 | Nhiều root (region phụ, `global`) vỡ ràng buộc một root ở schema, twin và web | High | Accept (root `account`) | Phase 3, 8 |
| 7 | Validator chung bỏ mất chốt `file://`, allowlist tên và shorthand | High | Accept | Phase 5, AC9 |
| 8 | Props từ registry đẩy secret (biến môi trường Lambda, Outputs của CFN) sang LLM | High | Accept (`chat_props`) | Phase 1, 5 |
| 9 | Nội dung labaws lọt git qua hint, đoạn trích coverage, `notes/`; slug không validate; endpoint ảnh chưa thiết kế | High | Accept | Phase 4, 6, 11 |
| 10 | Phase 7 phụ thuộc Phase 8; collector thiếu SG egress và route target; collector theo lab làm `reachable()` đạt sai; không giới hạn vòng lặp | High | Accept | Phase 6, 7, 8 |
| 11 | Đổi region bỏ sót khoảng 40 file test; fixture Floci phải ghi lại bằng script; cache AZ | High | Accept | Phase 3 |
| 12 | Principal admin của moto hiện ra và xoá được | High | Accept (`protected`) | Phase 1, 5 |
| 13 | Icon được bundle lúc build; `web/public/icons` không tồn tại | Medium | Accept | Phase 2, 8, AC4 |
| 14 | Mâu thuẫn bộ kết luận và caveat giữa AC và Phase 6; AC4 thiếu test chat/twin; AC3 thiếu số đo độ trễ | Medium | Accept | plan.md, Phase 6 |
| 15 | Effort Phase 8–10 ước thấp; DHCP, egress-only IGW, placement group, Oracle thực ra thiếu trên Floci | Medium | Accept | plan.md, Phase 8–10 |

Câu hỏi phạm vi do red-team nêu đã được người dùng trả lời: bỏ quét Resource Explorer, mỗi H2 một tab, làm nhiều region ngay, reachability được chấm sau bảng chuẩn, và replication chấm theo cấu hình.

### Whole-Plan Consistency Sweep

Danh sách thay đổi đã áp vào mọi file:

- Bỏ Resource Explorer và kind `unknown` phía server.
- Bỏ `content.sections` và `tasks[].section`.
- Bộ bốn kết luận và caveat lấy từ registry.
- Root `account` làm ở Phase 3, không phải ở Phase 8.
- Thứ tự phase là 1 → 2 → 3 → 4 → 5 → 6, và Phase 7 cần Phase 8.
- Icon nằm trong `web/src/scene/aws-objects/icons/`.
- Props reachability nằm ở Phase 8.
- 16 op cũ giữ argv override.
- Effort mới: 358h.

Đã soát các thuật ngữ cũ (`Resource Explorer`, `web/public/icons`, `content.sections`, `giống từng ký tự`, `dependencies: [1, 2]` của Phase 7, `TAP_UPSTREAM` đổi lúc chạy). Mọi lần còn xuất hiện chỉ là ghi chú lịch sử hoặc câu phủ định.

Cũng trong lượt soát này, các đường dẫn sai được sửa:

- fixture lab nằm ở `server/tests/fixtures/labs/`;
- `questions.yaml` nằm ở `server/tests/fixtures/chat/`;
- script icon là `scripts/import-aws-icons.mjs`;
- `aws-object-layer.tsx` nằm trong `scene/aws-objects/`;
- hướng dẫn chat nằm trong `docs/labctl.md`.

`ak plan validate` báo OK.

## Validation Log

### Session 1 — 2026-10-31

Sáu câu hỏi sau red-team đóng vai trò cổng validation. Người dùng chọn phương án đề xuất ở cả sáu.

| Câu hỏi | Trả lời | Ảnh hưởng |
|---|---|---|
| Áp dụng các finding red-team? | Áp dụng cả 15 | Mọi phase |
| Node lạ lúc chạy? | Bỏ quét Resource Explorer | Phase 1, 2; quyết định 7 |
| Giao diện lý thuyết? | Mỗi H2 một tab | Phase 4 |
| Nhiều region? | Làm ngay, root `account` | Phase 3; quyết định 8 |
| Chấm bằng reachability? | Sau bảng chuẩn và đầu-cuối | Phase 7; quyết định 6 |
| Lab replication? | Chấm theo cấu hình, có caveat | Phase 8, 9; quyết định 9 |
