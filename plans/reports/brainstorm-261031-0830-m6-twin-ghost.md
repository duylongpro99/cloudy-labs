# Brainstorm M6: twin và ghost

- Ngày: 2026-10-31
- Phạm vi PRD: F6.1–F6.4. Mốc M6 trong [roadmap](../../docs/roadmap.md).
- Quyết định của người dùng (2026-10-31): check **chạy tự động** khi graph đổi; ghost **gắn với tài nguyên thật qua check**.

## Hiện trạng (đã kiểm trong code)

- **F6.1 gần như đã có từ M2.** Mọi lệnh ghi đi qua api-tap (`127.0.0.1:4566`, profile `lab`) phát sự kiện, hub collect sau debounce 0,15 giây; lệnh không đi qua tap thì poll mỗi 5 giây (`server/src/cloudy_labs/server/hub.py`). SDK và Terraform dùng cùng endpoint nên cũng đi qua tap, nhưng chưa có test nào chứng minh điều đó.
- **Check chỉ chạy qua CLI.** `Engine.check` chạy `run_checks` rồi ghi `Progress.record_checks`. Lab-server không có API check, web không có panel check.
- **Contract checker đã trả `resource_ids`** (`server/src/cloudy_labs/checks.py`), lưu trong `check_runs.resource_ids_json`. Đây là nguồn để gắn ghost và tô sáng node.
- **`Lab.target: dict[str, Any] = {}`** đã có chỗ trong schema nhưng chưa có hình dạng (`labs/schema.py`).
- **Layout web xác định từ cây node** (`web/src/scene/layout.ts`, `graph/graph-to-scene.ts`). Ghost muốn nằm đúng chỗ thì phải được trộn vào cây trước khi tính layout.
- **F6.4:** sau `labctl reset`, Floci khởi động lại, hub thấy `emulator-down` rồi graph rỗng; attempt mới làm `latest_results` rỗng. Chưa có test đầu-cuối nào cho cảnh sau reset.
- Lab 6 và 7 thật chưa có, nên M6 làm trên `fixture-lab-06` và `fixture-lab-07` như M3–M5.

## Contract

**Outcome.** Người học làm lab ở terminal (CLI, SDK hoặc Terraform qua profile `lab`) và thấy trên cảnh 3D:
- tài nguyên thật hiện ra trong ≤ 2 giây;
- kiến trúc mục tiêu của lab hiện dạng ghost mờ, đúng vị trí lồng nhau;
- khi check liên quan qua, ghost biến thành node thật được đánh dấu đạt;
- panel check hiện trạng thái từng check, bấm vào một check thì các node liên quan được tô sáng;
- `labctl reset` đưa cảnh về chỉ còn ghost và mọi check về chưa đạt.

**Constraints.**
- Emulator vẫn là nguồn sự thật (PRD nguyên tắc 1). Ghost luôn được đánh dấu rõ, không bao giờ trông giống tài nguyên thật.
- Gắn ghost chỉ dựa trên kết quả checker (`resource_ids`), không có ngôn ngữ so khớp thứ hai.
- Check chạy tự động sau mỗi lần graph đổi `content_hash`, có debounce, không chạy chồng. Checker chỉ gọi `Describe*`, nên không sinh sự kiện ghi trên api-tap và không tạo vòng lặp collect ↔ check.
- Chỉ ghi vào progress khi kết quả khác lần ghi trước của attempt hiện tại, để `labctl status` và `lab_summary` không bị spam. `labctl check` giữ nguyên hành vi.
- Không thêm dependency. Dùng lại websocket `/ws`, hub, `run_checks`, `Progress`.
- Builder và chat vẫn chạy như cũ; ghost hiện cả khi đang dùng builder và có công tắc ẩn/hiện.

**Non-goals.**
- Nội dung Lab 6 và 7 thật. Chỉ thêm `target` cho các lab fixture.
- Lab ngoài 6 và 7, palette mới (M7).
- Sửa checker để trả thêm thông tin ngoài `resource_ids`.
- Ghost cho cạnh (route, association) nếu khó; xem câu hỏi mở.
- Lưu trạng thái panel qua lần tải lại trang ngoài những gì server đã có.

