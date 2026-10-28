# Nghiên cứu: kỹ thuật dựng cảnh "sơ đồ kiến trúc AWS 3D" cho F3

Ngày: 2026-10-27. Ngữ cảnh: `docs/product-requirements.md` mục F3 (F3.1 đến F3.6). Ký hiệu: **[KC]** là đã kiểm chứng trực tiếp từ nguồn (trang, mã nguồn, gói tải về), **[SL]** là suy luận của người nghiên cứu. Mọi URL truy cập ngày 2026-10-27.

## Kết luận ngắn

Nên dùng camera **trực giao (orthographic) góc isometric** điều khiển bằng `CameraControls`, ánh sáng **hemisphere + một đèn key có bóng + Environment dựng bằng Lightformer**, vật liệu **MeshStandardMaterial nhám, khay bán trong suốt bằng `opacity` (không dùng `transmission`)**, viền khay đúng màu nhóm AWS, hậu kỳ chỉ gồm **N8AO half-res + SMAA + ToneMapping**, nhãn **troika SDF** có viền chữ và ẩn theo mức zoom, chuyển động bằng **react-spring**. Giữ trên R3F v9 với `WebGLRenderer`, vì R3F v10 (alpha) đổi mặc định sang WebGPURenderer trong khi `postprocessing` vẫn chỉ chạy trên WebGL. Rủi ro chính là **điều khoản icon AWS chưa rõ cho sản phẩm thương mại**, xem mục 2.

## 1. Prior art: các công cụ sơ đồ cloud dạng isometric/3D

| Công cụ | Cách dựng cảnh | Điều làm nó dễ đọc |
|---|---|---|
| Cloudcraft (Datadog) | Mỗi component có màu riêng cho chế độ `isometric` và `2d`, kèm `accentColor`; vị trí theo lưới `mapPos` [KC][1]. Vùng (Area) là đa giác phẳng có màu nền, màu viền, tuỳ chọn "shadow" để tăng tương phản, thứ tự chồng qua Raise/Lower; không có độ cao [KC][2]. Subnet có `shape` (`dynamic`/`rectangular`) và `padding` mặc định 1.5 [KC][3]. Nhãn chữ có thể chiếu 3D hoặc 2D, nằm phẳng (flat) hoặc đứng (standing), xoay 4 hướng, có "outline" để tăng tương phản [KC][4]. | Góc nhìn cố định một góc, lưới nền, khối phẳng màu đơn với ba mặt được tô sáng khác nhau, nhãn nằm phẳng trên mặt đất [SL, mô tả theo ảnh chụp sản phẩm quen thuộc]. Người dùng than phiền "chỉ dùng được một góc nhìn" và "isometric đẹp nhưng sơ đồ phẳng dễ đọc hơn" [KC][5]. |
| Isoflow / FossFLOW | Ứng dụng React vẽ sơ đồ isometric trong trình duyệt, lưu JSON; FossFLOW là bản fork mã nguồn mở của thư viện Isoflow [KC][6][7]. Giấy phép giữa các bản fork không thống nhất (MIT và Unlicense) [KC][7]. | Phép chiếu isometric 2D thuần (không có ánh sáng thật), icon đặt trên ô lưới, nhãn là khối HTML nổi phía trên [SL]. |
| AWS VPC Resource map | Sơ đồ 2D trong console: VPC, subnet, route table, IGW, NAT, endpoint; subnet public màu xanh lá, private màu xanh dương [KC][8]. | Quan hệ cấu hình hiển thị dạng cột trái sang phải, không có 3D [KC][8]. |

Bài học rút ra [SL]: (a) **nhãn nằm phẳng có viền** và **màu theo vai trò** là hai yếu tố giúp Cloudcraft dễ đọc; (b) lời phàn nàn về "một góc nhìn" ủng hộ việc cho xoay nhưng **bám (snap) về 4 góc isometric**; (c) phản hồi "2D dễ đọc hơn" cho thấy nên có chế độ nhìn từ trên xuống (top-down) bằng cùng camera trực giao. Không tìm thấy công cụ three.js/R3F mã nguồn mở nào dựng VPC/subnet 3D đáng kể để tham khảo mã.

