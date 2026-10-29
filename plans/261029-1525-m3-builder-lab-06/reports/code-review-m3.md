# Code review: M3 builder kéo-thả cho Lab 6 (working tree chưa commit)

Ngày: 2026-10-29. Review chỉ đọc. Không chạy lại các bộ test lead đã chạy (pytest 228, ruff, pnpm test 139, typecheck, e2e docker). Đã chạy 3 script tái hiện trong scratchpad (không docker, không dev server): một cho regex/CIDR/aws_profile, một cho runner, một cho `/api/preview` qua `TestClient`. Không sửa file nguồn nào.

## Phạm vi
- Server: `builder/{ops,validate,runner}.py`, `emulator/aws_profile.py`, diff trong `server/app.py`, `cli.py`, `labs/schema.py`, `graph/collector.py`, cùng các test mới và test đã sửa.
- Web: `src/builder/*`, `src/scene/{live-scene,pointer-probe,drop-highlight,connect-line,property-panel}.tsx`, `src/app.tsx`.
- Trọng tâm, theo thứ tự lead yêu cầu: (1) bảo vệ endpoint ghi, (2) an toàn của `aws_profile.py`, (3) luật validate, (4) runner, (5) state machine web, (6) chỗ thiếu test.

## Đánh giá chung
Thiết kế cốt lõi vững. Trình duyệt chỉ gửi `{op, params}`. Danh mục op là `dict` cố định, `argv[0]` luôn là `aws`, không qua shell. Thứ tự kiểm ở `op_request` đúng: Origin → Content-Type → JSON → shape → op → pydantic `extra="forbid"` → lab đang mở → palette → emulator. `/api/run` validate lại phía server, nên preview cũ không làm chạy được lệnh sai luật. Vite chỉ bind loopback và proxy giữ nguyên `Origin`. `TrustedHostMiddleware` chặn DNS rebinding. Mọi id trong params phải trùng đúng id một node trong graph, nên chỉ còn `name`, `cidr`, `destination` và `az` là chuỗi tự do.

Tìm thấy: hai lỗi ở `aws_profile.py` làm hỏng file config thật của người dùng (symlink, comment). Một lỗi state machine làm lệnh chạy khác lệnh đang hiển thị, trái với lời hứa cốt lõi của F4.4. Một lỗ validate (`az`) để chuỗi tùy ý vào argv khi emulator không trả danh sách AZ. Runner mất output khi timeout và để lại tiến trình mồ côi khi bị huỷ. Phần còn lại là lỗi nhỏ và nit.

---

## High

### H1. `ensure_lab_profile` thay symlink `~/.aws/config` bằng file thường
`server/src/cloudy_labs/emulator/aws_profile.py:79-89`

`path` là chính symlink, không được `resolve()`. `os.replace(tmp, path)` thay symlink bằng một file thường. `shutil.copy2(path, backup)` thì đi theo symlink, nên bản sao lưu vẫn đúng nội dung.

**Đã tái hiện:** `AWS_CONFIG_FILE=linkcfg -> dotfiles-config`, gọi `ensure_lab_profile()`:
```
still symlink: False real has lab: False
```
**Kịch bản lỗi:** Người dùng quản lý dotfiles bằng stow/chezmoi/yadm, nên `~/.aws/config` là symlink vào repo dotfiles. Sau `labctl up`, file thật trong repo không đổi, còn `~/.aws/config` thành một bản sao rời. Từ đó, mọi lần sửa hoặc `git pull` dotfiles (ví dụ thêm profile công việc mới) không còn tác dụng, và không có cảnh báo nào. Điều này trái với tiêu chí "không làm hỏng phần còn lại của file config AWS".

**Sửa:** ghi vào file đích, không ghi vào link.
```python
path = config_path()
target = path.resolve() if path.is_symlink() else path
# đọc, sao lưu và tạo file tạm cạnh `target`; os.replace(tmp, target)
```
Một lựa chọn khác là từ chối khi `path.is_symlink()` và in hướng dẫn. Thêm test: config là symlink → sau `ensure_lab_profile()` vẫn là symlink và file đích có `[profile lab]`.

