# Brainstorm M5: chat gợi ý lệnh

- Ngày: 2026-10-30
- Mốc: M5 trong [roadmap](../../docs/roadmap.md). Phạm vi PRD F5.1–F5.7 ([PRD](../../docs/product-requirements.md)).
- Trạng thái: đã chốt với người dùng, chuyển sang lập plan.

## Outcome

Web app có panel chat. Người học mô tả việc muốn làm và nhận về một chuỗi lệnh `aws ... --profile lab`. Mỗi lệnh có giải thích ngắn, dùng ID thật lấy từ resource graph, và đã đi qua validate của builder. Người học bấm Run cho từng lệnh hoặc cho cả chuỗi. Ở chế độ luyện tập, người học chép từng lệnh ra terminal tự chạy, và các ID của bước sau được điền tự động khi graph thấy tài nguyên do bước trước tạo ra.

## Constraints

- Không lệnh nào tự chạy (A1, F5.4). Run cả chuỗi chạy lần lượt từng bước, chờ collector xác nhận bước trước rồi mới chạy bước sau, và dừng ngay ở bước đầu tiên bị lỗi.
- Provider do người dùng tự cấu hình qua `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` và `LLM_API_FORMAT` (`openai` hoặc `anthropic`), đọc từ biến môi trường hoặc từ file cục bộ trong `~/.cloudy-labs/` (`config.home()`), nằm ngoài git. Key không bao giờ xuất hiện trong repo, log, response hay giao diện (F5.5, NFR6).
- Gọi provider bằng `httpx` có sẵn trong `server/pyproject.toml`, không thêm SDK.
- Chưa cấu hình provider thì chat tắt và hiện hướng dẫn cấu hình. Builder vẫn hoạt động bình thường (F5.7).
- `/api/chat` dùng chung lớp bảo vệ origin và JSON với `/api/preview` (`op_request` trong `server/app.py`).

## Non-goals

- Chạy hay validate lệnh nằm ngoài danh mục op của builder.
- Streaming token, lưu lịch sử chat phía server, nhiều phiên chat.
- Twin, ghost và trường `target` (M6). Lab ngoài Lab 6 và Lab 7.
- Nội dung Lab 6 và Lab 7 thật.

## Hướng đã chọn: LLM chọn op trong danh mục

LLM trả về JSON `{reply, steps: [{op, params, explanation}]}` hoặc một lời từ chối có lý do. `op` phải nằm trong `catalog(palette)` của lab đang mở, và `params` theo đúng model pydantic của op đó (`builder/ops.py`). Server dựng argv, chạy `validate()` trên graph hiện tại, rồi trả về cho web cùng định dạng với `/api/preview` (`command`, `problems`, `practiceExpect`). Bước nào sai op hoặc sai params được đánh dấu, không bị bỏ đi.

- **Chuỗi phụ thuộc:** một param có thể là `{"ref": <số bước>}`, nghĩa là ID của tài nguyên do bước đó tạo ra. Lúc gợi ý, bước có ref được đánh dấu "validate khi chạy". Ở chế độ thường, web thay ref bằng ID lấy từ `expect.node` của bước trước rồi gọi `/api/run`, và route này đã validate lại. Ở chế độ luyện tập, web lấy ID từ node khớp `practiceExpect` (`kind` và `label`) của bước trước. Server vẫn stateless.
- **Ngữ cảnh gửi cho LLM:** graph rút gọn (id, kind, label, các thuộc tính mà validate dùng), danh mục op kèm schema params, AZ, `choices()` (AMI và instance type), task của lab, và lịch sử chat do web gửi kèm.
- **Phạm vi (F5.6):** danh mục op đã lọc theo palette chính là ranh giới của lab. Prompt nêu rõ những gì emulator không hỗ trợ, dựa trên `docs/emulator-differences.md`, để LLM nói thẳng thay vì bịa lệnh.
- **Lấy JSON:** yêu cầu JSON trong nội dung text, parse bằng pydantic, và cho model sửa lại một lần nếu parse lỗi. Không dùng tool calling, vì endpoint OpenAI-compatible tự host hỗ trợ tool calling không đồng đều.

## Trade-offs

- **A. Op theo danh mục (đã chọn).** Giả định chịu lực: model làm theo được JSON schema của danh mục op. Gãy đầu tiên khi người học hỏi một việc mà builder chưa có op. Khi đó chat trả lời là việc này nằm ngoài phạm vi, nghĩa là chấp nhận đánh đổi khả năng linh hoạt để có validate và an toàn.
- **B. CLI tự do.** Giả định chịu lực: model viết CLI đúng và server parse lại được. Gãy gần như ngay từ đầu, vì lệnh ngoài danh mục không validate được (vi phạm F5.3), và argv do LLM viết có thể mang `--profile default` hay `--endpoint-url` rồi chạm AWS thật.

Better approaches: none — hướng được chọn chính là hướng đề xuất ban đầu. Bằng chứng: `op_request` đã ép `{op, params}`, đã chặn `server_fields`, và đã lọc theo palette.

## Acceptance criteria

1. Có bộ câu hỏi mẫu cho `fixture-lab-06` và `fixture-lab-07`. Chạy với một provider OpenAI-compatible thật (người dùng đã có sẵn), mọi bước gợi ý dùng ID có trong graph hoặc ref hợp lệ, và qua validate. Ghi kết quả vào `notes/` của plan.
2. Câu hỏi ngoài phạm vi lab bị từ chối kèm lý do. Câu hỏi về API mà emulator không hỗ trợ thì chat nói rõ điều đó.
3. Có unit test cho cả hai định dạng `openai` và `anthropic` qua `httpx.MockTransport`, gồm cả trường hợp JSON hỏng rồi được sửa lại.
4. Có test rằng key không có trong response, log hay thông báo lỗi.
5. Chưa cấu hình provider thì `/api/lab` báo chat tắt, web hiện hướng dẫn, và builder vẫn chạy.
6. Run cả chuỗi dừng ở bước lỗi đầu tiên. Ref được thay đúng ID ở cả chế độ thường lẫn chế độ luyện tập.

## Rủi ro còn lại

- Chất lượng gợi ý phụ thuộc model mà người dùng chọn. Model nhỏ có thể không làm theo được schema, và cơ chế sửa lại một lần chỉ giảm bớt chứ không loại bỏ được rủi ro này.
- Graph lớn làm prompt dài. Với Lab 6 và Lab 7 thì kích thước hiện tại vẫn nhỏ, nhưng tới M7 cần đo lại.
- Lab 6 và Lab 7 thật chưa có nội dung, nên bộ câu hỏi mẫu chỉ chứng minh được trên fixture.
