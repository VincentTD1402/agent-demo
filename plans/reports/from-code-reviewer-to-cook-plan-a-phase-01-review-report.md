# Review Plan A phase 1 (Preflight and decisions)

Phạm vi: probe_model.py, spike_mcp_identity.py, spike_langgraph.py, probe-report.json, scripts/check.{sh,ps1}, docs/api/openapi-v0.yaml, pyproject.toml, uv.lock, phần "Kết quả thực thi" + plan.md "Kết quả M0". Không đọc .env gốc. Không có git repo, nên "app không đổi" xác minh gián tiếp (xem b).

## Kết luận
Không có Critical. Có 3 High (spike chưa chứng minh đúng một số tuyên bố, OpenAPI v0 sẽ buộc đổi hợp đồng, check thiếu typecheck/lint scripts). Phần lớn tiêu chí đạt; còn vài mục chưa đóng.

## (a) Tiêu chí chấp nhận phase 1
| Bước | Trạng thái |
|------|-----------|
| 1 probe | Một phần. Không gọi `/v1/models` (phase-01.md:24). "Quá 2048 token trả lỗi gì" chỉ ghi `type(e).__name__` (probe_model.py:186), không ghi status/message. |
| 2 chất lượng vi/en/trộn | Thiếu kịch bản **trộn** vi+en; chỉ có 1 câu en, 1 câu vi (probe_model.py:124-133). Không test vòng tool-result -> trả lời cuối, không test streaming kèm tool call. |
| 3 spike MCP | Đạt, xem (e). |
| 4 spike LangGraph | Đạt phần context/interrupt/TTL/pool/stream node. `start_ttl_sweeper` chỉ kiểm `hasattr` (spike_langgraph.py:86), chưa chạy thật. `stream_mode="messages"` không thử; chỉ `updates` (:106). Phase-01.md:27 yêu cầu "messages lọc theo node". Phát hiện 5 trong báo cáo ghi "stream `updates`" - ngầm đổi yêu cầu mà không giải thích. |
| 5 unaccent/CREATE EXTENSION | Chỉ có kết luận trong văn bản (phase-01.md:70), **không có script/chứng cứ tái lập** trong repo (spike_langgraph.py không chạy unaccent). Cần ít nhất một đoạn SQL hoặc ghi cách tái lập. Tuyên bố hợp lý (unaccent là STABLE; vector không trusted) nhưng chưa kiểm chứng được từ repo. |
| 6 deps + uv.lock | Đạt. `uv lock --check` -> 106 packages, nhất quán. |
| 7 quy trình test trên Postgres compose | **Chưa đóng.** Không có ghi nhận Docker Desktop/WSL2 ở phần kết quả; `scripts/check` không kiểm Docker/Postgres; `backend/tests/test_agent_graph.py` dùng InMemorySaver nên chưa chứng minh gì về Postgres. |
| 8 script check | Một phần: thiếu **typecheck backend** (mypy/pyright) dù phase-01.md:31 liệt kê "typecheck"; ruff chỉ chạy `backend` (check.sh:12, check.ps1:13), không phủ `scripts`. Ngưỡng 95% có trong code (probe_model.py:18). |
| 9 OpenAPI v0 | Có, nhưng xem (g). |
| 10 câu hỏi cho chủ shop | **Không thấy** danh sách câu hỏi mở (số ngày hoàn tiền, KB, đội ngũ, đối soát) trong phần kết quả hay plan.md "Kết quả M0". Gap. Lưu ý probe còn cho thấy model tự bịa "đổi trả 7 ngày/14 ngày" (probe-report.json:153,171), càng cần chốt chính sách. |
| Bookkeeping | phase-01.md:8 `status: pending` và Success Criteria (:45-47) vẫn `[ ]` dù Todo đã `[x]`; :45 có lặp "≥ 95% kịch bản đạt; ≥ 95% kịch bản đạt". |