### H2. Lệnh chạy có thể khác lệnh đang hiển thị (preview cũ sau khi sửa form)
`web/src/builder/use-builder.ts:66-77`, `:157-161`; `web/src/builder/command-panel.tsx:46`

Action `edit` giữ `preview: s.preview` của rev cũ (dòng 70). Action `run` chỉ kiểm `s.preview` có tồn tại và không có problem (dòng 76), không kiểm preview đó thuộc rev nào. `run()` gửi `s.draft.params` của rev mới (dòng 161). Nút Run và nút "Chép lệnh" vẫn bật với chuỗi lệnh cũ.

**Kịch bản lỗi:** Form `create-subnet` đang hiện `--cidr-block 10.66.1.0/24`. Người học gõ thành `10.66.2.0/24` rồi bấm Run trong vòng 200 ms debounce cộng RTT. Lệnh chạy dùng `10.66.2.0/24`, còn panel vẫn hiện `10.66.1.0/24` cho tới khi outcome về. Nếu bấm "Chép lệnh" lúc đó, người học dán lệnh cũ. Server có validate lại, nên giá trị mới vẫn phải hợp lệ. Nhưng bất biến "lệnh hiện ra là lệnh chạy" (plan, quyết định thiết kế 1; F4.4) bị phá. Trường hợp tương tự: `failed` do 503 hoặc mất kết nối có `problems: []`, sau đó `edit` → Run bật ngay với preview cũ.

**Sửa:** gắn rev vào preview và chỉ cho Run khi preview khớp draft.
```ts
| { phase: 'form'; draft: Draft; preview: Preview | null; previewRev: number | null; error: string | null }
// previewed: { ...s, preview: a.preview, previewRev: a.rev, error: a.error }
// run: if (s.phase !== 'form' || !s.preview || s.previewRev !== s.draft.rev || s.preview.problems.length > 0) return s
```
`CommandPanel` tắt Run/Chép và làm mờ lệnh khi `previewRev !== draft.rev`. Thêm test reducer: `previewed(rev 0)` → `edit` → `run` phải giữ `phase: 'form'`.

---

## Medium

### M1. `az` không được validate khi danh sách AZ rỗng, nên chuỗi tùy ý (kể cả `file://`) vào argv
`server/src/cloudy_labs/builder/validate.py:118`; `server/app.py:75-79`; `graph/collector.py:313-320`

`if azs and params.az not in azs` bỏ qua luật khi `azs == []`. `region_azs()` trả `[]` khi gặp bất kỳ `BotoCoreError`/`ClientError` nào, ví dụ một lần timeout thoáng qua. `region_zones()` chỉ cache khi danh sách khác rỗng. `/api/run` chỉ đòi `hub.graph.status == "ok"`, không đòi có AZ.

**Đã tái hiện** (`TestClient`, `azs=lambda: []`):
```
'argv': [..., '--availability-zone', 'file:///etc/hosts', ...], 'problems': []
```
**Kịch bản lỗi:** AWS CLI v2 đọc `file://...` làm giá trị tham số. Khi đó nội dung một file cục bộ, ví dụ `~/.aws/credentials`, được gửi tới api-tap/Floci, và thông báo lỗi "invalid AZ" có thể in lại nó vào stderr, rồi stderr trả về trình duyệt. Muốn gọi được thì phải qua Origin hợp lệ (web app hoặc một tiến trình cục bộ), nên rủi ro thực tế thấp. Nhưng đây là tham số duy nhất phá bất biến "mọi giá trị vào argv đều đã qua validate", và luật AZ lặng lẽ biến mất mỗi khi emulator chậm. Form web cũng chuyển ô `az` thành input tự do khi `lab.azs` rỗng (`build-form.tsx:41`).

