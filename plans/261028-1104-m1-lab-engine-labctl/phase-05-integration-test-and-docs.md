---
phase: 5
title: "Kiểm thử tích hợp và tài liệu"
status: completed
priority: P1
effort: "3h"
dependencies: [4]
---

# Phase 5: Kiểm thử tích hợp và tài liệu

## Goal

Chứng minh vòng đời lab đầu-cuối trên Docker thật, và ghi tài liệu cách chạy cùng các điểm emulator khác AWS thật (NFR5).

## Files to Create / Modify

- Create: `server/tests/test_lifecycle_docker.py` (marker `docker`)
- Create: `docs/emulator-differences.md`
- Create: `docs/labctl.md`
- Modify: `docs/roadmap.md` (dòng M1: link plan, trạng thái), `docs/product-requirements.md` (F1.2 thêm `labctl down`, đã chốt ở Validation Log)
- Modify: `plans/261028-1104-m1-lab-engine-labctl/plan.md` (trạng thái, kết quả)

## Tasks & Steps

1. `test_lifecycle_docker.py` dùng thư mục `CLOUDY_LABS_HOME` tạm và `CLOUDY_LABS_LABS_DIR` trỏ tới fixture:
   - `up` → `start fixture-vpc` → `check` trượt → tạo VPC bằng boto3 (đóng vai người học) → `check` đạt, SQLite có bản ghi.
   - `reset fixture-vpc` → `check` trượt.
   - Kiểm trên moto: `reset` + `reset-auth` khôi phục lượt không xác thực (tạo user không ký 1 lần sau reset thành công).
   - `down` → không còn container/network/volume mang label owner của stack.
   - Fixture teardown luôn gọi `down`, để test lỗi giữa chừng cũng không bỏ lại tiến trình.
2. `docs/emulator-differences.md`: chuyển các điểm ở báo cáo M0 mục 3 thành ghi chú cho người soạn lab, gồm: IMDS chiếm `169.254.169.254:80` nên UserData (ví dụ Lab 7) phải bind vào IP private lấy từ `local-ipv4`; CIDR trùng mạng Docker; `PublicIpAddress` là `127.0.0.1`; `ReservationId` không ổn định; instance `running` trước khi UserData xong; moto bỏ qua `Condition`; tài nguyên mồ côi sau `compose down`.
3. `docs/labctl.md`: yêu cầu (Docker Desktop, uv), cài đặt, từng lệnh, vị trí `~/.cloudy-labs`, cách viết một lab (schema, checker, ví dụ rút gọn từ fixture), cảnh báo chỉ nạp lab tin cậy.
4. Cập nhật roadmap dòng M1 với link plan; ghi rõ phần "Lab 6 + 7" của điều kiện qua mốc còn chờ nội dung lab.
5. Chạy `uv run pytest -m docker`, ghi kết quả vào plan.

## Verification

- `cd server && uv run pytest && uv run pytest -m docker` qua hết.
- Sau test: `docker ps -a --filter label=io.floci.owner` trống và không còn container `cloudy-labs-*`.
- Link trong `docs/labctl.md`, `docs/emulator-differences.md` và roadmap trỏ tới file có thật.
