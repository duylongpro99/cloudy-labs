# Độ chính xác của `labctl coverage <lab>`

**Chưa đo.** Bài đo cần 5 lab do người dùng dán vào `labs/<slug>/content/` (cục bộ, không commit). Hiện `labs/` chưa có lab nào như vậy, nên chưa có precision và recall.

Cách đo khi có nội dung:

1. Với mỗi lab, chạy `uv run labctl coverage <slug> --json` và ghi kết luận, finding và danh sách chưa nhận diện.
2. Đánh giá tay từng lớp (`blocked`, `gap`, caveat, chưa nhận diện) bằng cách đọc trang lab.
3. Ghi vào bảng dưới: slug, số đúng/sai theo lớp, và loại sai (ví dụ "lệnh trong prose bị bỏ qua", "tên tài nguyên chung bị nhận nhầm"). Không ghi câu nào của trang lab.

| Lab | Lớp | TP | FP | FN | Loại sai |
|---|---|---|---|---|---|

Đã biết từ lần chạy danh mục: từ điển bỏ qua danh từ một từ (Volume, Endpoint, Snapshot), nên lab EBS và endpoint chỉ bị bắt qua lệnh `aws` trong trang hoặc qua `catalog-overrides.yaml`.
