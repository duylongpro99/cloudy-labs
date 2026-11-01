---
phase: 4
title: "Nội dung lab cục bộ: lý thuyết và hint"
status: completed
priority: P2
effort: "14h"
dependencies: [3]
---

# Phase 4: nội dung lab cục bộ, lý thuyết và hint

## Goal

App hiển thị phần lý thuyết của lab, mỗi heading H2 một tab, cùng hint. Nội dung lấy từ file cục bộ, không bao giờ vào git và không bao giờ được gửi sang provider LLM.

## Hiện trạng

- `/api/lab` (`server/app.py:174-199`) trả task và một số trường khác, nhưng không trả hint.
- Hint nằm trong `lab.yaml` (`labs/schema.py:144`), được validate nhưng không dùng ở đâu.
- Web hiển thị task dạng text thuần trong `twin/check-panel.tsx`; chưa có trình render markdown.
- Người dùng chọn: nội dung labaws.site chỉ dùng cá nhân, không commit; mỗi H2 một tab (2026-10-31).

## Thiết kế

- Mỗi lab là một thư mục `labs/<slug>/`:
  - `lab.yaml` và `checks.py` được commit;
  - `content/` bị gitignore. Trong đó có `content/lab.md` (markdown người dùng dán), `content/hints.yaml` và ảnh nếu có.
- **[Red team] Tab theo H2.**
  - `content.py` tách `lab.md` theo heading cấp 2. Mỗi tab có `title` (text của heading) và `markdown`. Phần trước H2 đầu tiên là tab "Giới thiệu".
  - Không có bảng vai trò mục, không có `content.sections`, không có `tasks[].section`.
- **[Red team] Hint của lab labaws** nằm trong `content/hints.yaml` (gitignore), dạng `{task_id: [hint...]}`, vì hint viết theo nội dung lab cũng là nội dung phái sinh.
  - Hint trong `lab.yaml` vẫn dùng được cho lab tự viết (fixture 06/07).
  - Khi cả hai cùng có, `content/hints.yaml` thắng.
- `/api/lab` trả thêm:
  - `hints` theo task;
  - `content`: danh sách tab `{title, markdown}` khi có `content/lab.md`, hoặc `null`.
- **[Red team] Endpoint ảnh** `GET /api/lab/content/{name}`:
  - chỉ phục vụ lab đang mở;
  - `name` khớp `^[A-Za-z0-9._-]{1,100}\.(png|jpg|jpeg|gif|webp|svg)$`;
  - đường dẫn `resolve()` phải `is_relative_to(labs/<slug>/content)`;
  - SVG trả kèm header `Content-Security-Policy: sandbox` và `X-Content-Type-Options: nosniff`;
  - GET đi qua TrustedHost như các route GET khác.
- **[Red team] Ảnh từ S3 presigned URL** trong markdown dán vào: `content import` bỏ query string `X-Amz-*` khỏi URL, và tải ảnh vào `content/` nếu người dùng chọn `--fetch-images`. Web không bao giờ tải URL ngoài; link ngoài chỉ hiện dạng link.
- Web có panel "Bài lab" gồm các tab theo H2.
  - Markdown được render bằng `react-markdown` + `remark-gfm` (cho bảng). Không cho HTML thô.
  - Ảnh chỉ trỏ tới `/api/lab/content/...`.
  - Hint nằm sau nút "Gợi ý" trong panel check.
- **[Red team] Không gửi nội dung lab sang chat.** `chat/prompt.py` không đọc `content/`. Có test khẳng định prompt sinh ra không chứa chuỗi nào của `lab.md` mẫu.
- `.gitignore` thêm `labs/*/content/`. Một test server kiểm `git check-ignore` trả đúng cho đường dẫn đó.
- **[Red team] Kiểm tra rò rỉ n-gram:** script `server/scripts/check-content-leak.py`.
  - Script lấy mọi n-gram 8 từ trong `labs/*/content/**/*.md` cục bộ và tìm chúng trong mọi file được git track.
  - Có trùng thì script in đường dẫn file và số lượng, không in đoạn trùng, rồi thoát với mã lỗi.
  - Chạy thủ công trước mỗi commit lab, và chạy ở Phase 11.
- `labctl content import <slug> <file.md> [--fetch-images]`: validate slug (Phase 3), chép file vào đúng chỗ, rồi in danh sách tiêu đề tab.

## Files to Create / Modify

- Modify: `.gitignore`.
- Modify: `server/src/cloudy_labs/labs/loader.py` (đọc tab và `hints.yaml`), `server/app.py` (`/api/lab`, endpoint ảnh), `cli.py` (`content import`).
- Create: `server/src/cloudy_labs/labs/content.py` (tách markdown theo H2, bỏ `X-Amz-*`).
- Create: `server/scripts/check-content-leak.py`.
- Create: `server/tests/test_lab_content.py`. Dùng markdown mẫu tự viết, không dùng nội dung thật. Gồm test tách tab, hint, endpoint ảnh (slug sai, `../`, đuôi lạ, SVG có CSP), gitignore và prompt chat không chứa nội dung.
- Create: `web/src/lab/lab-panel.tsx`, `web/src/lab/lab-panel.test.tsx`.
- Modify: `web/src/twin/check-panel.tsx` (nút gợi ý), `web/package.json` (`react-markdown`, `remark-gfm`; ghi giấy phép MIT).
- Modify: `docs/labctl.md`.

## Tasks & Steps

1. Loader: tách tab H2 và đọc `hints.yaml`.
2. Endpoint `/api/lab` và endpoint ảnh, kèm test an toàn đường dẫn.
3. CLI `content import`: bỏ query presigned, `--fetch-images`.
4. Panel web, nút hint, test render bảng và chặn HTML thô.
5. Test gitignore, test prompt chat và script kiểm rò rỉ.

## Verification

- `cd server && uv run pytest tests/test_lab_content.py tests/test_schema.py tests/test_app.py tests/test_chat_prompt.py -q`
- `cd web && npm test && npm run typecheck`
- `git check-ignore labs/x/content/lab.md` in ra đường dẫn.
- `cd server && uv run python scripts/check-content-leak.py` thoát 0 trên repo hiện tại.

## Risk / Rollback

- Markdown labaws.site có thể chứa HTML thô. Không render HTML; HTML hiện dạng text.
- Không có `content/` thì panel chỉ hiện task; app chạy bình thường.
