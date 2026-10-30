# labctl

`labctl` dựng emulator cục bộ và chạy vòng đời một lab: bắt đầu, tự làm bằng AWS CLI, chấm, làm lại. Mã nguồn nằm ở [`server/`](../server/), package `cloudy_labs`.

## Yêu cầu

- Docker Desktop (hoặc Docker Engine có `docker compose`) đang chạy.
- [uv](https://docs.astral.sh/uv/). uv tự cài Python 3.12 nếu máy chưa có.
- AWS CLI v2 để làm lab. Builder kéo-thả cũng chạy lệnh bằng AWS CLI này; thiếu nó thì builder vẫn hiện lệnh nhưng nút Run bị khoá.
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
| `labctl up` | Ghi profile `lab` vào config AWS của bạn (xem [Builder kéo-thả](#builder-kéo-thả)). Dựng api-tap, Floci và moto ([`compose.yaml`](../server/src/cloudy_labs/emulator/compose.yaml)), chờ healthy, dọn tài nguyên mồ côi từ lần trước, pull sẵn `alpine/socat:latest`. Lần đầu, lệnh này build thêm hai image Amazon Linux 2023 cài sẵn gói cho IMDS và SSH (`cloudy-labs/al2023:1-x86_64` và `:1-arm64`, khoảng 1–2 phút, cần mạng); các lần sau dùng lại. `down` không xoá các image này. Chạy lại khi stack đang chạy thì chỉ báo "already running", trừ khi Floci healthy trong Docker nhưng không trả lời ở cổng host; khi đó container Floci được tạo lại. Cổng bị process khác chiếm thì báo lỗi, không đổi sang cổng khác. |
| `labctl down` | Tắt stack và xoá container EC2, network VPC, volume mà Floci để lại. |
| `labctl env [lab]` | In các dòng `export` trỏ AWS CLI vào emulator của lab (mặc định Floci). Dùng: `eval "$(labctl env lab-06)"`. |
| `labctl start <lab>` | Cảnh báo nếu CIDR của lab trùng mạng Docker, reset emulator của lab, mở một lần làm mới (attempt), chạy các bước `setup` và in danh sách task. Nếu `setup` lỗi, lần làm mới vẫn được mở; chạy `labctl reset <lab>` để thử lại. |
| `labctl check <lab> [--json]` | Chạy các check của lab. Cần lần làm hiện tại là của lab này. |
| `labctl reset <lab>` | Reset emulator, mở lần làm mới, chạy lại `setup`. |
| `labctl status [lab] [--json]` | Health của từng emulator, lab đang làm, kết quả check gần nhất, danh sách lab và lab nào đã hoàn thành. |
| `labctl serve` | Chạy lab-server cho cảnh 3D trực tiếp và builder ở `127.0.0.1:8730`, chạy foreground đến khi Ctrl-C. Cảnh báo khi thiếu `aws` CLI hoặc profile `lab`, khi AWS CLI cũ hơn 2.13 (bỏ qua `endpoint_url`), và khi file credentials có section `[lab]`. Xem [Cảnh 3D trực tiếp](#cảnh-3d-trực-tiếp). |

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

## Builder kéo-thả

Khi có lab đang làm (`labctl start <lab>`) và lab khai báo `builder.palette`, panel trên cùng của cảnh có thêm bảng tài nguyên. Builder không tự tạo gì: mỗi thao tác chỉ dựng một lệnh `aws`, người học đọc lệnh rồi bấm Run.

- **Tạo**: kéo một tài nguyên (VPC, Subnet, Internet Gateway, Elastic IP, NAT Gateway, Route Table, Security Group, Key Pair, EC2 Instance) từ bảng vào cảnh. Security Group thả vào VPC, Key Pair vào Region, Instance vào subnet. Khay nhận được tô sáng, khay không nhận được tô tối; thả sai chỗ thì panel giải thích vì sao. Thả xong, form hiện các trường còn thiếu, điền sẵn gợi ý (CIDR của lab, block /24 còn trống, AZ của khay).
- **Nối**: chọn Internet Gateway, Route Table hoặc Security Group, kéo chấm tròn phía trên nó tới VPC, IGW, NAT Gateway, subnet hoặc instance. Ra `attach-internet-gateway`, `create-route` (mặc định `0.0.0.0/0`), `associate-route-table` hoặc `modify-instance-attribute`. Gắn SG vào instance thì server tự điền các SG instance đang có vào `--groups` (lệnh này thay cả danh sách), trình duyệt không được gửi danh sách đó.
- **Thuộc tính**: panel thuộc tính của VPC có nút "Bật DNS hostnames", của subnet có nút "Tự gán IP public", của Security Group có danh sách rule inbound và nút "Thêm rule inbound" (mặc định tcp 80 từ `0.0.0.0/0`). Rule mở SSH (cổng 22, hoặc protocol `-1`) cho `0.0.0.0/0` bị từ chối kèm lời giải thích; rule trùng cũng bị từ chối, vì Floci không tự chặn ([khác biệt](emulator-differences.md#ec2)).
- **Instance**: form chỉ cho chọn AMI và instance type hợp với máy (khoá theo kiến trúc), SG trong VPC của subnet, key pair (hoặc không dùng), và UserData mặc định của lab (`builder.userData` trong `lab.yaml`, tối đa 16 KB). UserData bind web server vào `0.0.0.0:80` thì form nhắc rằng IMDS đã chiếm cổng đó.
- **Key pair**: chạy `create-key-pair` xong, panel có nút "Tải `<tên>`.pem". AWS chỉ trả private key một lần; trang chỉ giữ key trong bộ nhớ (không `localStorage`, không gửi đi đâu), server không ghi stdout của lệnh vào log.
- **Luyện tập** (công tắc trên panel builder, nhớ theo trình duyệt): builder dựng và kiểm lệnh như thường nhưng không có nút Run. Bấm Chép thì panel chờ bạn dán lệnh vào terminal và chạy; panel hiện lệnh ghi gần nhất emulator nhận được qua api-tap, và báo xong khi graph có tài nguyên đúng loại với Name đã gõ (hoặc cạnh, thuộc tính tương ứng). Emulator đã nhận lệnh mà 10 giây sau cảnh vẫn chưa khớp thì panel gợi ý kiểm lại tên đã gõ. Không có giới hạn thời gian; Esc huỷ. Công tắc khoá khi đang Run.
- Panel lệnh hiện đúng lệnh sẽ chạy, kèm `--profile lab --output json`, để copy sang terminal. Run và Chép chỉ bật khi form hết lỗi và lệnh đang hiện khớp với lần sửa cuối; vừa sửa form thì lệnh cũ mờ đi cho tới khi preview mới về. Sau Run, panel hiện exit code, stdout, stderr, rồi chờ graph của collector thấy thay đổi (tối đa 5 giây) mới báo xong. Cảnh chỉ đổi theo graph, không theo builder. Esc huỷ thao tác đang dở.

Phía server, trình duyệt chỉ gửi `{op, params}`, không bao giờ gửi dòng lệnh. Server dựng argv từ danh mục op cố định ([`ops.py`](../server/src/cloudy_labs/builder/ops.py)), kiểm theo graph hiện tại ([`validate.py`](../server/src/cloudy_labs/builder/validate.py)), rồi chạy không qua shell, mỗi lần một lệnh, timeout 60 giây. Hết giờ hoặc huỷ thì cả process group của lệnh bị kill, output đã có vẫn được trả về. Không đọc được danh sách AZ của region thì `create-subnet` bị từ chối thay vì bỏ qua bước kiểm AZ ([`runner.py`](../server/src/cloudy_labs/builder/runner.py)).

| Endpoint | Việc làm |
|---|---|
| `GET /api/lab` | Lab đang làm: tiêu đề, attempt, palette, các op lab cho dùng, AZ của region, `images` và `instanceTypes` máy này chạy được, `userData` mặc định của lab, `canRun` và `runBlocker` (vì sao Run bị khoá: thiếu `aws` CLI, AWS CLI cũ hơn 2.13, hoặc file credentials có `[lab]`; `null` khi chạy được). `{"id": null}` khi chưa `start`. |
| `POST /api/preview` | `{op, params}` → lệnh hiển thị, argv, danh sách lỗi theo từng trường, và `practiceExpect` (graph phải có gì sau khi người học tự chạy lệnh). Không chạy gì. |
| `POST /api/run` | Kiểm lại rồi chạy. Trả exit code, stdout, stderr, thời gian và `expect` (graph phải có gì thì coi là xong). Còn lỗi kiểm tra thì không chạy, trả `409` kèm lệnh và danh sách lỗi. Lệnh đến khi lệnh trước chưa xong cũng trả `409`. Khi Run bị khoá (`runBlocker`), trả `503` kèm lý do. |

`/api/preview` và `/api/run` chỉ nhận request JSON từ origin của Vite dev server, để trang web khác không gửi lệnh được.

**Profile `lab`.** `labctl up` ghi một khối `[profile lab]` vào `~/.aws/config` (hoặc file mà `AWS_CONFIG_FILE` trỏ tới): endpoint là api-tap `http://127.0.0.1:4566`, key giả `test`/`test`, region `us-east-1`. Lần đầu sửa file, nó lưu bản sao `config.cloudy-labs.bak` cạnh file gốc. Khối có dòng đánh dấu `# managed by labctl` và chỉ khối đó bị ghi lại; nếu đã có `[profile lab]` không do labctl viết thì `up` báo lỗi và không đụng vào. Ghi qua symlink thì ghi vào file đích, symlink giữ nguyên; comment nằm ngay trên section kế tiếp không bị coi là của khối lab. AWS CLI cũ hơn 2.13 bỏ qua `endpoint_url` và một section `[lab]` trong file credentials sẽ đè key giả, nên khi gặp một trong hai, lab-server khoá Run để lệnh không đi tới AWS thật. Runner bỏ mọi biến `AWS_*` (trừ `AWS_CONFIG_FILE`) khỏi môi trường của lệnh, nên lệnh chạy giống hệt khi dán vào terminal bất kỳ.

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

`tests/test_builder_e2e_docker.py` (cũng `-m docker`) dựng stack, mở `fixture-lab-06`, chạy lab-server, dùng Vite dev server đang chạy ở 5174 (hoặc tự bật rồi tắt), rồi để [`web/scripts/e2e-builder-lab-06.mjs`](../web/scripts/e2e-builder-lab-06.mjs) làm cả lab qua builder trong Google Chrome và chạy `labctl check`. Sau đó nó mở `fixture-lab-07` và để [`web/scripts/e2e-builder-lab-07.mjs`](../web/scripts/e2e-builder-lab-07.mjs) làm Lab 7 hai lần: một lần bằng Run, một lần ở chế độ luyện tập (chép lệnh rồi chạy bằng `bash -c`, không có `/api/run` nào), mỗi lần chờ `labctl check` đạt tới 60 giây. Cần `aws`, `node`, `pnpm` và cổng 8730 trống. Test tự trỏ `AWS_CONFIG_FILE` vào thư mục tạm, không đụng config AWS của bạn.

`-m docker` còn so `ec2-image-catalog.yaml` với catalog nhúng trong image Floci đang ghim ở `compose.yaml`, nên quên sinh lại catalog sau khi đổi phiên bản Floci sẽ làm test trượt. Test đơn vị chỉ bắt được trường hợp tag Floci trong `compose.yaml` khác tag ghi ở đầu catalog.

## Bảo trì image Amazon Linux 2023 và catalog AMI

Chạy trong `server/`, cần Docker và mạng ([`images.py`](../server/src/cloudy_labs/emulator/images.py)).

| Khi nào | Lệnh |
|---|---|
| Đổi image Floci trong `compose.yaml` | `uv run python -m cloudy_labs.emulator.images sync-catalog`: lấy catalog nhúng trong binary Floci rồi trỏ các AMI Amazon Linux 2023 sang image của mình. Không sửa catalog bằng tay. |
| Muốn dùng bản `amazonlinux:2023` mới nhất | `uv run python -m cloudy_labs.emulator.images bump-base`: ghim digest mới vào `al2023/Dockerfile` và tăng `AL2023_VERSION` cùng các tag trong catalog. Digest chưa đổi thì lệnh chỉ báo và không sửa gì. |
| Sửa `al2023/Dockerfile` vì lý do khác | `bump-base --force`: chỉ tăng phiên bản tag. |

Sau `bump-base`, chạy test rồi `labctl down` và `labctl up` để build image mới và nạp lại catalog. Lệnh in ra câu `docker image rm` để xoá image phiên bản cũ.
