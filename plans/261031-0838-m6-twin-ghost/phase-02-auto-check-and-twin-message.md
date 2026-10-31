---
phase: 2
title: "Chạy check tự động và tin twin trên /ws"
status: completed
priority: P1
effort: "7h"
dependencies: [1]
---

# Phase 2: chạy check tự động và tin `twin` trên `/ws`

## Goal

Lab-server tự chạy check của lab đang mở khi trạng thái emulator đổi, ghi progress khi kết quả đổi, và đẩy tin `twin` cho mọi trình duyệt.

## Files to Create / Modify

- Modify: `server/src/cloudy_labs/progress.py` — `record_if_changed(attempt_id, results) -> bool`.
- Modify: `server/src/cloudy_labs/twin.py` — model pydantic `TwinState` (camelCase, `to_dict`), hàm `twin_state(loaded, attempt, results | None, graph)`.
- Create: `server/src/cloudy_labs/server/twin_runner.py` — `TwinRunner`.
- Modify: `server/src/cloudy_labs/server/hub.py` — hook gọi khi publish graph mới và ở mỗi nhịp poll; gửi tin `twin` hiện tại cho client mới.
- Modify: `server/src/cloudy_labs/server/app.py` — tạo `TwinRunner` trong `create_app` (tham số tiêm được cho test: `checks_runner`), khởi động và dừng trong `lifespan`.
- Create: `server/tests/test_twin_runner.py`; Modify: `server/tests/test_progress.py`, `server/tests/test_hub.py`, `server/tests/test_app.py`.
- Create: golden `twin` cho web, đặt cạnh golden graph (`GOLDEN` trong `server/tests/test_collector.py`), sinh lại bằng `UPDATE_GOLDEN=1` như golden graph.

## Tasks & Steps

1. `Progress.record_if_changed`: so kết quả mới với `latest_results` của chính attempt đó (không theo lab); khác thì `record_checks` và trả `True`. Danh sách rỗng ở lần đầu tính là khác.
2. `TwinState`: `lab`, `attempt`, `checks` (`id, task, description, status, message, resourceIds`), `ghosts`, `bound`. Không có attempt mở → `{lab: null, …}` rỗng. Graph `emulator-down` → mọi check `pending`, ghost giải theo kết quả rỗng.
3. `TwinRunner`:
   - `trigger(reason)` từ hub; một lượt một lúc, cờ dirty như `GraphHub.refresh`.
   - Một lượt: `current_lab()` trong thread → nếu graph `ok` thì `get_provider(...)`, `run_checks` trong thread, `record_if_changed` (mở `Progress` mới trong thread, như `current_lab`) → `bind_target` → `TwinState`; broadcast khi `to_dict()` khác lần trước.
   - Nhịp poll chỉ trigger khi lượt trước còn check `failed`.
   - Lỗi trong một lượt (provider không với tới, lab không load được) không làm sập server: log, trạng thái check `pending` kèm message lỗi.
4. Hub: gọi `runner.trigger` sau `broadcast(graph)` trong `_publish`, và trong `_poll_loop` khi graph không đổi. Client mới `subscribe` nhận `graph` rồi `twin` hiện tại (nếu có).
5. `labctl check` không đổi. Kiểm tay: `labctl check` ở terminal khi server đang chạy không làm hỏng tin `twin` (lượt auto tiếp theo cho cùng kết quả, không ghi thêm).
6. Sinh golden `twin` cho lab-06 trên golden graph với một nửa số check qua.

## Verification

- `cd server && uv run pytest tests/test_progress.py tests/test_twin_runner.py tests/test_hub.py tests/test_app.py -q`
- Test tối thiểu:
  - `record_if_changed` ghi lần đầu, không ghi khi giống, ghi khi một check đổi; attempt mới thì ghi lại;
  - runner với `run_checks` giả: graph đổi → một tin `twin`; hai trigger dồn → đúng hai lượt; kết quả không đổi → không broadcast;
  - graph `emulator-down` → không gọi checker, check `pending`;
  - poll trigger khi còn `failed`, không trigger khi mọi check `passed`;
  - client `/ws` mới nhận `graph` rồi `twin`;
  - attempt đổi (giả `labctl reset`) → tin `twin` có attempt mới, mọi check theo kết quả mới.
- `uv run pytest -q` toàn bộ server xanh.