**Sửa:** fail closed và kiểm thêm hình dạng.
```python
AZ = re.compile(r"[a-z]{2}(-[a-z]+)+-\d[a-z]")
if not azs:
    problems.append(Problem("az", "could not read this region's Availability Zones from the emulator; try again in a moment"))
elif params.az not in azs:
    ...
```
Thêm test: `azs=[]` → `/api/run` trả 409, runner không được gọi.

### M2. Runner làm mất stdout/stderr đã có khi timeout
`server/src/cloudy_labs/builder/runner.py:58-65`

`wait_for(proc.communicate())` huỷ task `communicate`, và phần dữ liệu nó đã đọc mất theo. Lần `communicate()` thứ hai chỉ đọc phần còn lại.

**Đã tái hiện:** `sh -c 'echo partial-out; echo partial-err >&2; sleep 30'`, timeout 1 s:
```
RunResult(exit_code=None, stdout='', stderr='\nlabctl: stopped after 1s without an answer', ...)
```
**Kịch bản lỗi:** `aws` in cảnh báo hoặc lỗi retry ra stderr rồi treo, ví dụ endpoint nhận kết nối nhưng không trả lời. Người học chỉ thấy "stopped after 60s", mất đúng thông tin chẩn đoán mà F4.4 hứa giữ nguyên văn.

**Sửa:** đọc hai stream bằng task riêng, còn timeout chỉ áp lên `wait()`.
```python
out_t = asyncio.create_task(proc.stdout.read())
err_t = asyncio.create_task(proc.stderr.read())
try:
    code = await asyncio.wait_for(proc.wait(), self.timeout)
except TimeoutError:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    await proc.wait()
    code = None
out, err = await out_t, await err_t
```
Thêm test: fake `aws` in ra trước khi `sleep`, sau timeout output đó vẫn còn.

### M3. Runner bị huỷ (CancelledError) thì để lại tiến trình `aws` mồ côi
`server/src/cloudy_labs/builder/runner.py:58-66`

Chỉ bắt `TimeoutError`. `start_new_session=True` nên Ctrl+C ở terminal `labctl serve` không tới được tiến trình con.

**Đã tái hiện:** huỷ task sau 0,5 s → `orphan pids after cancel: ['70086']`, kèm `RuntimeError: Event loop is closed` từ `BaseSubprocessTransport.__del__`.

**Kịch bản lỗi:** Dừng `labctl serve` (uvicorn huỷ request đang chờ khi tắt cưỡng bức) trong lúc một lệnh đang chạy. `aws` vẫn chạy tiếp ngoài mọi theo dõi, có thể ghi tài nguyên vào emulator sau khi server đã tắt. Đây đúng là kiểu tiến trình "ghost" mà rule process-management cấm.

**Sửa:**
```python
try:
    ...
finally:
    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        await asyncio.shield(proc.wait())
```

### M4. `aws_profile.render` xoá comment của section kế tiếp khi cập nhật khối lab
`server/src/cloudy_labs/emulator/aws_profile.py:47`, `:67-69`

Khối lab kéo dài tới header `[` kế tiếp. Vòng `while` chỉ cắt dòng trống ở cuối, còn comment nằm giữa khối lab và section sau bị coi là một phần khối lab.

**Đã tái hiện:** config có `...cli_pager =\n# Work account (prod) - do not delete\n[profile work]`, khối lab bị đổi một dòng → `ensure_lab_profile()` trả `updated` và `comment kept: False`.

**Kịch bản lỗi:** Người dùng thêm profile mới ngay sau khối lab, kèm comment mô tả ở phía trên. Lần `labctl up` sau mà khối cần ghi lại (labctl đổi port hoặc key, hoặc người dùng lỡ sửa một dòng) sẽ xoá comment đó. Bản sao lưu chỉ được tạo trước lần ghi đầu tiên, nên không giữ comment này. Lỗi trái với tiêu chí "giữ nguyên comment" trong phần verification. Test hiện có (`test_keeps_comments_and_other_profiles_and_backs_up`) chỉ phủ comment nằm trước khối.

