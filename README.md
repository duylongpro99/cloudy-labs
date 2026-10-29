# Cloudy Labs

Hands-on labs cho AWS chạy trên emulator cục bộ: không tốn tiền, không sợ để quên tài nguyên, có chấm bài tự động, và có sơ đồ kiến trúc 3D dựng từ trạng thái thật của emulator. Bối cảnh và phạm vi xem ở [PRD](docs/product-requirements.md) và [roadmap](docs/roadmap.md).

**Trạng thái (2026-10-29).** Đã có engine lab và CLI `labctl` (M1) và cảnh 3D trực tiếp (M2): làm lab bằng AWS CLI thì sơ đồ kiến trúc 3D tự cập nhật từ trạng thái thật của emulator. Repo **chưa có bài lab nào**; thư mục `labs/` đang trống, nội dung lab sẽ bổ sung sau. Engine hiện được kiểm bằng lab fixture trong `server/tests/fixtures/labs/`.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `server/` | Package Python `cloudy_labs`: CLI `labctl`, engine chạy lab và checker, stack emulator (Floci cho AWS, moto cho dịch vụ Floci chưa hỗ trợ, api-tap đứng trước Floci), collector và lab-server cho cảnh 3D. |
| `web/` | Ứng dụng React + three.js hiển thị cảnh kiến trúc 3D trực tiếp và bộ sưu tập khối AWS. |
| `labs/` | Nơi đặt các bài lab (mỗi lab một thư mục có `lab.yaml` và `checks.py`). |
| `scripts/` | Script nhập icon AWS vào `web/`. |
| `docs/` | Tài liệu sản phẩm và hướng dẫn chi tiết. |
| `plans/` | Kế hoạch, báo cáo và nhật ký làm việc. |

## Yêu cầu

- Docker Desktop (hoặc Docker Engine có `docker compose`) đang chạy.
- [uv](https://docs.astral.sh/uv/) cho phần `server/`; uv tự cài Python 3.12 nếu máy chưa có.
- AWS CLI v2 để làm lab.
- Node.js và pnpm cho phần `web/`.
- Các cổng `127.0.0.1` 4566–4568, 5050, 5174 và 8730 còn trống ([bảng cổng](docs/labctl.md#cổng)).

## Làm lab với `labctl`

```bash
cd server
uv sync
uv run labctl up                       # dựng api-tap + Floci + moto; lần đầu build thêm image Amazon Linux 2023 (1–2 phút, cần mạng)
uv run labctl start <lab>              # reset emulator, mở lần làm mới, in danh sách task
eval "$(uv run labctl env <lab>)"      # trỏ AWS CLI trong shell này vào emulator của lab
aws ec2 describe-vpcs                  # làm bài bằng AWS CLI như trên AWS thật
uv run labctl check <lab>              # chấm bài; mã thoát 0 là đạt hết
uv run labctl reset <lab>              # làm lại từ đầu
uv run labctl status                   # health emulator, lab đang làm, tiến độ
uv run labctl down                     # tắt stack và dọn mọi container, network Floci để lại
```

Chi tiết từng lệnh, biến môi trường và cách viết một lab: [docs/labctl.md](docs/labctl.md). Những chỗ emulator khác AWS thật mà người viết lab cần biết: [docs/emulator-differences.md](docs/emulator-differences.md).

## Xem cảnh 3D

```bash
cd server && uv run labctl up && uv run labctl serve   # terminal 1: emulator + lab-server (127.0.0.1:8730), giữ chạy
cd web && pnpm install && pnpm dev                      # terminal 2: http://127.0.0.1:5174/
```

Mở `http://127.0.0.1:5174/` rồi làm lab bằng AWS CLI ở terminal khác: tài nguyên mới hiện trong cảnh sau dưới 1 giây, lệnh ghi "bay" tới tài nguyên nó tạo, bấm một khối để xem thuộc tính. Chủ đề mặc định theo hệ thống, nút "Chủ đề" chuyển tay. Chi tiết: [docs/labctl.md](docs/labctl.md#cảnh-3d-trực-tiếp).

Các trang khác: `?view=gallery` là bộ sưu tập khối AWS (thêm `&theme=dark` cho chủ đề tối), `?view=bench` là cảnh 200 node dùng để đo hiệu năng. Icon đã chọn nằm sẵn trong `web/src/scene/aws-objects/icons/`. Chỉ khi cần nhập lại icon mới phải tải gói AWS Architecture Icons vào `aws-icon-pkg/` (không commit) rồi chạy `pnpm import-icons`.

## Test

```bash
cd server
uv run pytest             # test đơn vị, không cần Docker
uv run pytest -m docker   # vòng đời đầy đủ trên stack thật, kèm kiểm catalog AMI khớp bản Floci đang ghim
uv run ruff check src tests

cd ../web
pnpm typecheck && pnpm test
# cần `pnpm dev` đang chạy, Google Chrome:
node scripts/check-live.mjs   # hành vi cảnh trực tiếp với WebSocket giả (không cần lab-server)
node scripts/check-scene.mjs  # bộ sưu tập và tương tác trên cảnh bench
pnpm bench:chrome             # đo khung hình cảnh 200 node; tóm tắt bằng scripts/summarize-bench.mjs
```

## Bảo trì emulator

Đổi phiên bản Floci hoặc cập nhật image Amazon Linux 2023 dùng cho instance EC2 đều có lệnh riêng (`python -m cloudy_labs.emulator.images sync-catalog` và `bump-base`); xem mục "Bảo trì image Amazon Linux 2023 và catalog AMI" trong [docs/labctl.md](docs/labctl.md).
