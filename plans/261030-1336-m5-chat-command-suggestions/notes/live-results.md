# Bộ câu hỏi mẫu với LLM thật: kết quả

**Chưa chạy.** Lúc làm M5 (2026-10-30), máy phát triển chưa cấu hình provider: `load_settings()` trả `Missing` với đủ bốn biến `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_API_FORMAT`. Agent không đọc hay đặt key thay người dùng, nên điều kiện qua mốc "chuỗi gợi ý chạy hết thì `labctl check` đạt" **chưa được chứng minh với LLM thật**. Docker 29.7.2 và aws CLI đã có; 18 test được thu thập và bỏ qua với lý do `no LLM provider set`.

## Cách chạy

Đặt provider theo [docs/labctl.md](../../../docs/labctl.md#chat-gợi-ý-lệnh) (biến môi trường hoặc `~/.cloudy-labs/llm.env`), cổng 8730 trống, rồi:

```bash
cd server
uv run pytest -m llm tests/test_chat_live.py -v
```

Câu hỏi nằm ở [`questions.yaml`](../../../server/tests/fixtures/chat/questions.yaml): mỗi lab 6 câu `fresh` (có 2 câu ngoài phạm vi), 1 câu `build` bao trọn lab (chạy hết chuỗi qua `/api/run`, rồi `labctl check` phải đạt trong 90 giây), và 2 câu `built` phải dùng id có trong cảnh. Câu `built` bị bỏ qua nếu `build` của lab đó trượt.

Câu trượt do model thì ghi vào bảng dưới, không sửa test hay câu hỏi cho qua.

## Kết quả

| Ngày | Model (`LLM_MODEL`) | Định dạng | fixture-lab-06 đạt | fixture-lab-07 đạt | `build` + `labctl check` |
|---|---|---|---|---|---|
| | | | /9 | /9 | 06: , 07: |

### Câu trượt

| Test id | Lý do (trích lỗi assert) | Do model hay do code |
|---|---|---|
| | | |
