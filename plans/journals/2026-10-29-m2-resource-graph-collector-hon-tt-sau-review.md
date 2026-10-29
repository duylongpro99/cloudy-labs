---
title: M2 resource graph collector hoàn tất sau review
date: 2026-10-29
summary: "M2 xong: collector, api-tap, labctl serve, cảnh live; sửa 11/12 mục review, L5 ghi tài liệu"
---

# M2 resource graph collector hoàn tất sau review

## Chuyện gì đã xảy ra
- Hoàn tất 6 phase của plan `261029-1006-m2-resource-graph-collector-scene`: collector đọc Floci thành ResourceGraph, api-tap (4566 → Floci, SSE 4568), `labctl serve` (FastAPI 127.0.0.1:8730, WebSocket), cảnh 3D live trên Vite 5174.
- Review (`reports/code-review-m2.md`): 2 High, 4 Medium, 6 Low.
  - H1: api-tap ghi `Content-Length: 0` cho HEAD nên S3 HeadObject mất kích thước object. Sửa: giữ nguyên header của upstream với HEAD/204/304.
  - H2: hằng `FLOCI_OWNER = 4566` có thể xoá instance và forwarder của một Floci mặc định khác. Probe với `FLOCI_PORT=4569` cho thấy `io.floci.owner` đi theo cổng Floci nghe trong container. Compose nay đặt `FLOCI_PORT=4567` và publish `4567:4567`; forwarder chỉ bị dọn khi tên chứa id instance của stack này.
  - M1: chỉ một lần collect lỗi là xoá cả cảnh. Sửa: Floci từ chối kết nối (`EndpointConnectionError`) thì `emulator-down` ngay; timeout hoặc lỗi khác phải lặp 2 lần liền.
  - M2–M4, L1–L4, L6 đều đã sửa và có test. L5 (nâng cấp khi stack M1 còn chạy) ghi vào `docs/emulator-differences.md`.

## Kết quả
- Server 146 passed; `pytest -m docker` 6 passed; độ trễ ghi → WS p50 233 / p95 281 ms.
- Web 97 passed (10 file), typecheck sạch.
- E2E: lab 6+7 chạy qua tap không bước nào lỗi, đối chiếu sơ đồ khớp; serve tắt rồi bật lại thì trang tự nối lại; không có lỗi trên trang.

## Quyết định
- Sau khi sửa M1, `labctl reset` thường không hiện `emulator-down`: cổng chỉ đóng khoảng 0,5 s, ngắn hơn chu kỳ poll 5 s. Lần trước nó hiện là nhờ timeout bị tính thành "down", chính là lỗi M1.
- Chấp nhận như vậy và ghi lại thành hạn chế, không thêm kênh báo riêng từ reset sang serve. Mục tiêu "về Region trống, không tải lại trang" vẫn đạt.

## Bước tiếp
- Chạy `labctl reset <lab>` trọn vẹn khi đã có lab thật.
- Xử lý nhãn chồng nhau ở M3.
- Chưa commit; chờ người dùng yêu cầu.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