## 2. AWS Architecture Icons: nơi tải, điều khoản, màu nhóm

**Trang tải chính thức**: https://aws.amazon.com/architecture/icons/ . Gói hiện tại là `Icon-package_07312026.zip` (khoảng 14 MB, có SVG và PNG ở các cỡ 16/32/48/64) và `Microsoft-PPTx-toolkits_07312026.zip`, phát hành "Release 24-2026.07.31", cập nhật theo quý [KC][9][10].

**Điều khoản, trích nguyên văn**:
- Trang tải: "We allow customers and partners to use these toolkits and assets to create architecture diagrams. ... You can also put icons in materials like whitepapers, presentations, data sheets, and posters." [KC][9]
- Deck PPTx, slide 5: "Customers and partners can use AWS icons to create architecture diagrams. The icons are basic in design so that you can incorporate them directly into your whitepapers, presentations, datasheets, posters, or any technical material that you want." [KC][10]
- Slide 15: "DO: Use icons at their predefined size, color and format in diagrams. ... DON'T: Crop service icons. Flip or rotate icons. Change icon shapes." [KC][10]
- Slide 14: "DON'T: Create groups with nonapproved AWS icon(s). Resize group icons." [KC][10]
- Gói zip **không có tệp LICENSE/README** nào [KC, đã liệt kê toàn bộ gói]. AWS Trademark Guidelines không nhắc riêng tới architecture icons, nhưng có các điều chung: "You will not display the AWS Marks in any manner that implies sponsorship or endorsement by AWS" và "You will not incorporate AWS Marks into the names of your organization, products, or services" [KC][11].

**Đánh giá**:
- Công cụ học cá nhân, phi thương mại: rủi ro thấp. Một ứng dụng sinh sơ đồ kiến trúc nằm trong phạm vi "create architecture diagrams" [SL]. Cần dán icon phẳng lên mặt trên khối, giữ nguyên tỉ lệ và màu, không cắt, không xoay lệch so với khối. Phép chiếu phối cảnh của camera không phải là "change icon shapes" [SL].
- Công cụ học thương mại: **chưa rõ**. Điều khoản cho phép "customers and partners" dùng để tạo sơ đồ, nhưng không nói gì về việc đóng gói icon vào một sản phẩm phần mềm bán ra. Thực tế ngành là draw.io (Apache-2.0) phân phối bộ hình AWS4 và Cloudcraft dùng biểu tượng AWS [KC][12][1], song đây là tiền lệ chứ không phải giấy phép [SL]. Khuyến nghị: giữ icon tự vẽ làm phương án dự phòng sau một cờ cấu hình, không đưa "AWS" vào tên sản phẩm, ghi rõ không liên kết với AWS, và xin xác nhận bằng văn bản hoặc ý kiến pháp lý trước khi bán [SL].

**Màu và kiểu nhóm chính thức** (deck PPTx slide 25, đọc trực tiếp từ XML; độ dày nét 15875 EMU, tức 1.25pt) [KC][10]:

| Nhóm | Màu viền | Kiểu nét | Nền (draw.io AWS4) |
|---|---|---|---|
| AWS Cloud | `#232F3E` | liền | không [KC][12] |
| Region | `#00A4A6` | gạch chấm (`sysDash`) | không |
| Availability Zone | `#00A4A6` | gạch (`dash`) | không (draw.io dùng viền `#147EBA`, khác deck) |
| VPC | `#8C4FFF` | liền | không |
| Public subnet | `#7AA116` | liền | `#F2F6E8`, chữ `#248814` [KC][12] |
| Private subnet | `#00A4A6` | liền | `#E6F6F7`, chữ `#147EBA` [KC][12] |
| Security group | `#DD344C` | liền | không |
| Auto Scaling group | `#ED7100` | gạch | không |