## (b) Không hồi quy
- Không có git nên không diff được. Gián tiếp: mtime file trong backend/app đều <= 09:10, trước pyproject/uv.lock (11:26), Dockerfile/compose/.env.example mtime 09:02; không file nào mới hơn sau giai đoạn phase 1. Chấp nhận là không đổi (confidence ~85%; xác nhận chắc chắn bằng diff của bên điều phối).
- Dockerfile: `uv sync --frozen --no-dev --no-install-project` (Dockerfile:16). `uv export --no-dev` cho thấy pytest/ruff/pip-audit **không** vào prod; httpx có mặt vì là phụ thuộc bắc cầu của runtime (không phải rò dev). pyjwt 2.15.1, argon2-cffi 25.1.0 (+bindings 26.1.0, có wheel win/linux/musl), cryptography 50.0.2 đều có trong lock. Không build Docker thật trong review này (chưa chạy được); rủi ro thấp vì `--frozen` + lock khớp.
- **Medium:** pyjwt/argon2/cryptography là runtime deps "dự phòng" khi chưa có code dùng (YAGNI; tăng bề mặt image + pip-audit). Chấp nhận vì phase 4/7 sắp dùng, nhưng spike_mcp_identity.py cũng cần `pyjwt` nên `pyjwt` là hợp lý.
- **Low:** `openai` được import trực tiếp (probe_model.py:15) nhưng không khai báo trong pyproject (chỉ bắc cầu qua langchain-openai). Hoạt động nhưng mong manh khi nâng langchain-openai; nên khai báo hoặc dùng `langchain_openai`/httpx.

