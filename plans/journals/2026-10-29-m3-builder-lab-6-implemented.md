---
title: M3 builder kéo-thả cho Lab 6 đã làm xong, chờ Lab 6 thật
date: 2026-10-29
summary: "M3 xong với lab fixture: builder kéo-thả chạy đủ 20 bước Lab 6 và check 8/8; đã sửa 13 mục review; plan để in-review"
---

# M3 builder kéo-thả cho Lab 6 đã làm xong, chờ Lab 6 thật

## Chuyện gì đã xảy ra
- Làm đủ 6 phase của plan `261029-1525-m3-builder-lab-06`.
  - Phía server: lab fixture `fixture-lab-06`, danh mục op cố định (`builder/ops.py`), validate theo graph (`builder/validate.py`), runner không qua shell (`builder/runner.py`), các endpoint `/api/lab`, `/api/preview`, `/api/run`, và profile `lab` mà `labctl up` ghi vào config AWS.
  - Phía web: palette, thả vào khay, thao tác nối, nút thuộc tính, panel lệnh.
- Lần chạy e2e đầu hỏng vì ba chỗ:
  - Camera đổi khung khi cảnh lớn dần, nên điểm thả bị lệch. Sửa bằng cách cho script fit-view và kiểm tra điểm còn trên canvas.
  - NAT chưa `available` khi script thêm route tới NAT.
  - Nhãn Elastic IP che NAT Gateway.
- Script e2e làm route public trước NAT, vì NAT phải nằm trong subnet đã là public.
- Review (`reports/code-review-m3.md`) có 2 High, 4 Medium, 6 Low.
  - H1: ghi config qua symlink thì symlink bị thay bằng file thường.
  - H2: có thể bấm Run một preview cũ ngay sau khi sửa form.
  - M1: danh sách AZ rỗng thì bỏ qua bước kiểm AZ.
  - M2–M4: runner mất output khi timeout, bỏ lại tiến trình `aws` khi bị huỷ, và nuốt comment của section kế tiếp trong config.
  - Đã sửa đủ 2 High, 4 Medium và 6 Low, kèm test (bảng "Xử lý" trong report).

## Kết quả
- Server: 247 passed, ruff sạch.
- Web: 141 passed, typecheck sạch, `check-builder.mjs` 22/22.
- E2E Docker sau khi sửa: 20/20 bước, mỗi lần bấm Run đúng một `/api/run`, Run → cảnh p50 809 ms và p95 816 ms, `labctl check` 8/8.

## Quyết định
- Run bị chặn hẳn, chứ không chỉ cảnh báo, khi AWS CLI cũ hơn 2.13 hoặc file credentials có `[lab]`. Cả hai trường hợp đều có thể đưa lệnh tới AWS thật thay vì emulator.
- Runner đang bận thì trả 409 chứ không xếp hàng, để hai tab không chạy cùng một thao tác hai lần.
- Server không đọc được id tài nguyên từ stdout thì web chờ một graph mới hơn graph trước khi chạy, thay vì báo xong ngay.

## Bước tiếp
- Chạy lại e2e với Lab 6 thật khi có nội dung lab; M3 chỉ đóng sau bước đó.
- Kiểm xem Floci có từ chối subnet có CIDR chồng lấn không.
- Chưa commit; chờ người dùng yêu cầu.
