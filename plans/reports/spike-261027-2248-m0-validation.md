# Báo cáo spike M0: emulator, hiệu năng cảnh 3D và giấy phép

- Ngày: 2026-10-27
- Plan: [m0-spike-emulator-and-render-validation](../261027-1353-m0-spike-emulator-and-render-validation/plan.md)
- Máy đo: Apple M1 Pro, 16 GB, macOS (Darwin 25.6), Docker 29.7.2, Chrome 156, Safari 26.6.2, màn hình tích hợp 120 Hz
- Ghi chú chi tiết: [emulator](../261027-1353-m0-spike-emulator-and-render-validation/notes/emulator-notes.md), [render](../261027-1353-m0-spike-emulator-and-render-validation/notes/render-notes.md), [giấy phép](../261027-1353-m0-spike-emulator-and-render-validation/notes/license-summary.md), [checklist Safari](../261027-1353-m0-spike-emulator-and-render-validation/notes/safari-checklist.md)

## 1. Kết luận ngắn

| Giả định | Kết luận | Bằng chứng |
|---|---|---|
| **A4.** Floci trả đủ thuộc tính VPC/EC2 | **Đúng, kèm 5 điểm collector phải xử lý.** Trên máy đo, Floci có 38/39 trường đúng. Trường còn lại, `PrivateIpAddress`, sai vì CIDR của lab trùng một mạng Docker trên máy; với CIDR không trùng, Floci báo đúng IP | [`field-matrix.md`](../../spikes/m0-emulators/out/field-matrix.md), [`side-test-non-overlapping-cidr.txt`](../../spikes/m0-emulators/out/floci/side-test-non-overlapping-cidr.txt) |
| **A6.** F3.7 đạt ≥ 50 fps với 200 node trên Safari ở DPR 2 | **Đúng.** Mức `full` có p95 17 ms (60 fps, trần vsync của Safari) ở cả hai chủ đề | [`summary.md`](../../spikes/m0-render/results/summary.md) |
| **A8.** Mọi phụ thuộc cho phép phân phối thương mại cùng sản phẩm MIT | **Đúng.** Có 0 gói thuộc nhóm "Chặn" hoặc không rõ giấy phép, và 3 gói MPL-2.0 dùng không sửa đổi | [`license-summary.md`](../261027-1353-m0-spike-emulator-and-render-validation/notes/license-summary.md) |

Quyết định:
- **Backend chính: Floci 2.3.0.** MiniStack 1.5.33 làm dự phòng cho các lab chỉ cần kiểm tra cấu hình.
- **Mức hậu kỳ mặc định: `full`** (N8AO + SMAA + ToneMapping). `PerformanceMonitor` hạ xuống `lite` thay vì `flat`, vì `flat` không còn khử răng cưa.
- **api-tap dùng được nguyên trạng.** Proxy stdlib Python giữ được chữ ký SigV4 và làm output giống hệt gọi trực tiếp; độ trễ thêm p50 2,8 ms, p95 5,3 ms. Không cần phương án chỉ dùng polling.
- **moto dùng được cho Lab 3** khi policy là Allow/Deny theo resource. moto bỏ qua `Condition`. Checker IAM có thể dùng `simulate-principal-policy` của Floci, vì lệnh này đánh giá đúng cả Condition.

## 2. Ma trận trường: Floci và MiniStack

Cả hai backend chạy đủ 36 bước của Lab 6 + 7 mà không có lỗi ([`lab-06-07.sh`](../../spikes/m0-emulators/lab-06-07.sh), output nằm trong `spikes/m0-emulators/out/<backend>/`).

| Tài nguyên | Floci | MiniStack |
|---|---|---|
| VPC, AZ, Subnet, IGW, Route Table, Security Group, Key Pair | đủ, đúng | đủ, đúng |
| NAT Gateway | 5/5 | 4/5: `NatGatewayAddresses` rỗng dù đã truyền EIP |
| Instance | 7/8: `PrivateIpAddress` sai do trùng CIDR với mạng Docker; đúng khi không trùng | 7/8: `PrivateIpAddress` nằm ngoài subnet |

