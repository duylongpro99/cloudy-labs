---
phase: 1
title: "Package Python và schema lab"
status: completed
priority: P1
effort: "3h"
dependencies: []
---

# Phase 1: Package Python và schema lab

## Goal

Tạo package `cloudy-labs` trong `server/`, có entry point `labctl`, schema lab bằng pydantic và bộ nạp lab, cùng một lab fixture cho test.

## Files to Create / Modify

- Create: `server/pyproject.toml`, `server/uv.lock`, `server/.python-version` (3.12)
- Create: `server/src/cloudy_labs/__init__.py`, `config.py`, `cli.py` (khung argparse, các lệnh con chưa làm thì báo "chưa có")
- Create: `server/src/cloudy_labs/labs/__init__.py`, `schema.py`, `loader.py`
- Create: `server/src/cloudy_labs/checks.py` (`CheckResult`, `CheckContext`, `run_checks`)
- Create: `server/tests/fixtures/labs/fixture-vpc/lab.yaml`, `checks.py`
- Create: `server/tests/test_schema.py`, `test_loader.py`, `test_checks.py`
- Create: `labs/.gitkeep`
- Modify: `.gitignore` ở gốc repo: thêm `server/.venv/`, `__pycache__/`, `.pytest_cache/`

## Tasks & Steps

1. `uv init --package` trong `server/`, tên `cloudy-labs`, `requires-python = ">=3.12"`. Phụ thuộc: `boto3`, `pyyaml`, `pydantic` (đều Apache-2.0/MIT). Dev: `pytest`. Entry point `labctl = "cloudy_labs.cli:main"`. Đăng ký marker pytest `docker`, mặc định bỏ qua (`-m "not docker"`).
2. `config.py`: `home()` lấy từ `CLOUDY_LABS_HOME`, mặc định `~/.cloudy-labs`; `labs_dir()` lấy từ `CLOUDY_LABS_LABS_DIR`, mặc định `<repo>/labs`; hằng số cổng `FLOCI_PORT = 4566`, `MOTO_PORT = 5050`, region `us-east-1`, credential giả `test`/`test`.
3. `labs/schema.py`, pydantic v2, `extra="forbid"`:
   - `Lab`: `id` (slug), `provider` (`"aws"`), `emulator` (`"floci" | "moto"`, mặc định `floci`), `title`, `cidrs: list[IPv4Network] = []` (dùng cho preflight), `setup: list[str]` (tham chiếu `module:function`), `tasks: list[Task]`, `checks: list[Check]`, `hints: list[Hint] = []`, `target: dict = {}` (để M6 định nghĩa sau).
   - `Task(id, text)`, `Check(id, task, fn, args: dict = {}, description)`, `Hint(task, text)`.
   - Validator: id của task và check không trùng; `check.task` và `hint.task` trỏ tới task có thật; `fn` có dạng `module:function`.
4. `labs/loader.py`: `load_lab(lab_id)` đọc `labs_dir()/<id>/lab.yaml`, kiểm schema, nạp module checker bằng `importlib.util.spec_from_file_location` từ đúng thư mục lab (không thêm vào `sys.path`), trả về `LoadedLab` có `lab` và `resolve(fn) -> callable`. `list_labs()` liệt kê thư mục có `lab.yaml`. Lỗi YAML/schema/tham chiếu thành `LabError` có tên file và đường dẫn trường.
5. `checks.py`: `CheckResult(check_id, passed, message, resource_ids)`; `CheckContext(client)` bọc `provider.client`; `run_checks(loaded, ctx)` gọi từng check với `(ctx, **args)`. Checker ném exception thì thành kết quả trượt với thông điệp lỗi, không làm dừng các check khác. Checker trả về kiểu khác `CheckResult` cũng là trượt.
6. Lab fixture `fixture-vpc`: một task "tạo VPC `10.77.0.0/16` có tag `lab=fixture-vpc`", một check `vpc_exists` dùng `ec2.describe_vpcs` lọc theo tag, trả về `VpcId` trong `resource_ids`. Đây là fixture test, không phải nội dung lab.
7. Test đơn vị: schema hợp lệ/không hợp lệ (trùng id, tham chiếu task sai, `fn` sai dạng, trường lạ); loader nạp fixture và báo lỗi rõ khi thiếu hàm; `run_checks` với checker giả trong `tmp_path` cho các nhánh pass, fail, exception, sai kiểu trả về.

## Verification

- `cd server && uv run pytest` qua hết.
- `cd server && uv run labctl --help` liệt kê đủ `up down env start check reset status`.
