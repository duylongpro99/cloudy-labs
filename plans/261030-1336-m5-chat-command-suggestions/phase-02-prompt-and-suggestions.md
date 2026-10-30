---
phase: 2
title: "Prompt, parse và gợi ý đã validate"
status: completed
priority: P1
effort: "8h"
dependencies: [1]
---

# Phase 2: Prompt, parse và gợi ý đã validate

## Goal

Từ câu hỏi của người học, lab đang mở và graph hiện tại, dựng prompt, gọi provider, parse câu trả lời thành các bước op, giải ref, rồi dựng lệnh và validate từng bước bằng đúng code của builder (F5.1–F5.3, F5.6).

## Files to Create / Modify

- Create: `server/src/cloudy_labs/chat/prompt.py`
- Create: `server/src/cloudy_labs/chat/suggest.py`
- Create: `server/tests/test_chat_prompt.py`
- Create: `server/tests/test_chat_suggest.py`
- Modify: `server/src/cloudy_labs/builder/ops.py` (chỉ nếu cần một hàm công khai trả JSON schema của params theo alias, bỏ `server_fields`)

## Tasks & Steps

- [x] `prompt.py`: `system_prompt(lab, graph, azs, choices) -> str`, thuần, không I/O. Gồm:
  - Vai trò: trợ giảng của lab `<title>`; chỉ gợi ý bằng các op liệt kê; mọi lệnh chạy trên emulator cục bộ với profile `lab`; không bao giờ đề xuất credential AWS thật.
  - Danh mục op của lab (`catalog(palette)`) kèm `params` JSON schema theo alias camelCase, bỏ `server_fields`, và cử chỉ tương ứng trong builder.
  - Graph rút gọn: mỗi node `id`, `kind`, `label`, cha lấy từ `graph.contains`, và các prop mà validate dùng (`cidr`, `attachedVpc`, `ingress`, `groupName`, `state`, ...); mỗi cạnh `kind`, `from`, `to`, `label`. Bỏ node region và AZ, đưa AZ thành danh sách riêng.
  - `azs`, `choices` (AMI, instance type), task của lab, `builder.userData` mặc định, `builder.tags` không cần (server tự gắn).
  - Giới hạn emulator (hằng ngắn trong `prompt.py`, dẫn nguồn `docs/emulator-differences.md`) và quy tắc: việc không có op thì `refusal` nói rõ là ngoài phạm vi lab hoặc emulator không hỗ trợ.
  - Định dạng đầu ra bắt buộc và quy tắc `{"ref": n}`; trả lời bằng ngôn ngữ của người học.
- [x] `suggest.py`:
  - Model pydantic `Reply {reply: str, refusal: str | None = None, steps: list[RawStep] = []}`, `RawStep {op: str, params: dict[str, str | Ref], explanation: str}`. Bóc JSON khỏi khối ```` ```json ```` nếu model bọc lại.
  - `async suggest(messages, *, lab, graph, azs, choices, settings, complete=provider.complete) -> Suggestion`. Parse lỗi thì gửi lại một lần, thêm một lượt user nêu lỗi pydantic ngắn gọn; vẫn lỗi thì `Suggestion(reply="Model không trả về đúng định dạng; thử hỏi lại hoặc đổi model", steps=[])`.
  - Với mỗi bước: op không có trong `OPS` hoặc ngoài palette, có `server_fields`, params không qua `op.params.model_validate`, hoặc ref trỏ bước sau, bước chính nó, hay bước không phải `create`, thì đều thành `problems` với `field` tương ứng. Bước còn lại: nếu không có ref, dựng `Op.argv(params, tags)` và chạy `validate()`; nếu có ref, thay ref bằng `<id từ bước n>` để hiển thị lệnh, đặt `deferred=True`, bỏ qua validate theo graph. `modify-instance-attribute` được điền `currentGroups` từ graph như trong `checked` của `app.py`.
  - `practiceExpect` mỗi bước lấy từ `practice_expectation`. Kết quả mỗi bước gồm `op`, `params` (giữ nguyên ref để web giải), `explanation`, `command`, `problems`, `deferred`, `refs` (danh sách số bước được tham chiếu), `practiceExpect`.
- [x] Test prompt: có đúng các op của palette, không có op ngoài palette, không có `currentGroups`, có id thật từ graph fixture `lab-06-07.graph.json`; đo và ghi độ dài prompt (ký tự) cho fixture vào phần Verification của phase này khi làm.
- [x] Test suggest với `complete` giả trả chuỗi cố định: chuỗi hợp lệ hai bước có ref; JSON bọc trong code fence; JSON hỏng rồi sửa được; hỏng hai lần; op lạ; op ngoài palette; param thiếu; ref trỏ bước sau; ref trỏ bước không phải create; CIDR chồng lấn bị validate bắt; `refusal` không có bước.

## Verification

- Độ dài system prompt đo trên graph fixture `lab-06-07.graph.json`: `fixture-lab-06` 8196 ký tự, `fixture-lab-07` 8030 ký tự.

- `cd server && uv run pytest tests/test_chat_prompt.py tests/test_chat_suggest.py tests/test_builder_ops.py tests/test_builder_validate.py`