Màu icon nhóm SVG khớp với bảng trên (Region và Private subnet `#00A4A6`, Public subnet `#7AA116`, VPC `#8C4FFF`) [KC, đọc từ SVG trong gói]. Khi có xung đột, lấy deck PPTx làm chuẩn. Quy tắc nhãn: "All label text should be 12pt Arial", tên dịch vụ tối đa hai dòng, không ngắt giữa từ (slide 17). Riêng ca dùng cho đào tạo (slide 13): nền trắng, chữ đen, "All colors for icons have been accessibility tested and should not be altered" [KC][10]. Điều này phù hợp với một công cụ học tập và ủng hộ nền sáng.

## 3. Hệ sinh thái React Three Fiber (phiên bản ổn định tại 2026-10-27)

| Gói | `latest` | Ghi chú tương thích |
|---|---|---|
| `three` | **0.186.1** | `postprocessing` 6.39.5 yêu cầu three ≥0.168 và **<0.187**, nên phải ghim three [KC][13] |
| `@react-three/fiber` | **9.8.2** | peer `react >=19 <19.4`; React mới nhất là 19.3.1. Bản v10.0.0-alpha.6 đặt WebGPURenderer làm mặc định [KC][14] |
| `@react-three/drei` | **10.7.9** | kèm camera-controls ^3.1, troika-three-text ^0.52.4, three-mesh-bvh ^0.8.3, maath ^0.10.8 [KC, npm] |
| `@react-three/postprocessing` | **3.2.2** | peer postprocessing ^6.36, fiber ≥9.7; đã kèm `n8ao` ^2.0 [KC, npm] |
| `postprocessing` | **6.39.5** | v7 vẫn ở beta/alpha [KC, npm dist-tags] |
| `@react-spring/three` 10.1.2, `maath` 0.10.8, `troika-three-text` 0.52.5, `three-mesh-bvh` 0.9.16 | | [KC, npm] |

**Các helper drei phù hợp**:
- `OrthographicCamera` kết hợp `CameraControls`: camera-controls hỗ trợ cả camera Perspective lẫn Orthographic; với ortho thì dùng `ZOOM` thay cho `DOLLY`. Có `smoothTime` (mặc định 0.25 s), giới hạn `min/maxPolarAngle` và `min/maxAzimuthAngle` [KC][15]. drei 10.5 đã nâng lên camera-controls v3 [KC][16]. Dùng `fitToBox`/`setLookAt` để bay camera tới node được chọn [SL].
- `RoundedBox` cho thân khối dịch vụ. Nên tạo một geometry dùng chung rồi instancing [SL].
- `Text` (troika, SDF, khử răng cưa) hỗ trợ `outlineWidth`/`outlineColor`/`outlineBlur`. Font **.ttf/.otf/.woff, không hỗ trợ .woff2**; glyph được tạo trong web worker [KC][17][18]. Truyền prop `characters` để tải trước glyph, tránh nháy [KC][17]. Troika còn có `BatchedText` (gộp nhiều nhãn, đã sửa lỗi riêng cho Safari) nhưng drei chưa bọc sẵn [KC, CHANGELOG 0.52.x]. `Text3D` (chữ khối) tốn nhiều đỉnh và không cần cho ca này [SL]. `Html` chỉ nên dùng cho tooltip hoặc panel của node đang chọn, vì mỗi phần tử là một nút DOM được cập nhật vị trí mỗi khung hình [SL].
- `Decal` không cần: icon dán lên **mặt phẳng trên cùng**, nên một plane đặt lệch lên 0.001 rẻ hơn [SL].
- `Outlines`: viền theo phương pháp inverted hull, hỗ trợ `mesh`, `skinnedMesh`, `instancedMesh`, có tuỳ chọn `screenspace` [KC][19]. Rẻ hơn hiệu ứng Outline dạng hậu kỳ; nên dùng cho hover/chọn. `Edges` hợp cho viền khay [SL].
- `ContactShadows`: "a rather expensive effect"; đặt `frames={1}` khi cảnh tĩnh [KC][20]. `AccumulativeShadows` (kèm `RandomizedLight`): "zero performance impact after all frames have accumulated", nhưng chỉ đổ bóng lên **một mặt phẳng hướng Y** [KC][21], không đổ được lên các khay lồng nhau [SL]. `SoftShadows` (PCSS) can thiệp shader bóng, tốn chi phí mỗi pixel [SL].
- `Environment` kết hợp `Lightformer`: dựng env map ngay trong cảnh, không cần tải HDR (ứng dụng chạy local), đặt `frames={1}` [SL].
- `Instances`/`Merged`: một draw call nhưng có chi phí CPU cho mỗi instance khai báo; nếu cần CPU ≈ 0 thì dùng `InstancedMesh` thô [KC][22]. Với 200 node thì `Instances` là đủ [SL].
- `Bvh`: tăng tốc raycast cho hover/click [KC][23].

