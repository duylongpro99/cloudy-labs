# PRD: Cloudy Labs — hands-on labs for AWS với lớp kiến trúc 3D

- Trạng thái: **Bản nháp v0.6**. Đã chốt A1–A3 và A7–A12 (A10 đổi tên thành Cloudy Labs ngày 2026-10-28). A4 và A6 đã kiểm chứng qua [spike M0](../plans/reports/spike-261027-2248-m0-validation.md). A5 chờ ý kiến pháp lý
- Cập nhật: 2026-10-28
- Nguồn quyết định:
  - [Báo cáo nghiên cứu emulator](../plans/reports/research-261027-1027-cloud-simulator-for-hands-on-labs.md)
  - [Brainstorm lớp 3D](../plans/reports/brainstorm-261027-1423-3d-architecture-visual-layer.md)
- Lộ trình: [roadmap.md](roadmap.md)

## 1. Bối cảnh và vấn đề

Học AWS trên tài khoản thật có ba trở ngại: tốn tiền, sợ để quên tài nguyên đang chạy, và không ai chấm bài. Các emulator mã nguồn mở như Floci, MiniStack và moto đã giải quyết được phần giả lập API. Tuy vậy, trải nghiệm học trên chúng vẫn kém ở hai điểm:

1. **Không có kịch bản và cũng không chấm bài.** Emulator chỉ trả về kết quả API. Người học không biết mình đã làm đúng yêu cầu hay chưa.
2. **Không nhìn thấy kiến trúc.** Portal đi kèm emulator, ví dụ của Floci, chỉ là danh sách tài nguyên. Người học không thấy được VPC chứa subnet nào, subnet nằm ở AZ nào, hay route nào trỏ tới IGW. Mà chính những quan hệ không gian này mới là thứ khó hình dung nhất khi học AWS.

## 2. Tầm nhìn

Sản phẩm là một phòng lab AWS chạy hoàn toàn trên máy cá nhân. Ở đó, người học dựng kiến trúc trên một **sơ đồ kiến trúc AWS dạng 3D**. Mỗi thao tác đều hiện ra **đúng lệnh `aws` CLI** tương ứng, lệnh đó chạy thật trên emulator, và hệ thống chấm bài dựa vào trạng thái thật mà emulator trả về.

## 3. Người dùng mục tiêu

| Persona | Mô tả | Nhu cầu chính |
|---|---|---|
| **Người tự học** (chính) | Kỹ sư đang học AWS để làm việc hoặc thi chứng chỉ CLF/SAA. Có máy macOS và Docker | Thực hành không tốn tiền, nhìn thấy kiến trúc, biết mình làm đúng hay sai |
| Người soạn lab (phụ, sau) | Người viết thêm bài lab mới | Định nghĩa lab bằng YAML, không phải sửa code frontend |

## 4. Mục tiêu và chỉ số thành công

| Mục tiêu | Chỉ số |
|---|---|
| Người học hiểu được cấu trúc kiến trúc | Hoàn thành Lab 6 (VPC) mà không cần mở tài liệu ngoài để biết subnet đang nằm ở đâu |
| Người học vẫn thành thạo CLI | 100% thao tác trên builder và chat đều hiện lệnh CLI tương đương; có chế độ luyện tập buộc người học tự gõ lệnh |
| Phản hồi tức thì | Từ lúc lệnh chạy xong đến lúc cảnh 3D cập nhật mất ≤ 2 giây |
| Chấm bài đáng tin | Không có lab nào báo "đạt" khi trạng thái trong emulator chưa đúng |
| Không bị khoá vào một backend | Đổi Floci sang MiniStack mà không phải sửa frontend hay định nghĩa lab |

## 5. Ngoài phạm vi

- Viết emulator mới, hoặc tự viết bộ đánh giá IAM policy.
- Giả lập lưu lượng mạng hay data plane của VPC, và mọi hoạt ảnh luồng dữ liệu không có thật.
- Nhiều người dùng, đăng nhập, hay triển khai lên cloud.
- GCP. Kiến trúc chỉ chừa sẵn interface `Provider` cho nó.
- Mô hình 3D tả thực hoặc pipeline asset (Blender/glTF). Hình khối được dựng bằng code.
- Thay thế AWS Console. Builder chỉ phục vụ các lab, không nhằm phủ toàn bộ API.

## 6. Nguyên tắc sản phẩm

