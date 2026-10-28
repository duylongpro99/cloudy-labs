# Brainstorm: Lớp trực quan hoá 3D cho hands-on labs

- Thời điểm: 2026-10-27 14:23 (Asia/Saigon)
- Đầu vào: `plans/reports/research-261027-1027-cloud-simulator-for-hands-on-labs.md` (phương án A: Floci + `labctl`)
- Quyết định của người dùng: Floci portal nhàm chán → xây lớp 3D riêng. Thứ tự tính năng: **(1) builder kéo-thả → (2) chat tự nhiên gợi ý lệnh → (3) digital twin**. Phong cách: **sơ đồ kiến trúc AWS nâng thành 3D**. Lát cắt đầu: **Lab 6 + 7 (VPC & EC2)**.

## 1. Hợp đồng

### Kết quả
Một web app chạy cục bộ (localhost) cho phép người học:

1. **Builder**: kéo thả tài nguyên AWS vào cảnh 3D theo đúng kiểu sơ đồ kiến trúc AWS (Region → VPC → AZ → Subnet → Instance). Mỗi thao tác sinh ra **đúng lệnh `aws` CLI**, hiện cho người học xem, rồi chạy thật vào emulator. Cảnh chỉ cập nhật theo trạng thái emulator trả về, không theo ý định của thao tác.
2. **Chat**: người học mô tả bằng ngôn ngữ tự nhiên ("tạo 2 public subnet ở 2 AZ"), hệ thống gợi ý chuỗi lệnh CLI kèm giải thích; người học xác nhận từng lệnh trước khi chạy.
3. **Twin**: người học gõ CLI/Terraform ở terminal, cảnh 3D phản chiếu trạng thái thật; lab hiển thị kiến trúc mục tiêu dạng mờ (ghost), tài nguyên đạt check thì đặc lại.

### Ràng buộc
- Giữ phương án A: Floci (MiniStack thay được) qua wire protocol AWS ở cổng 4566; `labctl` + checker Python/boto3 vẫn là nguồn chấm điểm duy nhất.
- **Emulator là nguồn sự thật.** Builder và chat không bao giờ vẽ tài nguyên chưa tồn tại trong emulator (trừ ghost mục tiêu của lab, được đánh dấu rõ).
- **Không dữ liệu giả**: không hoạt ảnh luồng mạng trong VPC vì emulator không có data plane. Chỉ hoạt ảnh lệnh API và sự kiện thật.
- Học CLI vẫn là mục tiêu: builder và chat luôn hiện lệnh CLI tương đương; không có thao tác "ẩn" gọi SDK mà người học không thấy.
- Chat cần LLM (Claude API, model `claude-sonnet-5-5` hoặc `claude-haiku-5-5`) → cần API key, có chi phí; LLM chỉ gợi ý, không tự chạy.

### Ngoài phạm vi
Viết emulator mới; giả lập lưu lượng mạng; nhiều người dùng / triển khai cloud; GCP; mô hình 3D tả thực hoặc asset pipeline (Blender/glTF) ở giai đoạn đầu.

### Tiêu chí chấp nhận (lát cắt Lab 6 + 7)
1. Kéo "Subnet" vào một AZ của VPC → panel hiện lệnh `aws ec2 create-subnet --vpc-id ... --cidr-block ... --availability-zone ...`; sau khi chạy, subnet xuất hiện trong ≤2 s ở đúng AZ, lấy ID thật từ emulator.
2. CIDR chồng lấn hoặc nằm ngoài VPC bị chặn trước khi gửi lệnh, kèm giải thích; nếu emulator vẫn trả lỗi thì lỗi thật được hiển thị nguyên văn.
3. Chat: câu "cho subnet public ra internet" → gợi ý `create-internet-gateway`, `attach-internet-gateway`, `create-route` với ID thật từ trạng thái hiện tại; không lệnh nào chạy khi chưa xác nhận.
4. Twin: tài nguyên tạo từ terminal xuất hiện trong cảnh trong ≤2 s; ghost của Lab 6 đặc lại khi check tương ứng qua; `labctl reset` đưa cảnh về sạch.
5. Đổi image Floci → MiniStack không cần sửa frontend.

## 2. Phát hiện quan trọng: twin là nền móng, không phải tính năng cuối

Builder theo nguyên tắc "emulator là nguồn sự thật" cần đọc ngược trạng thái emulator sau mỗi lệnh — đó chính là **collector + scene graph** của twin. Nếu builder tự giữ trạng thái riêng, cảnh sẽ lệch ngay khi người học gõ thêm lệnh ở terminal, khi lệnh lỗi một phần, hoặc khi reset lab.

→ **Thứ tự tính năng người dùng thấy giữ nguyên (builder → chat → twin)**, nhưng hạ tầng xây theo thứ tự: collector/scene graph trước, builder là tính năng đầu tiên dùng nó. Twin ở cuối chỉ còn là thêm ghost mục tiêu + nguồn sự kiện từ terminal, chi phí nhỏ.

## 3. Kiến trúc đề xuất