**Hậu kỳ và chi phí** (Apple Silicon/Safari chưa có số đo công khai, các ước lượng đều là [SL]):
- **N8AO**: `halfRes` nhanh hơn 2 đến 4 lần, upsample tốn cố định khoảng 1 ms; mức chất lượng mặc định là Medium. Cần dùng SMAA vì "hardware antialiasing does NOT work with ambient occlusion". **Vật thể trong suốt bị render hai lần**; có thể đặt `userData.treatAsOpaque = true` để bỏ qua [KC][24]. Với các khay trong suốt phủ gần hết màn hình, đây là cái bẫy hiệu năng lớn nhất.
- **SMAA**: rẻ, chọn thay MSAA khi có AO [KC][24].
- **ToneMapping**: bắt buộc nếu render qua composer. Chế độ `NEUTRAL` giữ màu thương hiệu (như tím VPC, xanh subnet) ít bị lệch sắc hơn ACES hay AgX [SL].
- **Outline** (hậu kỳ): thêm các pass mask và cạnh. Dùng drei `Outlines` thay thế [SL].
- **Bloom** (`mipmapBlur`, `luminanceThreshold` khoảng 1): chỉ nên dùng cho hạt xung (pulse) có emissive >1. Bloom tốn thêm một chuỗi mip blur toàn màn hình, nên để tuỳ chọn [SL].
- **SSAO** cổ điển: kém hơn N8AO về chất lượng trên mỗi ms, không nên dùng [SL].

**Lưu ý Safari, WebGL2 và WebGPU năm 2026**: Safari 26 (tháng 9/2025) đã có WebGPU [KC][25]. Tuy vậy R3F v10 mới ở alpha và thư viện `postprocessing` 6.x chỉ chạy trên WebGLRenderer [KC][13][14]. Vì vậy nên ở lại **R3F 9 + WebGL2**, cả Chrome và Safari đều ổn định. Safari chạy WebGL qua ANGLE/Metal; MSAA trên render target float và bộ đệm có độ phân giải cao (DPR 2) là nguồn tốn fill-rate chính, nên giới hạn `dpr={[1, 2]}` và hạ DPR khi FPS tụt [SL].

## 4. Kỹ thuật làm cảnh diorama trông đẹp, kèm rào chắn hiệu năng

