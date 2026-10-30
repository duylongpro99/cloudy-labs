---
title: M4 builder cho Lab 7 và chế độ luyện tập đã làm xong, chờ Lab 7 thật
date: 2026-10-30
summary: "M4 xong với lab fixture: Lab 7 dựng bằng builder đạt 6/6 check ở cả Run và Luyện tập; sửa lỗi bind web server trên Floci và các mục review"
---

# M4 builder cho Lab 7 và chế độ luyện tập đã làm xong, chờ Lab 7 thật

## Chuyện gì đã xảy ra
- Làm đủ 6 phase của plan `261030-1045-m4-builder-lab-07`.
  - Phía server: `fixture-lab-07`, op cho Security Group, rule inbound, Key Pair, Instance và gắn SG; validate (chặn SSH mở cho cả Internet, giới hạn UserData, 5 SG mỗi instance); lựa chọn AMI và instance type theo kiến trúc máy.
  - Phía web: form EC2, rule SG, kéo cạnh SG → instance, tải .pem, công tắc Luyện tập.
- E2E Lab 7 trượt ở `web-server-answers`: socat forwarder của Floci gọi instance qua địa chỉ trên mạng compose, không qua IP private của VPC, và IMDS đã chiếm `0.0.0.0:80`. UserData giờ bind từng địa chỉ IPv4 trừ `lo`.
- Test API đọc graph khi `labctl start` chưa xong, nên subnet chưa là public; giờ test chờ theo cả loại node.
- Review (`reports/code-review.md`) có một High: aws CLI đọc file local khi một tham số bắt đầu bằng `file://`, nên trình duyệt có thể khiến lab-server đọc file trên máy. Cùng đó là các Medium:
  - Luyện tập tính nhầm tài nguyên trùng tên đã có sẵn.
  - `--groups` dựng từ graph cũ.
  - Lọt gate `currentGroups` bằng tên snake_case.
  - Nút Chép vẫn bật cho lệnh bị từ chối.
  - Nhãn cổng sai.
  - Gợi ý UserData đã cũ.
- Đã sửa tất cả các mục trên, kèm test.

## Kết quả
- Server: 313 passed, ruff sạch.
- Web: 165 passed, typecheck sạch, `check-builder.mjs` 22/22.
- `pytest -m docker`: 10 passed.
  - Lab 7 chế độ Run: 7/7 bước, 7 `/api/run` cho 7 lần bấm, p50 817 ms.
  - Lab 7 chế độ Luyện tập: 7/7 lệnh chạy trong shell, 0 `/api/run`, p50 703 ms.
  - `labctl check` đạt 6/6 ở cả hai chế độ.
- Floci từ chối subnet chồng lấn bằng `InvalidSubnet.Conflict`, như AWS; câu hỏi mở từ M3 đã đóng.

## Quyết định
- Chặn mọi giá trị bắt đầu bằng `file://`/`fileb://` ở validate, vì aws CLI không có công tắc tắt việc đọc file này. `http(s)://` không chặn vì aws CLI v2 mặc định không tải URL.
- `/api/run` cho `modify-instance-attribute` collect graph mới; collect lỗi thì trả 503 chứ không dùng graph cũ, để không tháo nhầm SG.
- Chép vẫn vào chế độ chờ khi ghi clipboard lỗi, vì lệnh vẫn hiện trên panel để chép tay.

## Bước tiếp
- Chạy lại e2e với Lab 7 thật khi có nội dung lab; M4 chỉ đóng sau bước đó.
- Còn mở, mức thấp: dòng "đã thấy" đếm cả lệnh lỗi, không có Thử lại khi Luyện tập lỗi, `seq` của api-tap đếm lại sau khi khởi động lại.
- Chưa commit; chờ người dùng yêu cầu.