**Sửa:** chỉ coi là của labctl những dòng ngay sau header là `MARK` hoặc dạng `key = value`. Dừng ở dòng trống, dòng comment khác hoặc header.
```python
def _own(line: str) -> bool:
    s = line.strip()
    return s == MARK or (bool(s) and not s.startswith(("[", "#", ";")))

end = i + 1
while end < len(lines) and _own(lines[end]):
    end += 1
``` Thêm test: comment ngay trên `[profile work]` nằm sau khối lab vẫn còn sau khi update.

---

## Low

### L1. Regex `NAME` và `TAG_TEXT` chấp nhận ký tự xuống dòng ở cuối
`server/src/cloudy_labs/builder/validate.py:20,107`; `server/src/cloudy_labs/labs/schema.py:45,65`

Với `re.match`, `$` khớp trước một `\n` ở cuối chuỗi. **Đã tái hiện:** `NAME.match("lab06-vpc\n")` → True, và `/api/preview` trả `problems: []` với `Value=lab06-vpc\n` trong `--tag-specifications`. Không có shell nên không thành injection, nhưng tag mang ký tự xuống dòng đi vào emulator, và câu lệnh hiển thị có xuống dòng bên trong dấu nháy. **Sửa:** dùng `NAME.fullmatch(...)` (bỏ `^`/`$`) hoặc kết thúc pattern bằng `\Z`, cả hai chỗ. Thêm `"a\n"` vào `test_name_is_required_and_shorthand_safe`.

### L2. Hai `/api/run` đồng thời cùng qua validate trên một graph
`server/src/cloudy_labs/server/app.py:175,192-196`

`validate` chạy ngoài lock của runner, còn request thứ hai xếp hàng chờ lock. Hai tab (hoặc web cùng một client khác) gửi `create-subnet 10.66.1.0/24` gần như cùng lúc: cả hai qua luật chồng lấn, và cả hai lần chạy. Nếu Floci không tự từ chối CIDR chồng lấn (khác AWS), emulator sẽ có hai subnet chồng nhau. Cùng cơ chế với `attach-internet-gateway` hai lần. **Sửa:** khi `runner.busy` thì trả 409 "một lệnh khác đang chạy" thay vì xếp hàng. Lock vẫn giữ để chống race giữa lúc kiểm và lúc chạy.

### L3. `ran` chuyển thẳng sang `done` khi server không suy được `expect`
`web/src/builder/use-builder.ts:86`; `server/src/cloudy_labs/builder/ops.py:179-189,205-206`

Op tạo tài nguyên, exit 0, nhưng stdout không parse được id (output lạ của Floci, hoặc CLI in cảnh báo trước JSON) → `expect: null` → panel báo "Xong: cảnh đã có thay đổi" dù graph chưa xác nhận gì. Điều này trái tiêu chí "cảnh/phase chỉ đổi sau khi graph xác nhận". **Sửa:** op có `result_id` mà không đọc được id thì trả `expect` dạng "graph version mới", hoặc chuyển sang `failed` với lời giải thích. Chỉ `done` ngay khi op thật sự không có gì để chờ.

### L4. Kéo bị kẹt ở `dragging` khi graph mất `ok` hoặc không có `pointerup`
`web/src/app.tsx:171`; `web/src/scene/pointer-probe.tsx:36-37`

`PointerProbe` chỉ được mount khi `graph.status === 'ok'`. Emulator rớt giữa lúc kéo, hoặc nhả chuột ngoài cửa sổ trình duyệt, hoặc có `pointercancel` (touch, đổi tab), thì không có `onEnd`, và state kẹt ở `dragging` với ghost theo chuột cho tới khi bấm Esc. **Sửa:** nghe thêm `pointercancel`. Trong `useSceneBuilder`, khi `builder` bị gỡ (graph không ok) thì dispatch `cancel`.

