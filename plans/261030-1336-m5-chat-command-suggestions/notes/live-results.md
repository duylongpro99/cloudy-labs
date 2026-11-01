# Bộ câu hỏi mẫu với LLM thật: kết quả

**Đã chạy 2026-11-01** với provider của người dùng (endpoint OpenAI-compatible, model `ds/deepseek-v4-pro`). Lúc làm M5 (2026-10-30) máy chưa có provider nên bộ câu hỏi chưa chạy được.

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
| 2026-11-01, lần 1 | `ds/deepseek-v4-pro` | `openai` | 9/9 | 7/9 | 06: đạt, 07: đạt |
| 2026-11-01, lần 2 (sau khi sửa test) | `ds/deepseek-v4-pro` | `openai` | 8/9 | 9/9 | 06: đạt, 07: đạt |

### Câu trượt

| Test id | Lý do (trích lỗi assert) | Do model hay do code |
|---|---|---|
| `fixture-lab-07-*` (2 câu, lần 1) | `sourceGroupId:  is not in the scene` | Do test. Model để trống `sourceGroupId`, trường SG nguồn tuỳ chọn của rule inbound; server validate đạt và lệnh đúng (chỉ `IpRanges`). Test coi mọi tham số `*Id` phải có trong cảnh kể cả khi rỗng. Đã sửa test để bỏ qua giá trị rỗng. |
| `fixture-lab-06-built1` (lần 2) | `expected ['create-subnet'], got []` | Do model. Lần 1 câu này đạt; lần 2 model trả lời không kèm bước nào. |
