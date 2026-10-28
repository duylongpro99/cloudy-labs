---
phase: 4
title: "Lab engine: start, check, status, tiến độ"
status: completed
priority: P1
effort: "4h"
dependencies: [1, 3]
---

# Phase 4: Lab engine: start, check, status, tiến độ

## Goal

`labctl start | check | status` hoạt động đầu-cuối, và tiến độ học được lưu trong SQLite cục bộ (F1.5).

## Files to Create / Modify

- Create: `server/src/cloudy_labs/engine.py`, `progress.py`
- Create: `server/tests/test_progress.py`, `server/tests/test_engine.py`
- Modify: `server/src/cloudy_labs/cli.py` (lệnh `start`, `check`, `status`)

## Tasks & Steps

1. `progress.py`, `sqlite3` của stdlib, file `home()/progress.db`, tạo thư mục nếu chưa có:
   - Bảng `attempts(id INTEGER PK, lab_id, started_at)`; bảng `check_runs(attempt_id, check_id, passed, message, resource_ids_json, ran_at)`.
   - Hàm: `start_attempt(lab_id)`, `record_checks(attempt_id, results)`, `current_attempt()`, `latest_results(lab_id)`, `lab_summary()` (lab đã đạt hết check hay chưa).
   - Lược đồ có `PRAGMA user_version` để nâng cấp về sau.
2. `engine.py`:
   - `start(lab_id)`: nạp lab → preflight CIDR (`lab.cidrs` so với mạng Docker; trùng thì **in cảnh báo**, nêu rõ Floci sẽ âm thầm đổi IP private sang `10.240.0.0/16`, và tiếp tục) → `provider.reset(lab)` → chạy `setup` (mỗi hàm nhận `CheckContext`) → `start_attempt` → in tiêu đề, danh sách task và lệnh `eval "$(labctl env <lab>)"`.
   - `check(lab_id)`: cần một attempt đang mở cho lab đó (nếu không, báo "chạy `labctl start` trước") → `run_checks` → `record_checks` → in từng check (đạt/trượt, thông điệp, ID tài nguyên) và tổng. Mã thoát 0 khi đạt hết, 1 khi có check trượt.
   - `status()`: health của từng emulator, lab đang làm, kết quả check gần nhất, danh sách lab có sẵn.
   - Kiểm stack đang chạy trước `start`/`check`; nếu chưa thì báo "chạy `labctl up` trước".
3. `reset(lab_id)`: `provider.reset(lab)` rồi chạy lại `setup` và mở attempt mới; lệnh `labctl reset` chuyển sang gọi hàm này.
4. CLI dùng `--json` cho `check` và `status` để M2 và test đọc được; mặc định in dạng chữ.
5. Test đơn vị: `progress` trên `tmp_path` (tạo bảng, ghi, đọc lại, nâng `user_version`); `engine.check` với một lab tạm trong `tmp_path` có checker không gọi AWS, kiểm mã thoát và bản ghi SQLite.

## Verification

- `cd server && uv run pytest` qua.
- Thủ công: `uv run labctl start fixture-vpc` → `uv run labctl check fixture-vpc` trượt → tạo VPC theo task → `check` đạt → `uv run labctl status` hiện kết quả đó.
