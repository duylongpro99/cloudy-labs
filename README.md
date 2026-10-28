# Cloudy Labs

Hands-on labs cho AWS chạy trên emulator cục bộ: không tốn tiền, không sợ để quên tài nguyên, và có chấm bài tự động. Về sau sẽ có thêm sơ đồ kiến trúc 3D dựng từ trạng thái thật của emulator. Bối cảnh và phạm vi xem ở [PRD](docs/product-requirements.md) và [roadmap](docs/roadmap.md).

**Trạng thái (2026-10-28).** Đã có engine lab và CLI `labctl` (M1) cùng thư viện khối 3D từ AWS Architecture Icons (một phần M2). Repo **chưa có bài lab nào**; thư mục `labs/` đang trống, nội dung lab sẽ bổ sung sau. Engine hiện được kiểm bằng lab fixture trong `server/tests/fixtures/labs/`.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `server/` | Package Python `cloudy_labs`: CLI `labctl`, engine chạy lab và checker, stack emulator (Floci cho AWS, moto cho dịch vụ Floci chưa hỗ trợ). |
| `web/` | Ứng dụng React + three.js hiển thị cảnh kiến trúc 3D và bộ sưu tập khối AWS. |
| `labs/` | Nơi đặt các bài lab (mỗi lab một thư mục có `lab.yaml` và `checks.py`). |
| `scripts/` | Script nhập icon AWS vào `web/`. |
| `docs/` | Tài liệu sản phẩm và hướng dẫn chi tiết. |
| `plans/` | Kế hoạch, báo cáo và nhật ký làm việc. |

## Yêu cầu

- Docker Desktop (hoặc Docker Engine có `docker compose`) đang chạy.
- [uv](https://docs.astral.sh/uv/) cho phần `server/`; uv tự cài Python 3.12 nếu máy chưa có.
- AWS CLI v2 để làm lab.
- Node.js và pnpm cho phần `web/`.
- Cổng `127.0.0.1:4566` (Floci) và `127.0.0.1:5050` (moto) còn trống.

## Làm lab với `labctl`

```bash
cd server
uv sync
uv run labctl up                       # dựng Floci + moto; lần đầu build thêm image Amazon Linux 2023 (1–2 phút, cần mạng)
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
cd web
pnpm install
pnpm dev                               # http://localhost:5174
```

Mở `http://localhost:5174/?view=gallery` để xem bộ sưu tập khối AWS; thêm `&theme=dark` cho chủ đề tối. Icon đã chọn nằm sẵn trong `web/src/scene/aws-objects/icons/`. Chỉ khi cần nhập lại icon mới phải tải gói AWS Architecture Icons vào `aws-icon-pkg/` (không commit) rồi chạy `pnpm import-icons`.

## Test

```bash
cd server
uv run pytest             # test đơn vị, không cần Docker
uv run pytest -m docker   # vòng đời đầy đủ trên stack thật, kèm kiểm catalog AMI khớp bản Floci đang ghim
uv run ruff check src tests

cd ../web
pnpm typecheck && pnpm test
```

## Bảo trì emulator

Đổi phiên bản Floci hoặc cập nhật image Amazon Linux 2023 dùng cho instance EC2 đều có lệnh riêng (`python -m cloudy_labs.emulator.images sync-catalog` và `bump-base`); xem mục "Bảo trì image Amazon Linux 2023 và catalog AMI" trong [docs/labctl.md](docs/labctl.md).