### L5. `region_zones` gọi lại emulator ở mọi request khi danh sách AZ rỗng
`server/src/cloudy_labs/server/app.py:75-79`

Khi Floci chưa trả AZ, mỗi preview (debounce 200 ms) và mỗi `/api/lab` lại chiếm một thread để gọi `describe_availability_zones` và chờ timeout của `CLIENT_CONFIG`. **Sửa:** cache cả kết quả rỗng trong vài giây. Kết hợp với M1 (fail closed) để không lộ luật bị bỏ qua.

### L6. Profile `lab` vẫn có thể dùng credential thật hoặc đi tới AWS thật
`server/src/cloudy_labs/emulator/aws_profile.py:43-69`; `server/src/cloudy_labs/cli.py` (serve)

(a) `~/.aws/credentials` có `[lab]` thì key ở đó được ưu tiên hơn key giả trong config. Khi đó lệnh builder ký bằng key thật, và access key id lộ trong log của api-tap. `labctl up` chỉ kiểm config. (b) `endpoint_url` trong config chỉ được AWS CLI v2 ≥ 2.13 hỗ trợ. Với CLI cũ hơn, lệnh dán vào terminal đi tới AWS thật; với key giả thì chỉ lỗi xác thực, nhưng nếu gặp cả (a) thì tạo tài nguyên thật. **Sửa:** `labctl up` cảnh báo khi file credentials có `[lab]`. `labctl serve` kiểm `aws --version` ≥ 2.13 và cảnh báo nếu thấp hơn.

---

## Nit (không phải bug)

- `validate.py:74-77`: `10.0.0.0/016` và `10.0.0.0/255.255.0.0` bị báo "has host bits set", sai lý do (đã tái hiện). Hãy so prefix-length dạng chữ trước, rồi mới nói tới host bits.
- `validate.py:196`: chỉ dùng CIDR chính của VPC. Bỏ qua CIDR phụ, và nếu VPC thiếu `cidr` thì luật "nằm trong VPC" bị bỏ qua mà không báo gì.
- `validate.py:169-172`: route trùng với route `local` (destination bằng CIDR của VPC) không bị bắt, vì collector không vẽ cạnh `local`. Emulator sẽ từ chối và stderr hiện ra, nên chấp nhận được.
- `validate.py:103`: `assert isinstance(...)` biến mất khi chạy `python -O`. Nên dùng `if not isinstance: raise TypeError`.
- `app.py:52`: `_loaded` cache lab mãi mãi; sửa YAML lab thì phải khởi động lại `labctl serve`. Nên ghi chú điều này trong docs hoặc cache theo mtime.
- `aws_profile.py:26`: `AWS_CONFIG_FILE` dạng đường dẫn tương đối được hiểu theo cwd, nên `labctl up` và `labctl serve` chạy ở hai thư mục khác nhau sẽ thấy hai file khác nhau.
- `form-model.ts:48` và `validate.py:146` cùng định nghĩa "EIP còn trống" ở hai nơi. Chấp nhận được vì server là nguồn quyết định, nhưng cần giữ hai bên đồng bộ.

---

## Bảo vệ endpoint ghi: đã kiểm, không có lỗi
- Origin: thiếu, `null` hoặc lạ → 403 trước mọi thứ khác (`app.py:139-140`); có test ở `test_cross_site_writes_are_refused`. `/api/preview` dùng cùng helper nhưng chỉ `/api/run` có test (xem phần thiếu test).
- Content-Type khác `application/json` → 415. Một POST `text/plain` cross-site không qua được. POST `application/json` cross-site cần preflight, và preflight không thành vì app không có CORS middleware; dù vậy Origin vẫn bị chặn trước.
- Body: `set(body) == {"op","params"}`, `params` là dict, op là chuỗi có trong `OPS`, pydantic `extra="forbid"` và không ép kiểu số sang chuỗi. Op ngoài palette của lab → 422.
- Argv: không shell. Mọi id phải khớp đúng một node trong graph. `cidr` và `destination` phải bằng đúng `str(ip_network(...))`. `name` dùng regex (trừ L1). `az` là ngoại lệ duy nhất (M1). Tag của lab dùng `TAG_TEXT` (trừ L1). Không có giá trị nào bắt đầu bằng `-` lọt qua validate, trừ trường hợp M1.
- Vite proxy bind `127.0.0.1` và không đổi Origin, nên thiết bị khác trong LAN không giả Origin qua proxy được.

