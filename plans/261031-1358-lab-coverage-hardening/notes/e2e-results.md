# Kết quả nghiệm thu M7 (2026-11-01)

Chạy trên Apple M1 Pro, Docker Desktop, Floci và moto theo `server/src/cloudy_labs/emulator/compose.yaml`. Mỗi lần chạy, máy còn các container khác không thuộc dự án (load average khoảng 5–6).

| Kiểm tra | Lệnh | Kết quả |
|---|---|---|
| Unit server | `cd server && uv run pytest -q` | 904 passed, 136 deselected (docker, llm) |
| Lint server | `uv run ruff check src tests` | sạch |
| Web | `cd web && pnpm test`, `pnpm typecheck` | 599 passed (28 file); typecheck sạch |
| Contract registry trên Floci | `uv run pytest -q -m docker tests/test_registry_contract_docker.py` | 103/105 kind đạt. Hai kind trượt chỉ vì thời gian: `tgw-route-table` create 2,09 s và `efs-file-system` `put-backup-policy` 2,33 s, ngưỡng 2,0 s. Lần chạy trước trượt ở hai kind khác (`efs-mount-target` 2,07 s, `glue-crawler` 2,59 s). Bước kết quả: 224 pass, 56 no-op, 2 slow. Ngưỡng giữ nguyên. |
| Lab 6/7 qua builder | `uv run pytest -q -m docker tests/test_builder_e2e_docker.py` | 4 passed; `labctl check` 7/7 |
| Bench 200 node (NFR2) | `BENCH_RESULTS_DIR=… pnpm dev` + `node scripts/run-chrome-bench.mjs` | Chrome, 16 cấu hình: p95 khung hình 9,0–9,5 ms, 120 fps (trần vsync), kể cả 20 ghost và bộ kind trộn; idle 0 khung hình. Số liệu ở [bench/](./bench/). |
| Rò nội dung labaws | `cd server && uv run python scripts/check-content-leak.py` | exit 0 (máy chưa có `labs/*/content/`, nên kiểm tra này chưa có gì để so) |
| Catalog | `uv run labctl coverage --catalog … --json` | 530 lab: ready 1, ready-with-caveats 468, blocked 61, gap 0 |

## Chưa chạy

Bước 1–4 của Phase 11 (nhập nội dung lab-001, dựng RDS qua builder, `labctl check`, đối chiếu với trang labaws) cần người dùng tải nội dung lab-001 vào `labs/lab-001/content/`. Máy chưa có thư mục `labs/`.
