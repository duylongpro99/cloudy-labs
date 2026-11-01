---
phase: 6
title: "Công cụ coverage và contract test"
status: completed
priority: P1
effort: "32h"
dependencies: [5]
---

# Phase 6: công cụ coverage và contract test

## Goal

Một lệnh trả lời "lab này chạy được trên nền tảng chưa, và thiếu gì", cho một lab cụ thể hoặc cho cả danh mục. Câu trả lời dựa trên kết quả test thật và danh sách thiếu ở mức op, không chỉ dựa vào khai báo.

## Thiết kế

### 1. Ma trận hỗ trợ (sinh tự động)

- **Contract test** cho mỗi `ResourceType` có op `create`, chạy trên Floci thật. File là `test_registry_contract_docker.py` (marker `docker`), tham số hoá theo registry. Mỗi ca gồm:
  1. Tạo cha cần thiết theo `fixture` khai báo trong registry, ví dụ VPC và 2 subnet cho DB subnet group.
  2. Chạy lệnh `create` do builder sinh, với `defaults`.
  3. Graph có node đúng kind, đúng cha và đúng cạnh. **[Red team]** Đo độ trễ từ lúc lệnh trả về tới lúc node xuất hiện, và ghi số đo; ngưỡng mặc định là 2 giây, kind chạy container (RDS, ECS...) có ngưỡng riêng.
  4. Op `modify` (nếu có) chạy được và props đổi.
  5. Op `delete` chạy được và node biến mất.
- **[Red team]** Kết quả ghi vào `server/src/cloudy_labs/registry/contract-results.json` và được commit. Mỗi mục gồm kind, op, kết quả và độ trễ. File có một `floci_image_digest` và ngày chạy. Khi digest không khớp image đang ghim trong `compose.yaml`, `coverage` in cảnh báo; `coverage --strict` báo lỗi.
- `labctl coverage --matrix` sinh `docs/coverage.md` từ registry và `contract-results.json`. Bảng có:
  - service, kind;
  - trạng thái Floci (`supported`, `control-plane-only`, `missing`);
  - graph, 3D (icon riêng hay dự phòng);
  - builder (các op), contract test (đạt, trượt, chưa chạy) và độ trễ;
  - caveat (từ `caveats` của registry).

  Có test kiểm `docs/coverage.md` khớp với lần sinh mới nhất.
- Danh sách API Floci hỗ trợ được sinh từ docs Floci tại tag đang ghim, lưu ở `registry/floci-ops-<version>.json` kèm script tạo lại. Danh sách này dùng để báo một API lab gọi có hay không, kể cả API không thuộc kind nào trong registry.
- **[Red team] `registry/catalog-overrides.yaml`:** danh sách thiếu ở mức op mà cột `floci_missing` của CSV không bắt được, vì CSV chỉ ghi namespace.
  - Mỗi mục có `api`, `reason`, và `match` (từ khoá tìm trong `toc` hoặc `title` của CSV).
  - Mục khởi đầu: EBS `CreateSnapshot`/`CopySnapshot`, CodeCommit, `CreateDhcpOptions`, `CreateEgressOnlyInternetGateway`, `CreatePlacementGroup`, engine RDS Oracle.
  - Mỗi mục được đối chiếu tay với mục lục của các lab khớp; kết quả đối chiếu ghi trong `notes/catalog-overrides-review.md`, chỉ ghi slug và lý do.

### 2. `labctl coverage <lab>` (một lab)

Đầu vào: `labs/<slug>/` với `lab.yaml`, và tuỳ chọn `content/lab.md`. Các bước:

1. **Trích yêu cầu** từ nội dung lab:
   - lệnh `aws <service> <op>` trong mọi khối code, nhất là script dọn dẹp (297/530 lab có);
   - tên tài nguyên AWS trong các bước Console, khớp bằng từ điển sinh từ `label` của registry và tên resource type trong botocore (ví dụ "DB Subnet Group", "Target Group");
   - service ở metadata (`focus_services_field`).
2. **Trích từ `lab.yaml`:** kind trong palette và target, cùng service mà checker gọi (đọc tĩnh `client("...")` trong `checks.py`).
3. **Đối chiếu** từng yêu cầu với:
   - Floci (`floci-ops`, `floci.status`, `catalog-overrides.yaml`);
   - registry (có kind không);
   - contract test (đạt không, digest khớp không);
   - builder (có op không);
   - reachability (lab có route, SG, NACL hay peering thì đánh dấu `reachability-analysed`).
4. **[Red team] Kết luận**, đúng bốn loại như AC1:
   - `blocked`: có service hoặc API Floci thiếu;
   - `ready-with-caveats`: chỉ còn caveat lấy từ `caveats` của registry (`control-plane-only`, `flag-only`, `reachability-analysed`...);
   - `gap`: lỗ hổng của nền tảng (kind chưa có, contract trượt). Coverage in ra việc cần làm;
   - `ready`: không còn gì.