## Luật validate: đã kiểm
CIDR ngoài VPC (`subnet_of`), chồng lấn (`overlaps`, duyệt qua khay AZ tới VPC), prefix /16–/28, host bits khác 0, IPv6, thiếu prefix, container sai loại, AZ không thuộc region, IGW đã gắn hoặc VPC đã có IGW, NAT trong subnet private, EIP đang được dùng, route khác VPC, IGW chưa gắn, NAT chưa `available`, route trùng destination, subnet đã có association: tất cả đúng và đều có test. ID cạnh trong `expectation` khớp định dạng `link()` của collector (`collector.py:117`).

## Thiếu test
1. `aws_profile`: symlink (H1); comment sau khối lab khi update (M4); config CRLF; `[profile lab]` xuất hiện hai lần.
2. Runner: output một phần khi timeout (M2); huỷ giữa chừng phải kill process group (M3); tiến trình cháu giữ pipe sau `killpg`.
3. App: `azs=[]` với `create-subnet` (M1); 403/415 cho `/api/preview` (hiện chỉ test `/api/run`); `/api/run` khi runner đang bận (L2); `name` có `\n` (L1).
4. Web reducer: `edit` sau `previewed` rồi `run` (H2); `failed` có `problems: []` rồi `edit` rồi `run`; `ran` với `expect: null` cho op tạo tài nguyên (L3).
5. Web: không có test nào cho `useSceneBuilder` hoặc `PointerProbe` (kẹt drag, L4). Phần này hiện chỉ có e2e trình duyệt phủ.

## Theo dõi plan (lead cập nhật, reviewer không sửa plan)
- `plan.md` vẫn ghi mọi phase `Pending` và mọi checkbox Success Criteria chưa đánh dấu, dù code, test và e2e đã có. Lead nên cập nhật trạng thái sau khi xử lý các mục dưới đây.
- Tiêu chí "không làm hỏng file config AWS" chưa đạt hẳn vì H1 và M4. Tiêu chí "mỗi thao tác hiện lệnh đầy đủ trước khi chạy" bị H2 phá trong một khoảng ngắn. Tiêu chí "cảnh/phase chỉ đổi sau khi graph tới" có ngoại lệ L3.
- Plan đã ghi: M3 chỉ đóng sau khi chạy lại e2e với Lab 6 thật (lab đó chưa có).

## Việc nên làm, theo thứ tự
1. H1: resolve symlink trước khi ghi config; thêm test.
2. H2: gắn `previewRev`; Run và Chép chỉ bật khi preview khớp rev của draft; thêm test reducer.
3. M1: luật AZ fail closed khi danh sách rỗng, kiểm hình dạng AZ; thêm test app.
4. M2 và M3: runner đọc stream bằng task riêng và kill process group trong `finally`; thêm hai test.
5. M4: khối lab không nuốt comment; thêm test.
6. L1 (`fullmatch`), L2 (409 khi bận), L3, L4, L5, L6 theo thời gian còn lại.

## Số liệu
- Type coverage: chưa đo; `pnpm typecheck` sạch (lead đã chạy).
- Test: pytest 228 passed, vitest 139 passed, e2e docker 20 bước, `labctl check` 8/8 (theo lead; không chạy lại).
- Lint: ruff sạch (theo lead).