- **Ánh sáng**: `hemisphereLight` (trời trắng, đất xám ấm, cường độ khoảng 0.6) để mặt bên không bị đen. Một `directionalLight` key từ phía trên-trái-trước, có bóng; frustum bóng ôm sát bounding box cảnh; `shadow-mapSize` 2048; `shadowMap.autoUpdate=false` và chỉ đặt `needsUpdate` khi bố cục đổi. Một đèn fill yếu không bóng ở phía đối diện. Rim light là tuỳ chọn, ít giá trị với camera trực giao nhìn từ trên [SL]. Ba mặt khối có độ sáng khác nhau rõ rệt là tín hiệu chiều sâu chính của phong cách isometric [SL].
- **Vật liệu**: `MeshStandardMaterial` với roughness 0.6 đến 0.8, metalness 0. Không dùng `MeshPhysicalMaterial` cho khay: tài liệu three.js ghi rõ nó "has a higher performance cost, per pixel" [KC][26], và khi `transmission > 0` thì WebGLRenderer **render lại toàn bộ vật thể đục vào một render target HalfFloat có MSAA (≥4 mẫu) và tạo mipmap mỗi khung hình** (`renderTransmissionPass`) [KC][27]. Khay nên dùng `transparent`, `opacity` khoảng 0.08 đến 0.18, `depthWrite={false}`, phần đáy đậm hơn, cộng viền nét liền hoặc gạch đúng màu nhóm. Đặt `renderOrder` theo độ sâu lồng nhau (Region < VPC < AZ < Subnet) để tránh lỗi sắp xếp độ trong suốt [SL].
- **Bóng và AO**: một bóng directional (đổ lên cả các khay) cộng N8AO half-res, với `treatAsOpaque` trên khay, đủ tạo cảm giác "đặt lên" [SL]. Nếu hiệu năng không đạt, bỏ N8AO và giả AO bằng một quad mờ dạng blob shadow dưới mỗi khối, dùng chung texture và instancing [SL].
- **Bảng màu tiết chế**: nền trắng hoặc xám rất nhạt (đúng hướng dẫn đào tạo của AWS [KC][10]). Màu chỉ dành cho viền nhóm và icon. Thân khối trắng ngà, mặt trên mang một dải màu theo danh mục dịch vụ. Cạnh quan hệ màu xám đậm, chỉ đổi màu khi được chọn [SL].
- **Nhãn dễ đọc**: nhãn nhóm nằm **phẳng** ở góc trước-trái của khay, giống vị trí nhãn nhóm 2D của AWS. Nhãn node là `Billboard` + `Text` có `outlineWidth` khoảng 8% màu nền, đặt `depthOffset` hoặc `renderOrder` cao để không bị khay che. Ẩn nhãn node khi `camera.zoom` nhỏ hơn ngưỡng, nhưng luôn hiện nhãn nhóm. Cần font .woff có đủ dấu tiếng Việt (ví dụ Inter, Be Vietnam Pro) vì troika không đọc .woff2 [KC][18]/[SL].
- **Chuyển động**: `@react-spring/three` `useTransition` cho phép chạy hoạt ảnh xuất hiện/biến mất **trước khi unmount**: scale Y từ 0 lên 1 bám đáy khay, opacity, dùng spring cấu hình `{tension: 220, friction: 24}` [SL]. `maath/easing.damp3` hợp cho camera và chuyển động liên tục [SL].
- **Hover/chọn**: con trỏ đổi kiểu, tăng emissive nhẹ, nhấc khối 0.05 đơn vị; khi chọn thì thêm `Outlines` (screenspace) và làm mờ các node không liên quan về opacity khoảng 0.35 [SL].
- **Xung sự kiện API (F3.6)**: mỗi sự kiện từ api-tap sinh một hạt (instanced sphere) chạy dọc `QuadraticBezierCurve3` từ một "điểm client" ngoài Region tới node trong khoảng 600 ms, dùng `getPointAt(t)` với easing, rồi nháy emissive ở node đích. Gom tối đa N hạt đồng thời và tái sử dụng trong pool [SL].
- **Rào chắn hiệu năng cho khoảng 200 node** (R3F khuyến nghị tối đa khoảng 1000 draw call, lý tưởng "a few hundred or less"; nên dùng `frameloop="demand"` + `invalidate()`, instancing, dùng chung geometry và vật liệu, `PerformanceMonitor`/`regress`, DPR thích ứng [KC][28]):
  - Thân khối: 1 `InstancedMesh`. Icon: 1 instanced plane cho mỗi loại dịch vụ (khoảng 20 draw call), hoặc atlas cộng thuộc tính UV cho mỗi instance để còn 1 draw call [SL].
  - Khay: tối đa khoảng 60 mesh, mỗi khay gồm mặt và viền (khoảng 120 draw call); dùng chung vật liệu theo loại nhóm [SL].
  - Cạnh: gộp toàn bộ vào **một** `LineSegments2` (fat line). Không nên dùng một `<Line>` cho mỗi cạnh [SL].
  - Nhãn: 200 `Text` là khoảng 200 draw call; chuyển sang troika `BatchedText` nếu vượt ngân sách [SL].
  - Mục tiêu dưới 400 draw call. Theo dõi bằng `renderer.info.render.calls` và stats-gl có sẵn trong drei [SL].
  - `frameloop="demand"`: render chỉ khi camera di chuyển, có spring/xung đang chạy, hoặc có sự kiện. react-spring tự gọi invalidate trong R3F [SL, cần thử]. Phải gọi invalidate thủ công trong `onChange` của CameraControls và khi hạt xung còn sống [SL].