1. **Emulator là nguồn sự thật.** Cảnh 3D chỉ vẽ tài nguyên đang tồn tại trong emulator, với ID thật. Ngoại lệ duy nhất là kiến trúc mục tiêu (ghost) của lab, và ghost luôn được đánh dấu rõ.
2. **Mọi thao tác đều quy về CLI.** Không có lời gọi ngầm nào mà người học không thấy.
3. **Không dùng dữ liệu giả.** Chỉ có hoạt ảnh cho lệnh API và sự kiện thật, ví dụ Lambda được gọi hay message vào SQS.
4. **Chấm bài dựa trên trạng thái.** Hệ thống chấm kết quả cuối cùng, không so sánh lệnh người học đã gõ.

## 7. Yêu cầu chức năng

Mức ưu tiên: **P0** là bắt buộc cho lát cắt đầu (Lab 6 + 7), **P1** là giai đoạn tiếp theo, **P2** là để sau.

### F1. Lab engine (`labctl`): P0

- F1.1 Định nghĩa lab bằng YAML, gồm các trường `id, provider, title, setup, tasks, checks, hints`. Trường mới cho lớp 3D là `target`, mô tả kiến trúc mục tiêu dùng để vẽ ghost.
- F1.2 Các lệnh `labctl up | env | start <lab> | check <lab> | reset <lab> | status`.
- F1.3 Checker là các hàm Python dùng boto3, chạy trên emulator. Mỗi check trả về `pass/fail`, kèm thông điệp và ID tài nguyên liên quan để cảnh 3D tô sáng.
- F1.4 Interface `Provider` có `client(service)`, `env()`, `reset(lab)`, `health()`. Bản đầu tiên là `AwsProvider`.
- F1.5 Tiến độ học lưu trong SQLite cục bộ.

### F2. Resource graph và đồng bộ trạng thái: P0

- F2.1 Collector gọi các API `describe/list` để chuyển trạng thái emulator thành **resource graph** gồm `nodes`, `contains` và `edges`.
- F2.2 `api-tap` là một proxy mỏng đặt trước emulator, ghi log từng lệnh API. Khi gặp lệnh ghi, nó báo collector chụp lại trạng thái ngay. Ngoài ra collector vẫn polling chậm khoảng 5 giây làm lưới an toàn.
- F2.3 Server đẩy resource graph và sự kiện tới trình duyệt qua WebSocket.
- F2.4 Phạm vi tài nguyên trong lát cắt đầu: VPC, Subnet, AZ, Internet Gateway, NAT Gateway, Route Table và route, Security Group và rule, Key Pair, EC2 Instance.

### F3. Cảnh 3D theo phong cách sơ đồ AWS: P0