## Câu hỏi còn mở
- Floci có từ chối `create-subnet` khi CIDR chồng lấn không? Nếu không, L2 nên nâng lên Medium.
- Có cần hỗ trợ AWS CLI < 2.13 không? Câu trả lời quyết định L6(b) chỉ là cảnh báo hay là điều kiện chặn khi `labctl serve`.

---

## Xử lý (lead, 2026-10-29)

| Mục | Cách xử lý | Test |
|---|---|---|
| H1 | `ensure_lab_profile` ghi vào `config_path().resolve()`, nên symlink giữ nguyên và file đích được sửa. | `test_aws_profile`: symlink |
| H2 | Form giữ `previewRev`. `previewCurrent` chỉ đúng khi preview khớp rev của draft. Reducer và hook đều từ chối `run` khi preview cũ. Panel làm mờ lệnh cũ và khoá Chép/Run. | `use-builder.test`: sửa rồi run; failed → sửa → run |
| M1 | Luật AZ fail closed khi danh sách rỗng ("could not read this region's Availability Zones…"). | `test_builder_validate`, `test_app`: AZ không đọc được → 409 |
| M2 | Runner đọc stdout và stderr bằng hai task riêng. Hết giờ thì vẫn trả output đã có, kèm ghi chú timeout. | `test_runner`: output một phần khi timeout |
| M3 | `finally` kill process group khi lệnh chưa xong (kể cả khi bị huỷ), rồi chờ có `shield`. | `test_runner`: huỷ không để lại tiến trình |
| M4 | Khối lab chỉ gồm dòng đánh dấu và các dòng không rỗng, không bắt đầu bằng `[`, `#`, `;`. Comment và dòng trống trước section kế tiếp giữ nguyên. | `test_aws_profile`: comment trên section kế tiếp |
| L1 | `NAME` và `TAG_TEXT` dùng `fullmatch`. | `test_builder_validate`, `test_schema`: tên có `\n` |
| L2 | `/api/run` trả 409 khi runner đang bận, kiểm ngay trước khi chạy. Không xếp hàng. | `test_app`: bận → 409 |
| L3 | `expectation` không bao giờ trả `None`; không đọc được id thì trả `{"after": version}` (version của graph trước khi chạy), web chờ graph mới hơn. | `test_builder_ops`, `use-builder.test`: `after` |
| L4 | `PointerProbe` nghe `pointercancel`. `useSceneBuilder` huỷ thao tác đang dở khi cảnh mất kết nối emulator. | Chỉ có e2e trình duyệt phủ |
| L5 | AZ rỗng được thử lại, nhiều nhất mỗi 5 giây (`AZ_RETRY_S`). | `test_app` |
| L6 | Chọn chặn chứ không chỉ cảnh báo: `run_blocker()` khoá Run khi thiếu `aws`, CLI < 2.13, hoặc file credentials có `[lab]`. `/api/lab` trả `runBlocker`, `/api/run` trả 503, panel hiện lý do. `labctl up`/`serve` cảnh báo. | `test_aws_profile`: credentials, version CLI; `test_app`: runBlocker |
| Nit | Thông báo prefix dạng chữ ("write the prefix length as a number…"); `assert` thành `TypeError`. | `test_builder_validate`: `/024`, netmask |
| Thiếu test (3) | Thêm 403/415 cho `/api/preview`. | `test_app` |

Chưa làm: config CRLF và `[profile lab]` xuất hiện hai lần (chưa thấy trường hợp thật); test đơn vị cho `useSceneBuilder`/`PointerProbe`.

Câu hỏi còn mở vẫn mở: Floci có từ chối CIDR chồng lấn không (validate đã chặn ở phía builder, nên lệnh chạy tay mới gặp); AWS CLI < 2.13 hiện bị coi là không hỗ trợ cho Run.

Sau khi sửa: pytest 247 passed, ruff sạch, vitest 141 passed, typecheck sạch, `check-builder.mjs` 22/22.