## (c) Hợp đồng công khai / cấu hình
- Biến môi trường/config của app không đổi. Script đọc: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY` (cùng tên với backend/app/config.py:12-22, khớp) qua `.env` tương đối theo CWD (probe_model.py:23) -> phải chạy từ gốc repo, nếu không báo thiếu biến (Low; nên ghi trong docstring, đã có lệnh chạy nhưng không nói rõ CWD).
- Biến mới: `SPIKE_DATABASE_URL` (bắt buộc, `os.environ[...]` ném KeyError thô nếu thiếu - spike_langgraph.py:25; Low, nên in hướng dẫn). Không thêm vào .env.example (đúng, chỉ dùng cho spike).

## (d) Secret
- probe-report.json: không có key/secret. Có `llm_host: your-api-model-host` (:2) - tên host nội bộ, **Low**: cân nhắc bỏ nếu repo công khai. Có mẫu nội dung model, không nhạy cảm.
- Scripts không in giá trị env; ProbeSettings.llm_api_key mặc định "not-needed". Lỗi in `str(e)[:160]` có thể chứa URL/chi tiết server (probe_model.py:181, 206) nhưng OpenAI SDK không đưa API key vào message; chấp nhận.
- Key spike: `"spike-context-key-" + "x"*32`, `"another-key-"+...` (spike_mcp_identity.py:23-24), rõ ràng là giả. OK.

## (e) Độ đúng của spike
spike_mcp_identity.py
- Server-side fail-closed: **đúng về cấu trúc.** `verify()` (:45-56) chạy trong tool, thiếu header -> lỗi, `jwt.decode` ép `algorithms=["HS256"]`, `aud`, bắt buộc `exp/aud/jti`; danh tính chỉ lấy từ token. Mọi lỗi (kể cả JWT) -> exception -> adapter trả "Error executing tool".
- **High (false-positive PASS):** nhánh REJECTED chỉ kiểm chuỗi "Error executing tool"/exception (:96-101, :131) **không kiểm lý do**. Lỗi mạng/server/hết kết nối cũng được tính là REJECTED nên các ca âm (expired, tampered, wrong_key, no_header, replay_second, pre_signed) có thể PASS vì nguyên nhân sai. Chỉ các ca "OK" bảo vệ gián tiếp (nếu server chết thì ca valid FAIL), nhưng không loại trừ lỗi khác chỉ ảnh hưởng ca âm (vd. interceptor ném lỗi trước khi gửi). Sửa: server ghi `reason` (expired/mismatch/replay/missing/bad_sig) vào danh sách kiểm; so khớp từng ca với lý do mong đợi.
- **Medium:** `args_hash` chỉ phủ `args` đã sort; danh tính (user_id, thread_id, tool, aud, exp) phủ qua claim đã ký. Phần plan yêu cầu ràng buộc; nhưng `thread_id` cứng `"t-1"` (:36) và server không so với bất cứ giá trị nào, nên **chưa chứng minh ràng buộc thread/user với yêu cầu thực**; user_id/thread_id chỉ được "đọc ra", không đối chiếu. Phase 5 phải kiểm. Ngoài ra hash theo `json.dumps` Python: Hợp đồng chéo ngôn ngữ chưa xét (ok cho spike).
- jti replay: `seen_jti` set trong bộ nhớ, kiểm+thêm đồng bộ không có `await` giữa -> nguyên tử trong một event loop; chấp nhận cho spike. **Medium cho phase 5**: không giới hạn kích thước, không TTL, mất khi restart, không chia sẻ giữa nhiều worker/replica (compose chạy mcp 1 tiến trình?), jti chỉ thêm *sau* khi đối chiếu nên hợp lệ; cần cache có TTL=exp hoặc bỏ replay nếu TTL ngắn + idempotency ở tool ghi.
- `exp = iat + 2s` không leeway, `signed_at_emission_then_waited` đợi 3s -> chứng minh đúng việc ký lúc phát thì hết hạn; nhưng **không chứng minh "sau resume"** (không có LangGraph interrupt/resume trong spike MCP) - tuyên bố "chịu được resume trễ" suy ra gián tiếp (interceptor gọi lúc thực thi). Chấp nhận, nên ghi rõ giới hạn.
- Flaky: server khởi động bằng `sleep(1.5)` (:107) thay vì thăm dò cổng; cổng cứng 18765 -> xung đột có thể cho kết quả sai (Low-Medium).
- Windows: uvicorn trong thread (không có signal handler) ổn; loop mặc định Proactor, không cần Selector vì không dùng psycopg. Nhóm `logging.disable(INFO)` ẩn cả log lỗi hữu ích khi debug.

spike_langgraph.py
- Windows: SelectorEventLoop được ép (:129) đúng; nhưng `asyncio.run(..., loop_factory=)` yêu cầu Python 3.12 (đã ghim 3.12) - ok.
- **Medium:** biến toàn cục `seen` dùng để suy luận context; ca "resume không truyền context" chỉ chứng minh `runtime.context is None` khi `seen["after_resume"]` được ghi - nếu node không chạy lại (vd. lỗi) `seen["after_resume"]` giữ giá trị cũ (lần chạy trước không có) nên `ctx_without is None` có thể PASS vì chưa từng ghi (khởi tạo `seen={}` -> KeyError, không phải None, nên thực tế sẽ ném lỗi -> bắt ở :118; chấp nhận). Tuy nhiên nhánh `ctx_with == "u-2"` dựa lên giá trị ghi bởi lần chạy thứ hai: ok.
- TTL: `default_ttl=0.02` phút + `sleep(2)` + `sweep_ttl()` gọi tay: chứng minh sweep xoá, **không** chứng minh `start_ttl_sweeper` tự chạy (chỉ `hasattr`). Với `refresh_on_read=False` đúng ý. Không dọn bảng/ dữ liệu trong DB tạm (ok vì DB tạm, nhưng nên ghi DB phải là dùng một lần; spike `setup()` tạo bảng).
- Cần Postgres tạm do người chạy tự dựng: không có kiểm tra kết nối -> báo lỗi thô.

probe_model.py (thiết kế kịch bản)
- **Medium:** `temperature=0` + 3 lần lặp (probe_model.py:74) cho kết quả gần như giống hệt (xem probe-report.json: 3 trial giống nhau từng ký tự). 3 lần không đo biến thiên; ngưỡng 95% với 3 lần/kịch bản (10 kịch bản = 30 phép thử): 1 lần trượt = 96.7% vẫn "GO", 2 lần = 93% NO-GO -> ngưỡng thô và mẫu nhỏ. Nên tăng mẫu (>=20 cho tool/structured), thêm nhiều prompt khác nhau thay vì một câu cố định.
- `go` tính trên trung bình **overall** (probe_model.py:216-221) nên một nhóm yếu (structured_output hoặc language) có thể bị che bởi nhóm khác; chỉ ép riêng tool_calling. Phase-01.md:32 nói tool calling, structured output, ngôn ngữ đều >= 95%. Sửa: yêu cầu **từng nhóm** >= ngưỡng.
- `thinking_clean` bị xếp vào nhóm "language" (:167) làm phồng tỉ lệ nhóm này; nên là nhóm riêng.
- `lang_en` kiểm "không có ký tự có dấu" (:127) và `lang_vi` chỉ "có ít nhất 1 ký tự dấu" (:133): kiểm quá lỏng (câu en lẫn vi pass nếu không dấu; câu "Chao ban" không dấu thì fail oan). Không kiểm ngôn ngữ thật.
- `s_tool_choice_forced` chỉ kiểm có tool_call, không kiểm đúng tool/đối số (:95). `s_no_tool_needed` chỉ kiểm content khác rỗng.
- `s_tool_single` mong đợi `len(calls)==1` và order_id "A101" - rõ ràng, ok. Đáp án mơ hồ: `lang_*` gọi hỏi chính sách khi không có KB, kết quả model **bịa** "14 ngày"/"7 ngày" (report :153,171); bài kiểm vẫn PASS vì chỉ kiểm ngôn ngữ - nên ghi rõ là rủi ro hallucination chưa tính điểm (đã ghi trong phần phát hiện, tốt).
- `probe_embedding`: `"từ " * 3000` có thể chưa vượt 2048 token với tokenizer Qwen (đã cho BadRequestError nên thực tế vượt); `vietnamese_ok = True` chỉ khi gọi thành công, không kiểm UTF-8 đúng thật (vd. so sánh cosine câu có dấu vs không dấu). Step 1 yêu cầu "gửi UTF-8 đúng" - mới kiểm gián tiếp.
- Latency p50 0.32s tính cả scenario streaming; không có tải đồng thời. OK cho phase 1.
- `report` ghi `required_request_flags` tốt, giúp phase 6.
- Mã thoát: `return 0 if go else 1` đúng cho cổng.

## (f) scripts/check
- check.sh: shebang bash, `set -u` không `-e` (cố ý, gom lỗi) - ok. Mã thoát 0/1 đúng; mảng `FAILED` rỗng với `set -u` dùng `${#FAILED[@]}` an toàn trong bash >= 4.4 và macOS bash 3.2 sẽ lỗi "unbound variable" cho mảng rỗng khi mở rộng `"${FAILED[@]}"`, nhưng nhánh đó chỉ chạy khi không rỗng -> ok.
- Behaviour khi thiếu phần tuỳ chọn: alembic bị bỏ qua nếu không có `backend/alembic.ini` (đúng ở giai đoạn này, nhưng **fail-open im lặng**: khi phase 2 xong mà ini bị xoá/sai đường dẫn, bước bị bỏ mà vẫn "TẤT CẢ ĐẠT"; nên in dòng SKIP). Frontend: bỏ qua khi không có package.json; test chỉ khi có `"test"` (grep có thể khớp chuỗi ngoài `scripts`; Low). Hiện frontend không có script `test` (chỉ `typecheck`, package.json:9) nên bước test bị bỏ qua - đúng theo hiện trạng.
- **High:** thiếu `ruff check scripts` và typecheck backend (xem a-8). Nên `ruff check backend scripts` (đã chạy tay: All checks passed).
- Pytest: nếu sau này test cần Postgres compose mà Docker tắt, `check` chỉ báo FAIL pytest mà không giải thích; chưa có bước kiểm `docker compose ps` / pre-flight. `pytest` exit 5 (không có test) cũng bị tính FAIL - ok.
- check.ps1: `$ErrorActionPreference="Continue"` và dùng `$LASTEXITCODE` - đúng; `Pop-Location` không reset `$LASTEXITCODE` -> ok. Nếu `uv` không có, `$LASTEXITCODE` giữ giá trị cũ/`$null` (null -eq 0 là False -> FAIL, đúng). Parse sạch trên Windows PowerShell 5.1 (0 lỗi). File **không có BOM** (UTF-8) nên 5.1 sẽ hiển thị tiếng Việt thành mojibake khi chạy (Low; thêm BOM hoặc chuỗi ASCII). Khác biệt hành vi giữa sh và ps1: không đáng kể.
- Application Control chặn `pip-audit.exe`: script dùng `python -m pip_audit` đúng.
- `pip-audit` chạy trên môi trường uv hiện tại gồm cả dev deps (không chỉ prod) - Low.

## (g) OpenAPI v0 vs plan
Đối chiếu Plan A phase 4/5/7 và Plan B phase 1-6.
- **High - phân trang không nhất quán, sẽ buộc đổi hợp đồng:** chỉ `/v1/staff/refunds` có cursor + envelope `RefundPage` (openapi:130-133, :252). `/v1/staff/tickets` (:149-153), `/v1/conversations`, `/v1/me/notifications`, `/v1/me/refunds`, `/v1/me/tickets`, `/v1/products` trả mảng trần, không `limit/cursor`. Plan B phase 5 ghi các API staff "đều phân trang" (phase-05-staff-console.md:31). Đổi mảng -> envelope sau khi frontend đã mock là breaking. Chốt envelope `{items, next_cursor}` cho mọi danh sách ngay trong v0.
- **High - Plan B endpoints chưa có trong "hợp đồng đóng băng":** `POST /v1/checkout/price`, `POST /v1/orders` (+`Idempotency-Key`), `POST /v1/payments/{id}/mark-transferred`, `GET /v1/staff/payments`, `POST /v1/staff/payments/{id}/confirm|reject`, `GET /v1/staff/orders`, `POST /v1/staff/orders/{id}/status`, trạng thái đơn (`pending_payment, processing, shipped, delivered, cancelled`, phase-03 plan A:29). Bước 9 phase 1 chỉ liệt kê "chat, hoàn tiền, phiếu, thông báo, auth, staff" nên đúng chữ, nhưng frontend Plan B phase 3-6 sẽ cần; cần ghi rõ "v0 chưa gồm orders/payments" trong info.description hoặc bổ sung, kẻo hiểu lầm là đã đóng băng hết.
- **Medium - cookie/CSRF thiếu:** plan A phase 4:27 và Plan B phase 1:26 yêu cầu refresh/logout dùng cookie HttpOnly + header tuỳ chỉnh/`Origin`. OpenAPI không mô tả `Set-Cookie` trên Session (:179-181 chỉ nói văn bản), không khai báo cookie security scheme cho `/auth/refresh`, `/auth/logout`, không khai báo header CSRF. `/auth/logout` đang yêu cầu bearer (security mặc định) nhưng khi access token hết hạn khách không đăng xuất được; phase 4 ngụ ý logout qua cookie. Sửa: `security: []`/cookie scheme + header bắt buộc.
- **Medium - SSE:** thiếu `ticket_id` trong sự kiện handoff (message {text, lang} :80) trong khi ChatResponse có `ticket_id` (:223) và Plan B phase 2 yêu cầu hiển thị mã phiếu handoff. Thiếu `status` cuối ở `done` (:81: chỉ {thread_id}). Nên `done {thread_id, status, ticket_id}` hoặc `message` có `ticket_id`. Tên pha: plan nói `status` (node/tool_start/tool_end), v0 dùng `{node|tool, phase}` - tương đương nhưng lệch chữ; chốt một dạng.
- **Medium - 409 chat:** plan A phase 7 nói 409 "kèm hành động đang chờ" -> schema `Error` (:183) không có trường payload; `/v1/chat/stream` không khai báo 401/409/429 (chỉ 200). Chat rate limit (plan A phase 4/7) không có 429.
- **Medium - ChatResponse.status** `[completed, awaiting_confirmation, handoff]` (:219) phase 7 không định nghĩa enum này; không có trạng thái cho lỗi/hết ngân sách/guard chặn; thêm giá trị enum mới sau này là breaking với client strict. Nên có quy ước "client phải chịu giá trị lạ".
- **Medium:** `Notification.payload` (:232) kiểu object không có cấu trúc theo loại, trong khi `notification-copy.ts` (Plan B phase 6) ánh xạ loại -> nội dung + liên kết; cần `oneOf`/ít nhất các khoá chuẩn (`refund_id`, `order_id`, `ticket_id`). Notification `id` kiểu string (không uuid) và `/me/notifications/{id}/read` cũng vậy: lệch với các id uuid khác, chốt sớm.
- **Low:** thiếu `GET /v1/me/refunds/{id}`, `GET /v1/me/tickets/{id}`, `GET /v1/staff/tickets/{id}` (phase 7:36-39 "[/{id}]"). Thiếu `required` trong nhiều schema (Refund, Ticket, Conversation, Notification) -> frontend sinh type toàn optional. `limit` thiếu `minimum`/`default` (:31, :132; backend thật `ge=1, default=50`). `RefundDecision.approved_amount_vnd` bắt buộc khi approve nhưng schema không biểu diễn. `/health` gắn tag `catalog`. `servers: /api` và `/health` thực tế ở đâu cần khớp nginx.
- Enum đúng với plan: RefundStatus, Refund.source, notification types, ticket category/priority (khớp phase 3 plan A:30-31), ConfirmPayload.action, memory keys (phase 6:47), user roles. Tốt.
- Auth: `Session` trả `expires_in` + `user` ok; RegisterRequest `additionalProperties:false` đúng plan.
- Docs mô tả "Quy ước: mọi endpoint cần JWT ... trừ catalog và /health": đúng; nhưng backend hiện tại còn `require_api_key` trên products (routes_products.py:7) - phù hợp vì plan sẽ gỡ ở phase 4; ghi rõ OpenAPI là hợp đồng *đích*, không phải hiện trạng.

## (h) Lint/type
- `uv run --python 3.12 ruff check backend scripts` -> All checks passed. `[tool.ruff] select = ["E9","F"]` rất tối thiểu (ghi chú trong file; chấp nhận).
- Không có typecheck Python. `# type: ignore[call-arg]` (probe_model.py:194) vô nghĩa nếu không chạy mypy.
- Kích thước file: probe_model.py 243 dòng (>200 theo development-rules; Low, nhưng là script spike; có thể tách scenarios).

## Điều làm tốt
- Probe tự ghi các cờ bắt buộc (`enable_thinking:false`) và hành vi mặc định rò suy luận: phát hiện giá trị cao, ảnh hưởng thật tới code agent hiện hành.
- Spike MCP có cả ca chống ký sớm (ký lúc phát tool_call) vs ký lúc thực thi; xác nhận `ctx` không lộ vào schema LLM.
- Phát hiện context_schema không lưu trong checkpoint và adapter trả lỗi dạng nội dung: đúng loại phát hiện cần ở preflight.
- Lock nhất quán, dev deps không vào image.

## Hành động đề nghị (ưu tiên)
1. (High) Spike MCP: ghi lý do từ chối phía server và so khớp từng ca; thêm kiểm user_id/thread_id.
2. (High) Probe: yêu cầu từng nhóm >= 95%, tăng mẫu, tách `thinking_clean`, thêm kịch bản trộn vi+en, tool-result roundtrip, `/v1/models`; ghi status/message khi vượt giới hạn embedding.
3. (High) OpenAPI v0: thống nhất envelope phân trang, ghi rõ phạm vi (chưa gồm orders/payments), bổ sung cookie/CSRF, `ticket_id` trong SSE, payload 409, 401/429, `required`.
4. (High) check: thêm `scripts` vào ruff, bước typecheck backend (hoặc ghi lý do hoãn), in SKIP rõ ràng, kiểm Docker/Postgres khi test cần.
5. (Medium) Đóng bước 5/7/10: lưu chứng cứ SQL cho unaccent/extension, ghi quy trình Docker/WSL2, liệt kê câu hỏi mở cho chủ shop.
6. (Low) Cập nhật `status:`/Success Criteria trong phase-01.md, xoá lặp ở :45, cân nhắc bỏ `llm_host`, khai báo `openai`, BOM cho check.ps1.

## Câu hỏi chưa giải quyết
- Chấp nhận các tiêu chí step 5/7/10 là "ghi nhận bằng văn bản" hay cần chứng cứ tái lập trong repo?
- OpenAPI v0 đóng băng chỉ phần Plan A hay bao gồm cả orders/payments của Plan B?
- Có chấp nhận ngưỡng 95% trên mẫu 3 lần/kịch bản (gần như tất định ở temperature 0) hay yêu cầu mẫu lớn hơn?
- `stream_mode="messages"` có còn cần hay thay bằng `updates` + lọc node (đã ngầm đổi)?
- Xác nhận không đổi trong backend/app bằng diff (repo không phải git).

**Status:** DONE_WITH_CONCERNS
**Summary:** Không có lỗi Critical; phạm vi sản phẩm không đổi (suy ra từ mtime), Dockerfile/lock nhất quán, lint sạch. Spike và probe chạy PASS nhưng một số phép kiểm yếu (lý do từ chối, ngưỡng theo nhóm, mẫu nhỏ); OpenAPI v0 có điểm sẽ gây breaking change (phân trang, cookie/CSRF, SSE handoff).
**Concerns/Blockers:** Các tiêu chí step 5, 7, 10 chưa có chứng cứ trong repo; OpenAPI phân trang/phạm vi Plan B cần chốt trước khi frontend mock; phase-01.md chưa cập nhật status/Success Criteria.