```text
 Trình duyệt (React + React Three Fiber)
 ┌──────────────────────────────────────────────────────────┐
 │ Palette kéo-thả │ Cảnh 3D (sơ đồ AWS 3D) │ Panel lệnh CLI │
 │ Chat            │ ghost mục tiêu lab      │ Kết quả check  │
 └──────────┬───────────────────▲───────────────────────────┘
   intent   │ REST              │ WebSocket: resource graph + event
 ┌──────────▼───────────────────┴───────────────────────────┐
 │ lab-server (Python, FastAPI) — dùng chung code với labctl │
 │  command-builder: intent → lệnh aws CLI (+ validate)      │
 │  runner: chạy `aws --profile lab ...`, trả stdout/stderr  │
 │  chat: Claude API + resource graph hiện tại → gợi ý lệnh  │
 │  collector: boto3 describe/list → resource graph JSON     │
 │  checker: tái dùng checks/ của labctl                      │
 └──────────┬───────────────────▲───────────────────────────┘
            │                   │ "có thay đổi" → chụp lại
 ┌──────────▼───────────┐  ┌────┴─────────────────────────┐
 │ Floci :4566 (Docker) │◄─┤ api-tap (proxy mỏng) :4566→  │◄── aws CLI ở terminal
 └──────────────────────┘  │ ghi log lệnh API              │
                           └───────────────────────────────┘
```

- **Resource graph** là hợp đồng trung tâm: `nodes` (id thật, type, thuộc tính), `contains` (Region⊃VPC⊃AZ⊃Subnet⊃Instance), `edges` (route → IGW/NAT, SG gắn ENI…). Builder, chat, twin, ghost đều đọc/ghi qua nó.
- **api-tap**: proxy chuyển tiếp mọi request tới Floci, phát sự kiện khi gặp lệnh ghi (Create/Delete/Modify/Put/Attach…) để collector chụp lại ngay, thay vì polling dày. Có thêm polling chậm (~5 s) làm lưới an toàn. Đặt proxy ở cổng người học dùng, Floci lùi sang cổng nội bộ.
- **Phong cách "sơ đồ AWS 3D"**: nhóm (Region/VPC/AZ/Subnet) là khay trong suốt ép đùn, viền và màu theo quy ước nhóm của sơ đồ AWS; dịch vụ là khối có icon dán mặt trên. Layout xác định (deterministic) theo cây `contains`, giống cách vẽ sơ đồ tay. Hình khối dựng bằng code, không cần file mô hình.

## 4. Các hướng đã cân nhắc

| | **Builder sinh lệnh CLI, chạy thật, đọc lại trạng thái** (chọn) | Builder giữ model riêng, xuất CloudFormation khi "Deploy" | Builder chạy boto3 trực tiếp |
|---|---|---|---|
| Phụ thuộc nhất vào | Floci trả về đủ thuộc tính qua describe để dựng lại cảnh | CloudFormation của Floci hỗ trợ đủ resource type của VPC/EC2 | — |
| Hỏng đầu tiên khi | Floci thiếu/ sai trường trong describe (vd. AZ của subnet) → phải ghi sai khác và vá trong collector | Stack lỗi giữa chừng → cảnh và emulator lệch; người học không thấy lệnh từng bước | Người học không thấy CLI → mất mục tiêu học cú pháp |
| Giá trị học | Cao: mỗi thao tác = một lệnh thấy được | Trung bình: học IaC, không học từng API | Thấp |

Better approaches: không có hướng nào tốt hơn thứ tự người dùng chọn về mặt tính năng; chỉ điều chỉnh thứ tự **hạ tầng** như mục 2 (bằng chứng: builder cần đọc lại trạng thái để không lệch với terminal và reset).

## 5. Rủi ro
1. **Độ đầy đủ describe của Floci cho EC2/VPC chưa kiểm chứng** — spike trong báo cáo nghiên cứu (mục 7.1) vẫn cần làm trước, giờ thêm việc ghi lại trường nào thiếu cho collector.
2. **Chat gợi ý lệnh sai/ảo giác** — giảm thiểu: đưa resource graph thật vào prompt, validate lệnh gợi ý qua cùng command-builder trước khi hiện, bắt buộc xác nhận.
3. **Phạm vi lớn** (3 chế độ + 3D) — giảm thiểu: lát cắt Lab 6+7 làm trọn builder trước, chat và twin là phase sau trên cùng resource graph.
4. **Giấy phép AWS Architecture Icons** khi dán vào mô hình 3D — cần đọc điều khoản trước khi dùng; dự phòng là icon tự vẽ.

## 6. Bước tiếp theo
1. Spike Floci (nửa ngày): chạy lệnh Lab 6+7, ghi lại output `describe-*` để chốt schema resource graph.
2. Lập plan bằng `ak:plan` với các phase: resource graph + collector + api-tap → cảnh 3D tĩnh từ graph → builder Lab 6 → builder Lab 7 → chat → twin + ghost.

## Câu hỏi còn mở
1. Builder chạy lệnh ngay sau khi kéo thả, hay hiện lệnh và đợi người học bấm "Run" (hoặc tự gõ lại ở terminal)? Đề xuất: mặc định hiện lệnh + bấm Run, có tuỳ chọn "tự gõ" cho chế độ luyện tập.
2. Có sẵn sàng dùng Claude API (key + chi phí) cho chat không, hay cần phương án offline?
3. Frontend React/TypeScript + backend Python có ổn không (giữ nguyên giả định Python của báo cáo trước)?
