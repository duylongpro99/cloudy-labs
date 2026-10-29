# labctl

`labctl` dựng emulator cục bộ và chạy vòng đời một lab: bắt đầu, tự làm bằng AWS CLI, chấm, làm lại. Mã nguồn nằm ở [`server/`](../server/), package `cloudy_labs`.

## Yêu cầu

- Docker Desktop (hoặc Docker Engine có `docker compose`) đang chạy.
- [uv](https://docs.astral.sh/uv/). uv tự cài Python 3.12 nếu máy chưa có.
- AWS CLI v2 để làm lab.
- Các cổng ở bảng [Cổng](#cổng) còn trống.

## Cài đặt

```bash
cd server
uv sync
uv run labctl --help
```

## Lệnh

| Lệnh | Việc làm |
|---|---|
| `labctl up` | Dựng api-tap, Floci và moto ([`compose.yaml`](../server/src/cloudy_labs/emulator/compose.yaml)), chờ healthy, dọn tài nguyên mồ côi từ lần trước, pull sẵn `alpine/socat:latest`. Lần đầu, lệnh này build thêm hai image Amazon Linux 2023 cài sẵn gói cho IMDS và SSH (`cloudy-labs/al2023:1-x86_64` và `:1-arm64`, khoảng 1–2 phút, cần mạng); các lần sau dùng lại. `down` không xoá các image này. Chạy lại khi stack đang chạy thì chỉ báo "already running", trừ khi Floci healthy trong Docker nhưng không trả lời ở cổng host; khi đó container Floci được tạo lại. Cổng bị process khác chiếm thì báo lỗi, không đổi sang cổng khác. |
| `labctl down` | Tắt stack và xoá container EC2, network VPC, volume mà Floci để lại. |
| `labctl env [lab]` | In các dòng `export` trỏ AWS CLI vào emulator của lab (mặc định Floci). Dùng: `eval "$(labctl env lab-06)"`. |
| `labctl start <lab>` | Cảnh báo nếu CIDR của lab trùng mạng Docker, reset emulator của lab, mở một lần làm mới (attempt), chạy các bước `setup` và in danh sách task. Nếu `setup` lỗi, lần làm mới vẫn được mở; chạy `labctl reset <lab>` để thử lại. |
| `labctl check <lab> [--json]` | Chạy các check của lab. Cần lần làm hiện tại là của lab này. |
| `labctl reset <lab>` | Reset emulator, mở lần làm mới, chạy lại `setup`. |
| `labctl status [lab] [--json]` | Health của từng emulator, lab đang làm, kết quả check gần nhất, danh sách lab và lab nào đã hoàn thành. |
| `labctl serve` | Chạy lab-server cho cảnh 3D trực tiếp ở `127.0.0.1:8730`, chạy foreground đến khi Ctrl-C. Xem [Cảnh 3D trực tiếp](#cảnh-3d-trực-tiếp). |

Mã thoát của `check`: `0` khi đạt hết, `1` khi có check trượt, `2` khi không chấm được (chưa `start`, emulator chưa chạy, lab lỗi, lỗi bất ngờ). Các lệnh khác trả `1` khi lỗi. `down` vẫn tắt stack khi có tài nguyên Floci không xoá được, rồi trả `1` và liệt kê chúng.

Reset chỉ đụng tới emulator mà lab dùng: container Floci được xoá và tạo lại cùng các instance của nó (khoảng 1–5 giây), moto được gọi `/moto-api/reset` và `/moto-api/reset-auth`, rồi tạo lại user admin (key cũ hết hiệu lực, cần chạy lại `eval "$(labctl env <lab>)"`).

## Cổng

Mọi cổng chỉ bind `127.0.0.1`. Nguồn gốc: [`config.py`](../server/src/cloudy_labs/config.py) và [`compose.yaml`](../server/src/cloudy_labs/emulator/compose.yaml). Cổng bị process khác chiếm thì lệnh báo lỗi, không đổi sang cổng khác.

| Cổng | Thành phần | Ai dùng |
|---|---|---|
| 4566 | api-tap, proxy đứng trước Floci | AWS CLI của người học (`labctl env`) và checker |
| 4567 | Floci, đi thẳng (Floci cũng nghe ở 4567 trong container) | `labctl` và collector, để lệnh đọc của chúng không bị tính là hoạt động của người học |
| 4568 | api-tap, luồng SSE `/events` các lệnh ghi | `labctl serve` |
| 5050 | moto | lab chạy trên moto |
| 8730 | lab-server (`labctl serve`) | web, qua proxy của Vite |
| 5174 | Vite dev server của `web/` | trình duyệt |

## Cảnh 3D trực tiếp

```bash
cd server && uv run labctl up && uv run labctl serve   # terminal 1, giữ chạy
cd web && pnpm dev                                      # terminal 2; mở http://127.0.0.1:5174/
```

Sau đó làm lab bằng AWS CLI như bình thường (`eval "$(uv run labctl env <lab>)"`); cảnh tự cập nhật.

- api-tap chuyển tiếp nguyên vẹn mọi request (giữ chữ ký SigV4). Gặp lệnh ghi (`Create*`, `Run*`, `Delete*`…), nó phát một sự kiện trên kênh SSE; không ai nghe thì sự kiện bị bỏ. api-tap nằm trong compose, nên CLI vẫn chạy khi `serve` tắt.
- `serve` nghe kênh đó, gom các sự kiện gần nhau (150 ms) rồi cho collector đọc lại Floci thành resource graph ([`schema.py`](../server/src/cloudy_labs/graph/schema.py)). Ngoài ra nó đọc lại mỗi 5 giây làm lưới an toàn. Graph chỉ được gửi khi nội dung đổi, kèm số phiên bản tăng dần.
- WebSocket `/ws` gửi hai loại tin: `graph` (toàn bộ graph) và `api-event` (`service`, `action`, `write`). `GET /api/graph` trả graph gần nhất. `/ws` chỉ nhận origin của Vite dev server.
- Floci từ chối kết nối (đã `down`, đang tạo lại) thì graph có `status: "emulator-down"` ngay và web báo trạng thái đó; Floci lên lại thì cảnh tự về trạng thái mới, không cần tải lại trang. Lỗi có thể chỉ thoáng qua (timeout) phải lặp lại 2 lần liền mới chuyển sang `emulator-down`, để một lệnh đọc chậm không xoá cảnh. `labctl reset` tạo lại Floci trong khoảng 1,5 s và cổng chỉ đóng chừng 0,5 s, ngắn hơn chu kỳ poll 5 s, nên cảnh thường đi thẳng về Region trống mà không kịp hiện `emulator-down`. Tắt `serve` khi web đang mở thì web báo mất kết nối và tự nối lại khi `serve` chạy lại.
- Độ trễ từ lúc lệnh CLI trả về tới khi WebSocket nhận graph mới: p95 khoảng 0,3 giây trên máy phát triển (`uv run pytest -m docker tests/test_latency_docker.py -s` in số đo).

## Biến môi trường

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `CLOUDY_LABS_HOME` | `~/.cloudy-labs` | Thư mục trạng thái cục bộ; tiến độ nằm ở `progress.db` (SQLite). |
| `CLOUDY_LABS_LABS_DIR` | `<repo>/labs` | Thư mục chứa các lab. |

Region là `us-east-1`. Với Floci, credential luôn là `test`/`test`. Với lab chạy trên moto, `start`/`reset` tạo user IAM `cloudy-labs-admin` và lưu key của nó ở `moto-credentials.json` trong `CLOUDY_LABS_HOME` (quyền `0600`); `labctl env <lab>` xuất key này, checker cũng dùng nó. Mọi key ở đây chỉ có giá trị trong emulator; không dùng credential AWS thật với `labctl`.

## Viết một lab

Mỗi lab là một thư mục trong `labs/`, tên thư mục trùng `id`:

```text
labs/<id>/
  lab.yaml
  checks.py
```

`lab.yaml` (schema: [`schema.py`](../server/src/cloudy_labs/labs/schema.py)):

```yaml
id: fixture-vpc
provider: aws
emulator: floci          # hoặc moto, cho lab cần IAM thật sự chặn quyền
title: Fixture VPC
cidrs: [10.77.0.0/16]    # mọi CIDR lab sẽ tạo, để preflight kiểm trùng mạng Docker
setup: []                # các hàm "module:function" chạy sau mỗi lần reset
tasks:
  - id: create-vpc
    text: Create a VPC 10.77.0.0/16 tagged lab=fixture-vpc.
checks:
  - id: vpc-exists
    task: create-vpc
    fn: checks:vpc_exists
    args: {cidr: 10.77.0.0/16}
hints:
  - task: create-vpc
    text: aws ec2 create-vpc --cidr-block 10.77.0.0/16 --tag-specifications ...
target: {}               # kiến trúc mục tiêu cho lớp ghost 3D, định nghĩa sau
```

Trường lạ, `id` trùng, check hoặc hint trỏ tới task không có, hay `fn` sai dạng `module:function` đều làm lab không nạp được. Mọi hàm được tham chiếu phải tồn tại ngay lúc nạp.

`checks.py`: mỗi checker nhận `ctx` và các `args`, trả về `CheckResult`. `ctx.client(service)` là client boto3 đã trỏ vào emulator của lab. `resource_ids` là các tài nguyên cảnh 3D sẽ tô sáng.

```python
from cloudy_labs.checks import CheckContext, CheckResult


def vpc_exists(ctx: CheckContext, cidr: str) -> CheckResult:
    vpcs = ctx.client("ec2").describe_vpcs(Filters=[{"Name": "tag:lab", "Values": ["fixture-vpc"]}])["Vpcs"]
    match = [v["VpcId"] for v in vpcs if v["CidrBlock"] == cidr]
    if match:
        return CheckResult(True, f"VPC {match[0]} has CIDR {cidr}", match)
    return CheckResult(False, f"no VPC tagged lab=fixture-vpc with CIDR {cidr}")
```

Checker ném exception, trả về kiểu khác `CheckResult`, hoặc trả `CheckResult` sai kiểu trường (`passed` không phải bool, `message` không phải chuỗi, `resource_ids` không phải danh sách chuỗi) được tính là trượt; các check còn lại vẫn chạy. Hàm `setup` nhận `ctx` giống checker.

Trước khi soạn lab, đọc [emulator-differences.md](emulator-differences.md) để tránh chấm dựa trên hành vi mà emulator không giống AWS.

> **Chỉ nạp lab tin cậy.** `checks.py` chạy với toàn quyền của người dùng. labctl chỉ nạp lab trong thư mục lab của repo (hoặc `CLOUDY_LABS_LABS_DIR`).

## Test

```bash
cd server
uv run pytest            # test đơn vị, không cần Docker
uv run pytest -m docker  # vòng đời đầy đủ trên stack thật; luôn gọi `down` khi xong
```

`-m docker` còn so `ec2-image-catalog.yaml` với catalog nhúng trong image Floci đang ghim ở `compose.yaml`, nên quên sinh lại catalog sau khi đổi phiên bản Floci sẽ làm test trượt. Test đơn vị chỉ bắt được trường hợp tag Floci trong `compose.yaml` khác tag ghi ở đầu catalog.

## Bảo trì image Amazon Linux 2023 và catalog AMI

Chạy trong `server/`, cần Docker và mạng ([`images.py`](../server/src/cloudy_labs/emulator/images.py)).

| Khi nào | Lệnh |
|---|---|
| Đổi image Floci trong `compose.yaml` | `uv run python -m cloudy_labs.emulator.images sync-catalog`: lấy catalog nhúng trong binary Floci rồi trỏ các AMI Amazon Linux 2023 sang image của mình. Không sửa catalog bằng tay. |
| Muốn dùng bản `amazonlinux:2023` mới nhất | `uv run python -m cloudy_labs.emulator.images bump-base`: ghim digest mới vào `al2023/Dockerfile` và tăng `AL2023_VERSION` cùng các tag trong catalog. Digest chưa đổi thì lệnh chỉ báo và không sửa gì. |
| Sửa `al2023/Dockerfile` vì lý do khác | `bump-base --force`: chỉ tăng phiên bản tag. |

Sau `bump-base`, chạy test rồi `labctl down` và `labctl up` để build image mới và nạp lại catalog. Lệnh in ra câu `docker image rm` để xoá image phiên bản cũ.
