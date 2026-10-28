# Tóm tắt giấy phép phụ thuộc (Phase 4), 2026-10-27

**Kết luận:** không có gói nào thuộc nhóm "Chặn" hoặc "không rõ giấy phép". Có 3 gói thuộc nhóm "Cần xem xét" (MPL-2.0), và cả 3 đều dùng không sửa đổi được. A8 (phân phối thương mại cùng sản phẩm MIT) không bị chặn bởi phụ thuộc nào đã kiểm.

Nguồn dữ liệu:
- npm: `spikes/m0-licenses/npm-licenses.json`, từ `pnpm licenses list --json` chạy trong `spikes/m0-render/`, gồm cả phụ thuộc gián tiếp và devDependencies; 95 gói.
- Python: `spikes/m0-licenses/python-licenses.json`, từ `pip-licenses --format=json --with-urls` trong một venv tạm (đã xoá). Venv cài fastapi, uvicorn, boto3, pyyaml, httpx, aiohttp, anthropic, openai, `moto[server]==5.2.4`; 84 gói, không tính bản thân pip-licenses và phụ thuộc của nó.

## npm (95 gói)

| Giấy phép | Số gói | Nhóm | Ghi chú |
|---|---|---|---|
| MIT | 76 | Cho phép | three, @react-three/*, @react-spring/*, react, vite… |
| Apache-2.0 | 9 | Cho phép | typescript 7.0.2, playwright-core (chỉ dùng để đo), draco3d, hls.js, @mediapipe/tasks-vision, @dimforge/rapier3d-compat (phụ thuộc tuỳ chọn của drei)… |
| ISC | 5 | Cho phép | n8ao 2.0.1, picocolors, potpack… |
| BSD-3-Clause | 2 | Cho phép | ieee754, source-map-js |
| Zlib | 1 | Cho phép | postprocessing 6.39.5. Zlib là giấy phép dễ dãi tương tự MIT; bảng phân loại của plan chưa liệt kê, nên bổ sung vào nhóm "Cho phép" |
| MPL-2.0 | 2 | Cần xem xét | lightningcss 1.33.0 (+ bản nhị phân darwin-arm64), phụ thuộc lúc build của Vite. Không nằm trong bundle phát hành. Dùng không sửa đổi thì không có nghĩa vụ gì thêm |

## Python (84 gói)

| Giấy phép | Số gói | Nhóm | Ghi chú |
|---|---|---|---|
| MIT / MIT License / MIT-0 | 31 | Cho phép | fastapi, pyyaml, anyio, cffi, cfn-lint (MIT-0)… |
| Apache-2.0 / Apache Software License | 20 | Cho phép | boto3, botocore, moto, openai, anthropic, requests… |
| Apache-2.0 kết hợp với MIT, BSD hoặc CNRI-Python | 5 | Cho phép | aiohttp (Apache-2.0 AND MIT), cryptography (Apache-2.0 OR BSD-3-Clause), python-dateutil, sniffio, regex (Apache-2.0 AND CNRI-Python; CNRI-Python là giấy phép dễ dãi, tương thích phân phối thương mại) |
| BSD / BSD-2 / BSD-3 | 25 | Cho phép | httpx, uvicorn, starlette, Flask, Jinja2, sympy, networkx… |
| PSF-2.0 / Python Software Foundation License | 2 | Cho phép | typing_extensions, aiohappyeyeballs |
| MPL-2.0 | 1 | Cần xem xét | certifi (gián tiếp qua httpx/requests). Dùng không sửa đổi; nếu sửa bundle CA thì phải công bố phần sửa đó |

Gói lớn nhất kéo vào là `moto[server]` (cfn-lint, sympy, networkx, Flask, docker…). moto chỉ chạy cục bộ như một backend; nếu Cloudy Labs không phân phối kèm moto thì các gói này không nằm trong bản phát hành. Gói nào có metadata không chuẩn (ví dụ "BSD" chung chung của antlr4-python3-runtime) đã được đối chiếu tay: antlr4 dùng BSD-3-Clause theo repo antlr/antlr4.

## Emulator, font và icon

| Thành phần | Phiên bản ghim | Giấy phép | Nguồn đã đọc |
|---|---|---|---|
| Floci | 2.3.0 | MIT | `https://raw.githubusercontent.com/floci-io/floci/2.3.0/LICENSE` |
| MiniStack | v1.5.33 | MIT | `https://raw.githubusercontent.com/ministackorg/ministack/v1.5.33/LICENSE` |
| moto | 5.2.4 | Apache-2.0 | `https://raw.githubusercontent.com/getmoto/moto/5.2.4/LICENSE` |
| Be Vietnam Pro | bản trong `google/fonts` (2021) | OFL-1.1 | `spikes/m0-render/public/fonts/BeVietnamPro-OFL.txt`; được nhúng và phân phối kèm phần mềm, chỉ không được bán font riêng lẻ, và bản sửa đổi không được dùng tên font gốc |
| AWS Architecture Icons | không dùng | không phân phối | Giữ quyết định F3.8: icon tự vẽ là mặc định. Spike này chỉ dùng icon SVG tự vẽ (`spikes/m0-render/src/scene/icons.ts`) |

Lưu ý ngoài phạm vi lockfile:
- Image Docker mà Floci kéo lúc chạy (`public.ecr.aws/amazonlinux/amazonlinux:2023`, `alpine/socat`) do máy người học tải trực tiếp, Cloudy Labs không phân phối lại. Nếu sau này Cloudy Labs đóng gói sẵn các image này (cài offline), cần kiểm tra lại giấy phép của chúng; Amazon Linux có nhiều gói GPL.
- Kiểm tra này dựa trên metadata khai báo của gói, không quét nội dung từng file (ví dụ file vendor bên trong gói).

## Việc cần làm sau này

- Sinh `THIRD_PARTY_NOTICES` từ hai file JSON trước bản phát hành đầu tiên.
- Ghi điều kiện "không sửa đổi" cho lightningcss và certifi trong tài liệu phát hành.