Những điểm collector ở M2 phải xử lý với Floci:
1. **`PrivateIpAddress` có thể nằm ngoài CIDR khai báo.** Floci tạo một Docker network cho mỗi VPC. Khi CIDR trùng một mạng Docker có sẵn (trên máy đo là `ingress` của Swarm và `ecommerce-net`), Floci âm thầm đổi sang `10.240.0.0/16`. Cần cho lab engine kiểm tra trùng lặp trước (preflight) và cảnh báo, và vẽ instance theo `SubnetId` chứ không theo IP. `FLOCI_SERVICES_EC2_AWS_FAITHFUL_PRIVATE_IP=true` không sửa được trường hợp này.
2. **`PublicIpAddress` là `127.0.0.1`** trên Docker Desktop. Cảnh nên hiển thị cổng host đã public (dải 30000–30999) thay cho IP công khai.
3. **`ReservationId` đổi sau mỗi lần gọi `describe-instances`.** Dùng `InstanceId` làm khoá.
4. **Instance ở trạng thái `running` trước khi UserData xong** từ 45 giây đến khoảng 6 phút, vì Floci cài gói qua mạng mỗi lần khởi động.
5. Log của api-tap không suy ra được action của S3 REST. Cần suy từ method + path.

## 3. Hành vi emulator khác AWS thật (đầu vào cho ghi chú lab, NFR5)

- **Floci:**
  - Proxy IMDS chiếm `169.254.169.254:80` bên trong instance, nên web server bind `0.0.0.0:80` sẽ lỗi `Address already in use`. Lab 7 phải bind vào IP private, lấy từ `local-ipv4`.
  - Lần thứ hai chạy, bước cài proxy IMDS timeout sau 180 giây và instance không có IMDS. Đây là rủi ro cho Lab 8.
  - Lần đầu public cổng ứng dụng, Floci pull `alpine/socat` không kèm tag, nên Docker kéo về cả 23 tag (khoảng 2 phút).
  - **`docker compose down -v` để lại container EC2, network VPC và volume mồ côi.** Lab engine phải dọn theo label `io.floci.owner=<port>`.
- **MiniStack:** EC2 chỉ là bản ghi (không có container). NAT không có địa chỉ. IP private ngoài subnet. Có endpoint `POST /_ministack/reset`.
- **moto:**
  - Không đánh giá `Condition`. `simulate-*` trả HTTP 500 (`NotImplementedError`). Request không ký trả 500 thay vì 403.
  - `/moto-api/reset` không khôi phục lượt không xác thực. Phải gọi thêm `/moto-api/reset-auth` với body là số trần và `Content-Type: text/plain`.
- **Môi trường macOS:** cổng 5000 bị AirPlay Receiver chiếm, nên moto chạy ở 5050.
- **Reset:**
  - `docker compose restart` tới khi health OK mất 1,1 s (Floci) và 0,7 s (MiniStack).
  - Xoá từng tài nguyên bằng API (khoảng 20 lệnh CLI) mất 19,3 s và 10,6 s.

## 4. moto Lab 3

Cấu hình `INITIAL_NO_AUTH_ACTION_COUNT=3`: chỉ 3 lệnh tạo user `admin` là không xác thực, mọi lệnh sau đó ký bằng key IAM thật. Bằng chứng: [`summary.txt`](../../spikes/m0-moto/out/summary.txt).

| Trường hợp | moto | Floci `simulate-*` |
|---|---|---|
| Allow `alice/*`: ghi `alice/x` | cho phép (đúng) | `allowed` |
| Allow `alice/*`: ghi `bob/x` | `AccessDenied` (đúng) | `implicitDeny` |
| Allow `lab03/*` + Deny `bob/*` | đúng ở cả ba prefix | — |
| Allow có Condition SSE, ghi không SSE | **cho phép (sai)** | `implicitDeny` (đúng) |
| `simulate-principal-policy` | HTTP 500 | hoạt động ([bằng chứng](../../spikes/m0-moto/out/floci-simulate.txt)) |

Sau reset + reset-auth, chạy lại Lab 3 cho kết quả giống hệt ở cả 28 bước. Qua api-tap, kết quả allow/deny giữ nguyên. Một proxy đổi header `Host` thì bị `SignatureDoesNotMatch` ([bằng chứng](../../spikes/m0-moto/out/api-tap-sigv4.txt)).

## 5. Hiệu năng cảnh 200 node

Cảnh có 200 node (21 khay, 179 khối), 60 cạnh Bezier, 60 hạt xung và nhãn troika; camera trực giao xoay 30°/s. Mỗi cấu hình đo 10 s sau 2 s làm nóng, canvas 1280×800 CSS px. Bảng đầy đủ 24 lần đo: [`summary.md`](../../spikes/m0-render/results/summary.md).

| Trình duyệt | Mức | p50 | p95 (xấu nhất trong 4 cấu hình) | Draw call | Program |
|---|---|---|---|---|---|
| Chrome | full / lite / flat | 8,3 ms | 9,3 ms | 680 / 448 / 445 | 24 / 16 / 12 |
| Safari | full / lite / flat | 17 ms | 17 ms (p99 tối đa 21 ms) | 680 / 448 / 445 | 24 / 16 / 12 |