5. **[Red team] Kết luận nháp và danh sách chưa nhận diện.**
   - Tên tài nguyên không chắc chắn không làm kết luận thành `gap`. Chúng được liệt kê riêng, mỗi mục ghi heading và số dòng trong `lab.md`, **không trích văn bản**.
   - Kết luận in ra là "nháp" cho đến khi người dùng xem danh sách đó một lượt và chạy `coverage <lab> --accept`. Lệnh này ghi `labs/<slug>/coverage-review.json`, chỉ chứa số dòng và quyết định.
   - `--quote` (mặc định tắt) in đoạn trích ra terminal để tiện xem, nhưng không ghi vào file nào.
6. Đầu ra dạng bảng cho người, và `--json` cho máy. JSON cũng không chứa đoạn trích.

### 3. `labctl coverage --catalog <csv>` (cả danh mục)

- Chạy bước 3–4 trên metadata công khai trong CSV (`api_namespaces`, `services_mentioned`, `focus_services_field`, `toc`), cộng `catalog-overrides.yaml`.
- In tổng theo kết luận và theo service, cùng danh sách lab `gap` kèm lý do.
- Ghi rõ trong đầu ra: độ tin cậy bị giới hạn bởi metadata công khai.
- Đây là thước đo nghiệm thu của Phase 8–10: sau Phase 10, số lab `gap` phải bằng 0.

### 4. [Red team] Bài đo độ chính xác

- Người dùng dán cục bộ 5 lab trải nhiều service. Chạy `coverage <lab>` rồi so với đánh giá tay.
- Ghi precision và recall theo lớp vào `notes/coverage-precision.md`. Chỉ ghi slug, con số và loại sai; không ghi nội dung.

### 5. Collector theo lab

- **[Red team] Tập kind thu là tập đóng**, gồm:
  - kind trong palette;
  - kind trong target;
  - kind mà reachability cần khi lab có kind mạng (Phase 7);
  - kind đã thấy gần đây, được hub lưu qua các lần refresh.
- Kind mới xuất hiện qua sự kiện api-tap được thêm vào tập đó, không làm mất kind đã có.
- Đo thời gian một lần refresh với toàn bộ registry và với một lab điển hình; ghi vào `notes/perf-results.md`.

## Files to Create / Modify

- Create: `server/src/cloudy_labs/coverage/__init__.py`, `coverage/extract.py` (trích lệnh và tên tài nguyên), `coverage/evaluate.py` (đối chiếu và kết luận), `coverage/matrix.py` (sinh `docs/coverage.md`).
- Create: `server/src/cloudy_labs/registry/contract-results.json`, `registry/floci-ops-2.3.0.json`, `registry/catalog-overrides.yaml`, `server/scripts/floci-ops-from-docs.py`.
- Modify: `server/src/cloudy_labs/cli.py` (`coverage`), `graph/collector.py` (thu theo lab), `server/hub.py` (lưu kind đã thấy).
- Create: `server/tests/test_registry_contract_docker.py`, `server/tests/test_coverage.py` (markdown mẫu tự viết; CSV thu nhỏ), `docs/coverage.md` (sinh ra).
- Modify: `docs/labctl.md`.

## Tasks & Steps

1. Script lấy danh sách API Floci; lưu JSON.
2. Contract test tham số hoá, có đo độ trễ và đóng dấu digest. Chạy cho các kind hiện có; ghi kết quả.
3. `extract.py`:
   - parse lệnh `aws`, kể cả lệnh nhiều dòng với `\` và biến shell;
   - từ điển tên tài nguyên;
   - đầu ra chỉ có heading và số dòng.

   Test trên markdown mẫu tự viết. Mọi thay đổi sau này của `extract.py` phải kèm test fixture.
4. `evaluate.py` với bốn kết luận và caveat lấy từ registry; test từng nhánh. Test cảnh báo khi digest lệch.
5. `catalog-overrides.yaml` và bản đối chiếu tay.
6. `matrix.py` và test "docs khớp".
7. `--catalog` trên CSV thật; ghi kết quả đầu tiên (trước Phase 8) vào `notes/coverage-baseline.md` làm mốc so sánh.
8. Bài đo độ chính xác trên 5 lab dán cục bộ.
9. Collector theo lab với tập kind đóng và số đo.

## Verification

- `cd server && uv run pytest tests/test_coverage.py -q`
- `uv run pytest -m docker tests/test_registry_contract_docker.py -q`
- `uv run labctl coverage --catalog ../plans/reports/researcher-261031-1358-labaws-catalog-and-floci-coverage.csv` in tổng 530 lab theo bốn kết luận. Lab khớp `catalog-overrides.yaml` ra `blocked`.
- Chạy `uv run labctl coverage --matrix` hai lần; lần thứ hai không làm đổi `docs/coverage.md`.
- `grep -c` trên `coverage-review.json` và `notes/*.md` không thấy câu nào của lab dán vào. Kiểm bằng `check-content-leak.py` (Phase 4).

## Risk / Rollback

- Trích tên tài nguyên từ văn bản Console có thể nhận nhầm. Tên không chắc chắn được liệt kê để người dùng xem lại, và không bao giờ được tính là `ready`.
- Metadata công khai có thể bỏ sót API. Bù bằng `catalog-overrides.yaml` và bài đo độ chính xác.
