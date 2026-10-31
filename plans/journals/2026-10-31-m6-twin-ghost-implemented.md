---
title: M6 twin và ghost đã xong với lab fixture
date: 2026-10-31
summary: "Check tự chạy, ghost gắn qua check, panel check có tô sáng; đạt 8 tiêu chí brainstorm và 2 tiêu chí bổ sung trên emulator thật; review không có High, đã sửa cả 5 mục"
---

# M6 twin và ghost đã xong với lab fixture

## Chuyện gì đã xảy ra

Đã làm đủ 5 phase của plan `261031-0838-m6-twin-ghost`.

**Server**
- Thêm schema `target` vào lab.
- Thêm `bind_target`: hàm thuần, gắn node vào tài nguyên thật qua `resource_ids` của các check đã qua.
- Thêm `TwinRunner`: chạy check khi graph đổi, và chạy ở mỗi nhịp poll khi còn check trượt.
- `/ws` có thêm tin `twin`.
- `record_if_changed`: chỉ ghi progress khi kết quả đổi.

**Web**
- `mergeTwin` thêm ghost vào cảnh; ghost vẽ mờ, viền nét đứt.
- Dấu đạt cho tài nguyên đã gắn.
- Panel "Kiểm tra" gom theo task, bấm một check thì tô sáng tài nguyên liên quan.
- Công tắc ẩn/hiện ghost.

**Docker e2e lần đầu trượt.** Ghost VPC không mất sau `create-vpc`, vì node chỉ gắn khi mọi check nó khai báo đều qua; lab 06 còn cần DNS hostnames. Đây là đúng thiết kế, nên test giờ đo độ trễ ghost từ lệnh ghi hoàn tất điều kiện.

**Kiểm tay trên trình duyệt** tìm ra hai lỗi UX:
- Panel che nửa cảnh ở cửa sổ nhỏ. Panel giờ gập được.
- "Lần làm N" cũ sau `labctl reset`. `useLab` giờ tải lại theo lab và attempt của twin.

**Review** không có mục Critical hay High. Đã sửa cả năm mục, mỗi mục có test:
- Badge SG và EIP đã gắn không có dấu đạt.
- Một describe bị timeout bị ghi thành check trượt. Giờ lỗi đó thành `EmulatorSlow`: lượt đó giữ kết quả cũ và nhịp poll sau chạy lại.
- Nhịp poll đến giữa lúc collect bị mất.
- Ẩn ghost rồi chọn check thì cả cảnh bị làm mờ.
- Thứ tự tắt server.

Mỗi lượt check giờ dùng một boto3 session riêng thay cho session mặc định mà collector cũng dùng.

## Kết quả

- Server: 426 passed, ruff sạch. Web: 207 passed, typecheck và build sạch.
- Docker `test_twin_docker.py`: 2 passed. Số đo sau khi sửa:
  - Lệnh CLI tới graph: trung vị 110 ms.
  - Lệnh ghi cuối tới lúc ghost mất: trung vị 501 ms.
  - Subnet tạo bằng boto3 tới graph: 198 ms.
  - Một lượt check: 398 ms (lab 06) và 360 ms (lab 07).
- Bench ghosts20: 120 fps, 211 draw call.
- Đạt cả 10 tiêu chí; chi tiết ở `plans/261031-0838-m6-twin-ghost/notes/e2e-results.md`.

## Quyết định

- Lỗi timeout hoặc mất kết nối của botocore được bắt qua sự kiện `needs-retry`. botocore 1.43 không có `after-call-error`, còn bọc client bằng proxy sẽ bỏ sót các lời gọi qua paginator.
- Đổi lấy an toàn thread bằng khoảng 100 ms mỗi lượt check, do mỗi lượt tạo session mới.

## Bước tiếp

- Dấu đạt trên badge mới có test dữ liệu; chưa xem bằng mắt trên trình duyệt.
- Khi có Lab 6 và 7 thật, tác giả lab viết `target` theo `docs/labctl.md`, rồi chạy lại phần kiểm đầu-cuối.
- Chưa commit; chờ người dùng yêu cầu.
