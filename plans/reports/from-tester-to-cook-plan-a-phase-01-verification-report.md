# Báo cáo kiểm chứng Plan A phase 1 (Preflight và quyết định, mốc M0)

Ngày: 2026-10-23. Người kiểm: tester (độc lập, chỉ đọc + chạy lệnh; không sửa file nào trong repo).
Không đọc root `.env`. Không chạy probe LLM live. Không chạy `npm run build`.

## Bảng kiểm tra

| # | Kiểm tra | Kết quả | Bằng chứng |
|---|----------|---------|------------|
| 1 | `bash scripts/check.sh` | PASS | exit 0. ruff: "All checks passed!". pytest: "4 passed in 0.44s". pip-audit: "No known vulnerabilities found". frontend typecheck: OK. npm audit high: "found 0 vulnerabilities". Bị bỏ qua: alembic check (không có `backend/alembic.ini`), frontend tests (không có script `test`). |
| 2a | Parse `scripts/check.ps1` bằng PowerShell Parser | PASS | "PARSE OK, errors=0" |
| 2b | `powershell -File scripts/check.ps1 -SkipAudit -SkipFrontend` | PASS | exit 0. ruff và pytest (4 passed) OK. Dòng tiếng Việt cuối bị mojibake trên console (xem concern C2). |
| 3 | `spike_mcp_identity.py` chạy 3 lần | PASS | 3/3 exit 0, 3/3 in "SPIKE PASS", 0 giá trị `false` trong `as_expected` (9/9 true mỗi lần). Kết quả: valid OK; no_header REJECTED (missing context); expired REJECTED; tampered args REJECTED; wrong key REJECTED; replay lần 1 OK, lần 2 REJECTED (replay); ký lúc emit rồi chờ > TTL REJECTED (expired); ký lúc thực thi sau khi chờ OK. Có traceback `ConnectionResetError WinError 10054` từ asyncio khi shutdown server: nhiễu, không làm fail. |
| 4 | OpenAPI `docs/api/openapi-v0.yaml` | PASS (validate), FAIL (đủ endpoint) | `openapi: 3.1.0`, `openapi_spec_validator.validate` = OK. 24 `$ref`, 0 không resolve. 22 schema, 32 path, 33 operation. Thiếu so với phase 7 (xem bên dưới). |
| 5 | `spike_langgraph.py` trên pgvector:pg17 tạm | PASS | container `tester-pg` chạy, `pg_isready` sẵn sàng sau 3s. Exit 0, "SPIKE PASS". Cả 3 nhóm (context/interrupt, store TTL + sweeper, stream theo node) đều đúng. Đã `docker rm -f tester-pg`, không còn container. |
| 6 | `backend/scripts/probe-report.json` | PASS | Tồn tại, 5716 byte, JSON hợp lệ (phải đọc UTF-8). Quét secret (api key, token, password, bearer, `sk-`, URL có credential): 0 khớp. Host chỉ là `your-api-model-host`. `verdict`: go=true, overall=1.0, threshold=0.95. `group_pass_rates`: tool_calling 1.0, structured_output 1.0, language 1.0, streaming 1.0. `latency p50` 0.32 (khớp phase). `embedding`: 1024 dims, vi OK, quá giới hạn trả BadRequestError (khớp phase). 10 kịch bản x 3 lần. |
| 7a | `pytest -q` | PASS | 4 passed in 0.50s |
| 7b | `uv lock --check` | PASS | "Resolved 106 packages", exit 0 |
| 7c | `uv sync --frozen --no-dev --no-install-project --dry-run` | PASS | exit 0. Chỉ liệt kê gói dev sẽ bị gỡ (pytest, ruff...). Lệnh Dockerfile resolve được. |
| 8 | Dọn dẹp | PASS (có ghi chú) | Không còn `tester-pg`. Không có LISTENING trên 18765, 55433, 55434 (chỉ còn TIME_WAIT, bình thường). Bốn container compose (`agent-demo-frontend-1`, `-api-1`, `-mcp-server-1`, `-db-1`) vẫn chạy, không bị đụng. Xem C4 về một process python lạ. |

## Lỗi / rủi ro cần xử lý

**F1 (FAIL, mức trung bình): OpenAPI v0 thiếu 4 endpoint mà phase 7 liệt kê trong v0.** Phase 1 nói "đóng băng OpenAPI v0" làm hợp đồng cho frontend.
- `GET /v1/me/memory/{key}` (phase 7 ghi `GET/DELETE /v1/me/memory[/{key}]`; spec chỉ có DELETE)
- `GET /v1/me/refunds/{id}` (phase 7: `GET /v1/me/refunds[/{id}]`)
- `GET /v1/me/tickets/{id}` (phase 7: `GET /v1/me/tickets[/{id}]`)
- `GET /v1/staff/tickets/{id}` (phase 7: `/v1/staff/tickets?status=` `/{id}`)