## 5. Công thức đề xuất (một lựa chọn)

| Lớp | Lựa chọn |
|---|---|
| Renderer | R3F 9.8.2 + three 0.186.1 (ghim) + WebGL2, `dpr={[1,2]}`, `frameloop="demand"`, `gl={{antialias:false}}` (SMAA lo khử răng cưa) |
| Camera | `OrthographicCamera` + `CameraControls`; azimuth 45°, góc nâng khoảng 35° (isometric). Cho xoay tự do nhưng có nút snap về 4 góc và nút top-down; giới hạn polar từ 15° đến 80°; `fitToBox` khi chọn node |
| Ánh sáng | hemisphere + key directional có bóng (cập nhật theo sự kiện) + fill yếu + `Environment` gồm 2 hoặc 3 `Lightformer`, `frames={1}` |
| Vật liệu | Standard nhám; khay dùng `opacity` (không dùng transmission) + viền và nét gạch theo bảng màu AWS ở mục 2; nền sáng |
| Hậu kỳ | `EffectComposer multisampling={0}` → `N8AO halfRes quality="medium"` (khay đặt `treatAsOpaque`) → `SMAA` → `ToneMapping` (Neutral). Bloom tắt mặc định; `PerformanceMonitor` tắt N8AO khi FPS < 50 |
| Nhãn | troika `Text` có viền chữ; nhãn nhóm nằm phẳng, nhãn node billboard ẩn theo zoom; `Html` chỉ cho node đang chọn |
| Chuyển động | react-spring `useTransition` cho node vào/ra; hạt xung instanced trên đường Bezier; `Outlines` cho hover/chọn |

**Lý do**: camera trực giao cho kích thước nhất quán và nhãn dễ đọc như sơ đồ AWS 2D, đồng thời vẫn đáp ứng yêu cầu xoay/zoom/pan của F3.4. Mọi hiệu ứng tốn kém đều chỉ chạy khi cảnh thay đổi, nhờ `demand`, bóng cập nhật theo sự kiện và env bake một lần. Tất cả là thư viện pmndrs chính dòng, đã ổn định nhiều năm, không phải bản alpha.

**Rủi ro chính**: (1) điều khoản icon cho bản thương mại chưa rõ, xem mục 2; (2) độ trong suốt nhiều lớp lồng nhau gây lỗi sắp xếp và nhân đôi chi phí N8AO trên Safari ở DPR 2. Giảm thiểu bằng `renderOrder` cố định, `treatAsOpaque`, và đo sớm trên Safari bằng cảnh mẫu 200 node trước khi chốt hậu kỳ.

## Trade-off đã cân nhắc

| Phương án | Đẹp | Chi phí GPU | Độ phức tạp | Kết luận |
|---|---|---|---|---|
| Ortho + Standard + N8AO half-res (đề xuất) | Cao | Trung bình | Thấp | Chọn |
| Perspective + Physical transmission + SoftShadows | Rất cao (kính) | Cao (thêm pass scene, MSAA RT) | Trung bình | Loại vì ngân sách 50 fps trên Safari |
| Phẳng hoàn toàn (không AO/bóng, chỉ đổ màu theo mặt) | Trung bình | Rất thấp | Thấp nhất | Phương án dự phòng khi `PerformanceMonitor` hạ cấp |
| WebGPURenderer + TSL (R3F v10) | Cao | Tốt về lâu dài | Cao, API alpha | Chờ R3F v10 ổn định |