**Acceptance criteria.**
1. Schema `target` được validate bằng pydantic: node có `id`, `kind`, `parent` (tuỳ chọn, trỏ node khác trong target), `label`, `checks` (trỏ check id có thật). Lab có `target` sai thì `labctl` báo lỗi rõ.
2. Với `fixture-lab-06` và `fixture-lab-07` sau `start`, cảnh hiện đủ ghost theo `target` và panel check hiện mọi check ở trạng thái chưa đạt.
3. Tạo tài nguyên bằng `aws --profile lab` ở terminal: node thật hiện trong ≤ 2 giây; khi check liên quan qua, ghost tương ứng biến mất và node thật được đánh dấu đạt, không cần gõ `labctl check`.
4. Có ít nhất một test chứng minh tài nguyên tạo bằng SDK (boto3 qua profile `lab`) cũng hiện trong ≤ 2 giây.
5. Bấm một check trong panel thì đúng các node trong `resource_ids` của nó, cùng các ghost khai báo check đó, được tô sáng; bấm lại thì bỏ.
6. `labctl reset` trong lúc web đang mở: cảnh chỉ còn ghost, mọi check về chưa đạt, không cần tải lại trang.
7. Hoàn thành fixture bằng terminal thì `labctl check` đạt và cảnh không còn ghost nào.
8. Có unit test cho phép gắn ghost (thuần, deterministic) và cho việc chỉ ghi progress khi kết quả đổi. Lab không có `target` vẫn chạy như trước.

## Phương án đã so sánh

| Phương án | Giả định chịu lực | Hỏng đầu tiên khi |
|---|---|---|
| **Gắn qua check (chọn)** | Checker trả đủ `resource_ids` cho mọi tài nguyên mà check xác nhận | Một checker trả thiếu id, hoặc một check trả nhiều id cùng kind mà ghost cần phân biệt (ví dụ subnet AZ a và AZ b) |
| So khớp thuộc tính | Tác giả lab viết điều kiện khớp đồng bộ với checker | Điều kiện khớp và checker lệch nhau, ghost đặc trong khi check vẫn trượt |
| Cảnh mục tiêu riêng | Người học chấp nhận nhìn hai khung | Không đạt F6.2 "ghost chuyển sang đặc" tại chỗ |

Trade-off của phương án chọn: trước khi check qua, cảnh có thể hiện cả ghost lẫn tài nguyên thật chưa đúng (ví dụ đã có 3 subnet nhưng check cần 4). Điều đó chấp nhận được và còn có ích, vì nó cho người học thấy phần nào chưa đúng.

Better approaches: none. Hướng được chọn là hướng dùng lại contract checker có sẵn (`CheckResult.resource_ids`) nên rẻ nhất để bỏ nếu sai.

## Hướng thiết kế đề xuất cho plan

- **Hình dạng `target`** (trong `lab.yaml`):
  ```yaml
  target:
    nodes:
      - {id: vpc, kind: vpc, label: VPC 10.66.0.0/16, checks: [vpc-exists]}
      - {id: az-1, kind: az, parent: vpc, label: AZ 1}
      - {id: public-1, kind: subnet-public, parent: az-1, label: Public 1, checks: [subnets-two-azs]}
  ```
- **Gắn ghost** là hàm thuần ở server: đầu vào là `target`, kết quả check mới nhất và graph; đầu ra là danh sách ghost còn lại kèm cha đã giải (ghost cha hoặc id thật đã gắn). Ghost được gắn khi mọi check của nó qua; id thật lấy từ hợp `resource_ids` của các check đó, lọc theo `kind` trong graph, gán theo thứ tự khai báo ghost và thứ tự id đã sắp xếp. Ghost không có check (như `az`) được gắn theo con của nó.
- **Luồng:** hub publish graph mới thì một task chạy check (debounce, một task một lúc), so với kết quả trước, ghi progress khi đổi, rồi broadcast message `twin` `{attempt, checks: [...], ghosts: [...]}` trên `/ws`. Client mới kết nối nhận ngay message `twin` hiện tại.
- **Web:** trộn ghost vào cây trước `computeLayout`; object ghost dùng vật liệu mờ và viền nét đứt, có nhãn "mục tiêu"; node thật nằm trong `resource_ids` của check đạt có dấu đạt; thêm panel check có tô sáng khi bấm; thêm công tắc ẩn/hiện ghost.

## Rủi ro

- Checker fixture hiện có trả `resource_ids` chưa chắc đủ cho mọi ghost. Plan phải rà từng checker của `fixture-lab-06` và `fixture-lab-07` và bổ sung id còn thiếu (đây là sửa fixture, không đổi contract).
- Nút `az` trong graph: cần xác minh cách collector đặt id cho AZ để ghost con của AZ được gắn đúng cha.
- Chạy check sau mỗi lần graph đổi tốn vài lệnh `Describe*` mỗi lần. Cần đo trên fixture và đặt debounce sao cho tổng độ trễ đến lúc ghost đặc vẫn hợp lý (đề xuất ≤ 3 giây sau khi tài nguyên hiện).

## Câu hỏi mở

- Có cần ghost cho cạnh (route, association, SG gắn vào instance) trong M6 không, hay chỉ ghost cho node? Đề xuất: chỉ node trong M6, cạnh để sau nếu thiếu.