Tái hiện: liệt kê path trong `docs/api/openapi-v0.yaml` và so với bảng endpoint ở `phase-07-api-v2.md` dòng 30-40.

Ngược lại, spec có thêm `/health`, `/v1/products[/{slug}]`, `/v1/auth/*` (5 operation). Không có trong bảng phase 7, nhưng phase 7 nói "trừ catalog + /health" và phase 4 chứa auth, nên đây là thông tin, không phải lỗi.

**Fix đề xuất:** thêm 4 GET vào spec, hoặc ghi rõ trong phase 7 rằng các GET chi tiết đó nằm ngoài v0.

## Concern (không chặn M0)

- **C1. Gate `check.sh` yếu hơn mô tả.** Phase nói pytest chạy trên Postgres của compose, nhưng suite chỉ có 4 test trong `backend/tests/test_agent_graph.py`, không có tham chiếu DB. Alembic check và frontend tests bị bỏ qua êm (không báo). Ruff chỉ bật `E9,F`.
- **C2. `scripts/check.ps1` không có UTF-8 BOM** (byte đầu `23 20 43`). Windows PowerShell 5.1 đọc file không BOM theo codepage ANSI, nên chuỗi tiếng Việt sẽ bị mojibake. Parser hiện không báo lỗi, nhưng nên thêm BOM hoặc chuyển toàn bộ chuỗi sang ASCII.
- **C3. Probe kịch bản `lang_vi` đạt 100% nhưng không kiểm tính đúng sự thật.** Output mẫu: "chính sách đổi trả ... trong vòng 7 ngày", trong khi không có KB. Đây là bịa chính sách, phase đã cảnh báo. Probe chỉ đo ngôn ngữ, không đo grounding. Cần kịch bản có KB để chứng minh guard hoạt động.
- **C4. Process lạ còn chạy:** PID 24740, `C:\Python314\python.exe -X utf8 ...\scratchpad\mock_api.py` (parent 17376). Không do các spike của phase này tạo ra. Tôi không kill. Cần chủ sở hữu xác nhận.
- **C5. Một số bằng chứng trong "Kết quả thực thi" không có trong repo:** thử `unaccent` (cần hàm IMMUTABLE bọc), quyền `CREATE EXTENSION vector` (superuser), và các lỗi công cụ (pip-audit bị chặn, uvx). Repo chỉ có 3 script trong `backend/scripts/`, không có script nào cho `unaccent` hay quyền extension. Không kiểm lại được.
- **C6. Rủi ro sản phẩm đã biết:** `backend/app` không có `enable_thinking` (grep = 0 khớp). Model là loại thinking, nên code hiện tại có thể rò suy luận ra khách. Phase đã ghi nhận và giao cho phase 6, nên không tính là lỗi của phase 1.
- **C7. Không verify được "spike chỉ thêm script, không đổi code sản phẩm"** vì thư mục không phải git repo. Mtime `backend/app` (09:09-09:10) có trước các spike, gợi ý là không đổi, nhưng chưa chứng minh.
- **C8. Nhiễu trong phase doc:** frontmatter `status: pending` dù kết quả là GO. Success Criteria chưa tick `[ ]` trong khi Todo đã tick `[x]`. Dòng "≥ 95% kịch bản đạt" bị lặp.
- Nhỏ: docstring `spike_langgraph.py` có DSN mẫu `postgres:t@localhost` (mật khẩu throwaway, không phải secret thật). Không cần sửa.

## Tổng kết

**Status:** DONE_WITH_CONCERNS

**Summary:** Toàn bộ gate chạy tay đều PASS: check.sh (exit 0), check.ps1 parse và chạy (exit 0), MCP identity 3/3 PASS, LangGraph PASS trên Postgres tạm, probe-report khớp phase, uv lock và sync frozen OK, dọn dẹp sạch. Điểm fail: OpenAPI v0 thiếu 4 GET endpoint so với phase 7, nên contract chưa đủ để frontend đóng băng.

**Concerns/Blockers:** Không có blocker cho M0. Cần sửa F1 (OpenAPI thiếu 4 endpoint) trước khi coi contract là đóng băng. Các mục C1-C5 nên xử lý trước phase 2.

## Câu hỏi chưa giải quyết

1. Bốn GET thiếu trong OpenAPI có cố ý để ngoài v0 không? Nếu có, phase 7 cần ghi rõ.
2. Process PID 24740 (`scratchpad/mock_api.py`) là của ai, có cần dừng không?
3. Gate "pytest trên Postgres" hiện không kiểm DB. Có cần thêm test DB sớm hay chấp nhận đến phase 2?
4. Có cần thêm UTF-8 BOM cho `check.ps1` không, hay chuyển sang ASCII?
5. Bằng chứng thử `unaccent` và quyền `CREATE EXTENSION` có lưu ở đâu để tái kiểm không?