- Cả hai chủ đề và cả hai DPR đều cho cùng kết quả.
- Idle ở chế độ `demand`: 0 khung hình trong 10 s trên cả hai trình duyệt.
- **Giới hạn của số đo:** mọi cấu hình đều chạm trần vsync (Chrome 120 Hz, Safari 60 Hz), nên bài đo xác nhận ngưỡng 20 ms nhưng không đo được dư địa GPU giữa các mức. M1 Pro là cận dưới của NFR2.
- Ảnh chụp: [sáng](../../spikes/m0-render/results/screenshot-light-full-dpr2.png), [tối](../../spikes/m0-render/results/screenshot-dark-full-dpr2.png), [cận cảnh tối, có nhãn tiếng Việt](../../spikes/m0-render/results/screenshot-dark-full-dpr2-zoom40.png).

Cạm bẫy đã gặp và cách xử lý cho M2 (chi tiết trong ghi chú render):
1. `<OrthographicCamera makeDefault>` của drei làm `CameraControls` gắn nhầm vào camera phối cảnh. Dùng `<Canvas orthographic>`.
2. `fitToBox` với camera trực giao làm lệch góc nhìn và để zoom bằng 1.
3. `Outlines screenspace` vỡ hình dưới camera trực giao. Dùng độ dày theo đơn vị thế giới.
4. Ở chế độ `demand`, thay đổi camera bằng code cần `controls.update(0)` và `invalidate()`.
5. three 0.186 đã bỏ `PCFSoftShadowMap`, kiểu bóng mặc định của R3F 9.8.2. Nên đặt kiểu bóng tường minh.

## 6. Tóm tắt giấy phép

- npm (95 gói, kể cả gián tiếp và dev): MIT 76, Apache-2.0 9, ISC 5, BSD-3 2, Zlib 1 (postprocessing, dễ dãi), MPL-2.0 2 (lightningcss, chỉ dùng lúc build).
- Python (84 gói): toàn bộ là giấy phép dễ dãi, trừ certifi (MPL-2.0, dùng không sửa đổi).
- Floci MIT, MiniStack MIT, moto Apache-2.0, font Be Vietnam Pro OFL-1.1. AWS Architecture Icons không được phân phối (giữ F3.8).
- Danh sách: [`npm-licenses.json`](../../spikes/m0-licenses/npm-licenses.json), [`python-licenses.json`](../../spikes/m0-licenses/python-licenses.json).

## 7. Phiên bản ghim cho M1

| Thành phần | Phiên bản |
|---|---|
| Floci | `floci/floci:2.3.0@sha256:e0b292df4dc9559b7b1bf4f51bdda4bb8e269276236438cd03cae661260ea8a9` |
| MiniStack | `ministackorg/ministack:1.5.33@sha256:b58186186515a372798ccf0ca9975c295db219b5a811975337d6967b968e07b4` |
| moto | `moto[server]==5.2.4` |
| AMI Floci cho Lab 7 | `ami-amazonlinux2023-arm64` + `t4g.micro` (`t3.*` bị từ chối với AMI arm64, giống AWS) |
| Frontend | three 0.186.1, @react-three/fiber 9.8.2, @react-three/drei 10.7.9, @react-three/postprocessing 3.2.2, postprocessing 6.39.5, n8ao 2.0.1, @react-spring/three 10.1.2, react 19.3.1, vite 8.3.5, typescript 7.0.2 |
| Font | Be Vietnam Pro Medium (`.woff`, chuyển từ TTF của google/fonts) |

## 8. Câu hỏi mở

1. Có nên đổi CIDR mặc định của Lab 6 (ví dụ sang `10.20.0.0/16`) để giảm khả năng trùng với mạng Docker trên máy người học? Điều này đổi nội dung lab so với tài liệu AWS quen thuộc.
2. Lab 8 (đọc credential qua IMDS) phụ thuộc vào bước cài proxy IMDS, mà bước này đã timeout một lần. Cần chạy thử nhiều lần ở M1 để biết tỉ lệ lỗi trước khi giữ Lab 8 trên Floci.
3. A5 (giấy phép AWS Architecture Icons) vẫn chờ ý kiến pháp lý. Spike không trả lời được câu này, nhưng nó không chặn công việc vì mặc định đã là icon tự vẽ.
4. Muốn đo dư địa GPU (không chỉ ngưỡng 50 fps), cần một máy yếu hơn hoặc cảnh lớn hơn 200 node. Chưa làm trong M0.