- F3.1 Các nhóm Region, VPC, AZ và Subnet là khay trong suốt ép đùn (extruded), có màu và viền theo quy ước nhóm của sơ đồ kiến trúc AWS. Subnet public và private có màu khác nhau.
- F3.2 Mỗi dịch vụ là một khối có icon ở mặt trên. Icon dùng AWS Architecture Icons nếu điều khoản cho phép, nếu không thì dùng icon tự vẽ.
- F3.3 Bố cục được tính một cách xác định (deterministic) từ cây `contains`, nên cùng một trạng thái luôn cho ra cùng một bố cục.
- F3.4 Có xoay, zoom và pan camera. Bấm vào một node sẽ mở panel thuộc tính lấy từ emulator.
- F3.5 Cạnh nối thể hiện quan hệ cấu hình, ví dụ route `0.0.0.0/0` trỏ tới IGW hay SG gắn vào instance. Cạnh này không biểu diễn lưu lượng.
- F3.6 Có hoạt ảnh nhẹ khi node xuất hiện hoặc bị xoá, và hiệu ứng "lệnh API bay tới dịch vụ" lấy từ sự kiện của api-tap.
- F3.7 **Công thức hình ảnh.** Chi tiết và nguồn nằm trong [báo cáo kỹ thuật dựng cảnh](../plans/reports/researcher-261027-1616-3d-architecture-rendering-techniques.md#5-công-thức-đề-xuất-một-lựa-chọn).
  - **Thư viện:** dùng three 0.186.1 và ghim phiên bản này vì postprocessing yêu cầu three dưới 0.187. Kèm @react-three/fiber 9.x, @react-three/drei 10.x và @react-three/postprocessing 3.x, chạy trên WebGL2. Chưa dùng R3F v10 vì bản này đang ở alpha và mặc định dùng WebGPU.
  - **Camera:** camera trực giao (orthographic), đặt ở góc isometric (azimuth 45°, góc nâng khoảng 35°). Có nút đưa về 4 góc chuẩn và nút nhìn từ trên xuống. Khi chọn một node thì camera tự zoom vừa node đó (`fitToBox`).
  - **Ánh sáng:** đèn hemisphere, một đèn chính có bóng, một đèn phụ yếu, và môi trường dựng bằng `Lightformer` chỉ tính một lần.
  - **Vật liệu:** `MeshStandardMaterial` nhám. Khay dùng `opacity`, không dùng `transmission` vì `transmission` bắt render thêm một lượt mỗi khung hình. Nền sáng.
  - **Màu viền nhóm:** theo deck chính thức của AWS (bản 2026-07).

    | Nhóm | Màu | Kiểu nét |
    |---|---|---|
    | Region | `#00A4A6` | gạch chấm |
    | AZ | `#00A4A6` | gạch |
    | VPC | `#8C4FFF` | liền |
    | Subnet public | `#7AA116` | liền |
    | Subnet private | `#00A4A6` | liền |

  - **Hậu kỳ:** N8AO ở nửa độ phân giải (khay đặt `treatAsOpaque`), SMAA và ToneMapping là mức mặc định (đã đo ở [spike M0](../plans/reports/spike-261027-2248-m0-validation.md#5-hiệu-năng-cảnh-200-node)). `PerformanceMonitor` tự hạ xuống mức `lite` (chỉ SMAA và ToneMapping) khi FPS dưới 50. Không hạ xuống chế độ phẳng, vì chế độ đó mất khử răng cưa mà gần như không nhanh hơn.
  - **Nhãn:** dùng troika `Text` có viền chữ, với font `.woff` có đủ dấu tiếng Việt. Nhãn node tự ẩn khi zoom xa.
  - **Chuyển động:** react-spring cho node xuất hiện và biến mất. Xung sáng chạy dọc cạnh nối khi có sự kiện API thật. Hover và chọn được tô bằng `Outlines`.
  - **Render theo nhu cầu:** dùng `frameloop="demand"`, chỉ render khi cảnh thay đổi.
- F3.8 Icon dịch vụ được nạp từ một bộ icon có thể thay thế. Vì sản phẩm sẽ được thương mại hoá và chia sẻ công khai (đã chốt A8), **bộ icon mặc định là icon tự vẽ** và được phân phối cùng sản phẩm. AWS Architecture Icons chỉ được bật khi đã có xác nhận pháp lý. Khi bật, phải tuân theo điều khoản của AWS: không cắt, lật, xoay hay đổi màu icon.
- F3.9 **Hai chủ đề sáng và tối** (đã chốt A9). Mặc định theo cài đặt hệ thống, và người học có thể chuyển tay. Mỗi chủ đề có bảng token riêng gồm màu nền, màu và độ trong suốt của khay, màu nhãn, cường độ ánh sáng và môi trường. Mỗi chủ đề cũng có biến thể icon riêng. Màu viền nhóm vẫn giữ quy ước AWS ở F3.7, chỉ chỉnh độ sáng nếu cần để đủ tương phản trên nền tối.

### F4. Builder kéo-thả: P0 (ưu tiên số 1 của người dùng)

- F4.1 Palette tài nguyên được lọc theo lab đang mở.
- F4.2 Người học kéo tài nguyên vào một container hợp lệ (ví dụ Subnet vào AZ thuộc VPC), sau đó điền các thông số tối thiểu vào form như CIDR hay tên.
- F4.3 **Validate trước khi gửi lệnh**: CIDR phải nằm trong VPC và không được chồng lấn, container phải đúng loại. Mỗi lỗi kèm giải thích mang tính dạy học.
- F4.4 Panel lệnh hiện lệnh `aws ... --profile lab` đầy đủ. Lệnh **chỉ chạy khi người học bấm Run** (đã chốt A1), sau đó panel hiện nguyên văn stdout hoặc stderr.
- F4.5 Cảnh chỉ thay đổi sau khi collector xác nhận trạng thái mới, chứ không vẽ theo ý định thao tác.
- F4.6 Builder hỗ trợ cả các thao tác nối, ví dụ attach IGW, tạo route bằng cách kéo cạnh từ Route Table tới IGW, hay gắn SG vào instance.
- F4.7 Chế độ luyện tập: builder chỉ hiện lệnh, người học tự gõ ở terminal, và cảnh cập nhật qua api-tap. **P1**.

### F5. Chat gợi ý lệnh: P1

- F5.1 Người học mô tả bằng ngôn ngữ tự nhiên. Hệ thống trả về một chuỗi lệnh CLI, mỗi lệnh kèm giải thích ngắn.
- F5.2 Prompt gửi kèm resource graph hiện tại, nên lệnh gợi ý dùng ID thật.
- F5.3 Mọi lệnh gợi ý đều đi qua cùng bộ validate của F4.3 trước khi hiện ra. Lệnh không hợp lệ bị đánh dấu.
- F5.4 Không lệnh nào tự chạy. Người học phải xác nhận từng lệnh, hoặc xác nhận cả chuỗi một lần.
- F5.5 Chat gọi **LLM provider do người dùng tự cấu hình** (đã chốt A2). Cấu hình đọc từ biến môi trường hoặc file cấu hình cục bộ nằm ngoài git, gồm `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` và `LLM_API_FORMAT`. Hỗ trợ cả hai định dạng: `openai` (`/v1/chat/completions`) và `anthropic` (`/v1/messages`), do người dùng chọn khi cấu hình (đã chốt A7). API key không bao giờ được ghi vào repo, log hay giao diện.
- F5.7 Nếu chưa cấu hình provider, chat bị tắt và hiện hướng dẫn cấu hình. Builder và twin vẫn hoạt động bình thường.
- F5.6 Chat từ chối gợi ý ngoài phạm vi lab, và nói rõ khi emulator không hỗ trợ một API nào đó.

### F6. Digital twin và kiến trúc mục tiêu: P1

- F6.1 Tài nguyên mà người học tạo từ terminal, SDK hay Terraform đều hiện trong cảnh trong ≤ 2 giây.
- F6.2 Trường `target` của lab được vẽ thành ghost (mờ). Khi check liên quan qua, ghost chuyển sang đặc.
- F6.3 Panel check hiển thị trạng thái từng check. Bấm vào một check sẽ tô sáng các node liên quan.
- F6.4 `labctl reset` đưa cảnh về trạng thái sạch.

### F7. Mở rộng bộ lab: P2

- F7.1 Thêm palette và các kiểu hiển thị cho IAM (Lab 1–3, 8), S3 (Lab 4–5), DynamoDB (Lab 9), Lambda, SQS và CloudWatch (Lab 10), và CloudFormation (Lab 11).
- F7.2 Lab 3 dùng moto để có lỗi `AccessDenied` thật. Lớp 3D phải hiển thị được cả hai backend.

## 8. Yêu cầu phi chức năng

| Mã | Yêu cầu |
|---|---|
| NFR1 | Chạy cục bộ trên macOS, với Docker Desktop hoặc công cụ tương đương. Một lệnh khởi động toàn bộ: `labctl up` |
| NFR2 | Cảnh 3D đạt ≥ 50 fps với tối đa 200 node trên máy MacBook đời Apple Silicon |
| NFR3 | Độ trễ từ lúc lệnh chạy xong đến lúc cảnh cập nhật ≤ 2 giây (p95) |
| NFR4 | Frontend chỉ phụ thuộc vào resource graph, không gọi emulator trực tiếp |
| NFR5 | Phiên bản image của emulator được ghim cố định, và những chỗ emulator khác AWS thật được ghi lại trong ghi chú lab |
| NFR6 | Không lưu secret trong repo. Credential của emulator là credential giả. LLM API key lấy từ biến môi trường hoặc file cấu hình ngoài git |
| NFR7 | Server chỉ lắng nghe trên `127.0.0.1` |
| NFR8 | Hỗ trợ trình duyệt Chrome và Safari bản mới nhất |

## 9. Kiến trúc tổng quan

Chi tiết ở [báo cáo brainstorm, mục 3](../plans/reports/brainstorm-261027-1423-3d-architecture-visual-layer.md#3-kiến-trúc-đề-xuất).

| Thành phần | Công nghệ (đã chốt A3) | Trách nhiệm |
|---|---|---|
| Emulator | Floci (Docker), có thể thay bằng MiniStack, kèm moto cho lab IAM | API AWS |
| `api-tap` | Proxy Python | Chuyển tiếp request, ghi log lệnh API, phát sự kiện thay đổi |
| `lab-server` | Python, FastAPI | Collector, command-builder và validate, runner, chat, checker, WebSocket |
| `labctl` | Python CLI, dùng chung package với `lab-server` | Vòng đời lab, chấm bài, tiến độ |
| Web app | React, TypeScript, React Three Fiber | Cảnh 3D, builder, chat, panel lệnh và panel check |

## 10. Quyết định và giả định

Đã chốt ngày 2026-10-27:

| Mã | Quyết định |
|---|---|
| A1 | Builder hiện lệnh và **đợi người học bấm Run** |
| A2 | Chat dùng **LLM provider tự cấu hình** của người dùng (base URL + API key) |
| A3 | Frontend dùng **React/TS + React Three Fiber**, backend dùng **Python/FastAPI** |
| A7 | Chat hỗ trợ cả hai định dạng API, `openai` và `anthropic`, chọn qua `LLM_API_FORMAT` |
| A8 | Sản phẩm **sẽ được thương mại hoá và chia sẻ công khai**. Mọi phụ thuộc và asset phân phối kèm phải có giấy phép cho phép dùng thương mại |
| A9 | Có **cả chủ đề sáng và tối** |
| A10 | Tên sản phẩm là **Cloudy Labs**, slug `cloudy-labs` (dùng cho repo, package và thư mục). Tên cũ XLabs đã bỏ ngày 2026-10-28. Tên không chứa "AWS". Khi cần nói rõ phạm vi thì chỉ dùng "AWS" như một từ mô tả, ví dụ "Cloudy Labs — hands-on labs for AWS", và không dùng logo AWS |
| A11 | Mã nguồn mở, giấy phép **MIT** |
| A12 | Hình thức thương mại hoá là **bản chạy trên máy người dùng**. Không host thành dịch vụ, nên phần "Ngoài phạm vi" giữ nguyên |

Đã kiểm chứng qua [spike M0](../plans/reports/spike-261027-2248-m0-validation.md):

| Mã | Giả định | Kết quả |
|---|---|---|
| A4 | Floci trả về đủ thuộc tính VPC/EC2 qua các lệnh `describe-*` | **Đúng, kèm điều kiện.** Floci 2.3.0 trả đủ mọi trường của F2.4. `PrivateIpAddress` sai khi CIDR của lab trùng một mạng Docker trên máy, `PublicIpAddress` là `127.0.0.1` trên Docker Desktop, và `ReservationId` không ổn định. Collector ở M2 phải xử lý các điểm này (báo cáo mục 2). Floci là backend chính; MiniStack thiếu `NatGatewayAddresses` nên chỉ làm dự phòng |
| A6 | Công thức F3.7 đạt ≥ 50 fps với 200 node trên Safari ở DPR 2 | **Đúng.** Mức hậu kỳ đầy đủ có p95 17 ms trên Safari 26.6 và 9,3 ms trên Chrome 156 (Apple M1 Pro), ở cả hai chủ đề. Bài đo chạm trần vsync nên chưa đo được dư địa |

Còn chờ kiểm chứng:

| Mã | Giả định | Ảnh hưởng nếu sai |
|---|---|---|
| A5 | AWS Architecture Icons được phép dùng trong sản phẩm thương mại. Hiện AWS chưa có văn bản rõ ràng nên cần ý kiến pháp lý. Từ nay giả định này không còn chặn công việc, vì mặc định đã là icon tự vẽ | Giữ icon tự vẽ (F3.8) |

## 11. Rủi ro

1. **Floci còn non trẻ.** Có thể có những chỗ hoạt động khác AWS thật. Giảm thiểu: chỉ phụ thuộc vào wire protocol, ghim phiên bản, và ghi lại các sai khác.
2. **Phạm vi lớn** vì gồm ba chế độ cộng với 3D. Giảm thiểu: làm trọn lát cắt Lab 6 + 7 bằng builder trước, rồi chat và twin dùng lại cùng resource graph.
3. **Chat có thể gợi ý lệnh sai.** Giảm thiểu: đưa trạng thái thật vào prompt, validate lệnh, và bắt buộc người học xác nhận.
4. **Người học quen bấm chuột thay vì gõ lệnh.** Giảm thiểu: luôn hiện lệnh CLI, và có chế độ luyện tập ở F4.7.
5. **Rủi ro pháp lý khi thương mại hoá.** Có thể vướng thương hiệu AWS, giấy phép icon, hoặc giấy phép của thư viện. Giảm thiểu: icon tự vẽ làm mặc định, kiểm tra giấy phép của mọi phụ thuộc trước mỗi bản phát hành, và đặt tên theo câu hỏi Q4.

## 12. Câu hỏi mở

Q1–Q6 đã được trả lời, xem A7–A12. Hiện không còn câu hỏi mở nào chặn M0.

Ghi chú: trước bản phát hành công khai đầu tiên, nên tra cứu xem tên "Cloudy Labs" và slug `cloudy-labs` có trùng với nhãn hiệu, tên miền hoặc dự án đã có hay không.