## Giới hạn của nghiên cứu

- Chưa đo FPS thực tế trên Apple Silicon/Safari. Mọi con số chi phí hậu kỳ là ước lượng [SL]; cần một bản spike đo `renderer.info` và thời gian khung hình.
- Không xem được bên trong mã render của Cloudcraft (là sản phẩm đóng). Phần mô tả hình ảnh dựa trên tài liệu component và hiểu biết chung.
- Chưa có văn bản pháp lý chính thức nào của AWS về việc nhúng icon vào phần mềm thương mại.

## Câu hỏi còn mở

1. Sản phẩm có dự định thương mại hoá không? Nếu có, cần xin xác nhận từ AWS hoặc ý kiến pháp lý trước khi dùng icon chính thức.
2. Có cần chế độ nền tối không? Deck AWS có bộ icon riêng cho nền tối, và bảng màu khay phải tinh chỉnh lại.
3. Ngưỡng zoom để ẩn nhãn node, và số hạt xung đồng thời tối đa, cần chốt qua thử nghiệm UX.

## Nguồn

1. https://docs.datadoghq.com/cloudcraft/components-aws/cloudfront
2. https://docs.datadoghq.com/cloudcraft/components-common/area/
3. https://docs.datadoghq.com/cloudcraft/components-aws/subnet/
4. https://docs.datadoghq.com/cloudcraft/components-common/text-label
5. https://aws.amazon.com/marketplace/reviews/reviews-list/B08KBV31ZM?page=20
6. https://ostechnix.com/create-isometric-diagrams-fossflow/
7. https://github.com/akx/FossFLOW (fork của stan-smith/FossFLOW); https://github.com/TimKieu/isoflow
8. https://docs.aws.amazon.com/vpc/latest/userguide/view-vpc-resource-map.html
9. https://aws.amazon.com/architecture/icons/
10. Microsoft-PPTx-toolkits_07312026.zip, tệp `AWS-Architecture-Icons-Deck_For-Light-BG_07312026.pptx`, slide 5, 13, 14, 15, 17, 25 (tải từ [9])
11. https://aws.amazon.com/trademark-guidelines/
12. https://github.com/jgraph/drawio/blob/dev/src/main/webapp/js/diagramly/sidebar/Sidebar-AWS4.js
13. https://github.com/pmndrs/postprocessing/releases (v6.39.5)
14. https://github.com/pmndrs/react-three-fiber/releases (v9.8.0, v10.0.0-alpha.6)
15. https://github.com/yomotsu/camera-controls (README)
16. https://drei.docs.pmnd.rs/controls/camera-controls
17. https://drei.docs.pmnd.rs/abstractions/text
18. https://github.com/protectwise/troika/tree/main/packages/troika-three-text (README)
19. https://drei.docs.pmnd.rs/abstractions/outlines
20. https://drei.docs.pmnd.rs/staging/contact-shadows
21. https://drei.docs.pmnd.rs/staging/accumulative-shadows
22. https://drei.docs.pmnd.rs/performances/instances
23. https://pmndrs.github.io/drei/performances/bvh
24. https://github.com/N8python/n8ao (README)
25. https://en.wikipedia.org/wiki/WebGPU; https://app.cinevva.com/guides/webgpu-vs-webgl-games
26. https://threejs.org/docs/pages/MeshPhysicalMaterial.html
27. https://github.com/mrdoob/three.js/blob/r186/src/renderers/WebGLRenderer.js (`renderTransmissionPass`, khoảng dòng 2002 đến 2025)
28. https://r3f.docs.pmnd.rs/advanced/scaling-performance
