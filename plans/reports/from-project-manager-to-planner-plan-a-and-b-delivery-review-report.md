# Đánh giá delivery: Plan A (261023-1010) + Plan B (261023-1100)

Ngày: 2026-10-23 | Vai trò: project-manager (advisory, không sửa plan/code)
Tiến độ đo được: **0/16 phase hoàn thành** (A: 0/9, B: 0/7). Chưa có code mới. Mọi số dưới là ước lượng.

---

## 0. Tóm tắt

- Claim: A 22d + B 16d = **38d**. Ước lượng lại (1 dev, có test): A ~36d, B ~25d = **~61d**. Lệch ~1.6x.
- Đường găng BE: A1→A2→A3→A4/A5→A6→A7→A9. Demo đầu tiên hiện tại ở cuối A7 (~ngày 25 BE). Đề xuất vertical slice đưa demo hoàn tiền end-to-end về ~ngày 20-22 BE.
- Plan B chưa áp dụng red-team (3 Critical, 10 High, 2 Medium). Các mục Critical nằm trên đường tiền/tồn kho, phải xử lý trước B3.
- Release coupling thật là **A7 + B1 + B2** (red-team #12). plan.md của B mới ghi B1.
- Chưa có CI, chưa có test runner ở frontend (`frontend/package.json` không có vitest/playwright), chưa có `docs/`. Các hạng mục này chưa có owner/phase rõ ràng.
- Phụ thuộc cứng ngoài tầm kiểm soát: LLM tự host (tool calling chưa kiểm chứng), embedding endpoint, Docker Desktop. Chưa có probe nào chạy.

**Yêu cầu với agent chính:** Hoàn tất toàn bộ plan và các task còn dở (mục 6 và 8). Đây là việc quan trọng nhất hiện tại. Không dừng ở phase 1 của Plan A, không để plan ở trạng thái nửa sửa. Plan chưa hoàn thiện thì `/ck:cook` sẽ chạy trên thông tin mâu thuẫn.

---

## 1. Milestone và trình tự giao hàng

### 1.1 Dependency graph (thực tế, đã đối chiếu frontmatter)

```
A1 → A2 → A3 ─┬─ A4 (auth) ─────────────┬─ A7 (API v2) ─┬─ A9 (hardening) 
              │                          │               │
              └─ A5 (MCP) ─ A6 (graph) ──┘               └─ A8 (eval, dep A6) → A9
B1 ← A4
B2 ← A7 + B1
B3 ← A3 + A4 + B1 (+ A5 vì sửa tools/orders.py; hiện thiếu trong frontmatter)
B4 ← B3
B6 ← B3 + B4 + A9 (worker; hiện thiếu trong frontmatter)
B5 ← B1 + B4 + B3 + B6 + A7 (hiện frontmatter thiếu B3, B6)
B7 ← tất cả
```

Đường găng: BE chain A1→A2→A3→A4→A5→A6→A7→A9 rồi B-BE (B3→B4→B6→B5→B7). FE (B1, B2, B5-FE) chạy song song được nếu contract đóng băng sớm và dùng mock.

Ghi chú sai lệch so với plan.md B: "Phase 1 và 2 làm song song với phase 3" không đúng. B2 phụ thuộc A7 (~ngày 25 BE), nên B2 không chạy song song với B3 trong giai đoạn đầu.

### 1.2 Đánh giá đề xuất vertical slice (Plan A, mục Red Team Review)

Kết luận: **Chấp nhận, có điều kiện.** Giữ thứ tự ngang cho nền móng (A1-A3: schema, bootstrap, role DB là ràng buộc kỹ thuật thật). Chuyển sang lát dọc từ A4-A6.

| Tiêu chí | Ngang (hiện tại) | Lát dọc (M1) |
|---|---|---|
| Demo đầu tiên | ~ngày 25 BE (sau A7) | ~ngày 20-22 BE |
| Rủi ro tích hợp LLM + LangGraph interrupt + ký token lúc resume | Lộ ở A6 (~ngày 20) | Lộ sớm, ~ngày 12-15 |
| Rework | Thấp về mặt cấu trúc | Cần tách A6 thành thin + full (+~1d tổng) |
| Schema tạm | Không có | Rev 0003-0005 có thể sửa roll-forward (D5 reset DB dev, chưa có prod) |

Điều kiện bắt buộc để chấp nhận lát dọc:
1. Không bỏ auth/RBAC/IDOR trong slice. Slice có test quyền ngay từ đầu.
2. Rule tối thiểu "không khẳng định đã hoàn tiền khi tool chưa xác nhận" phải có trong M1 bằng code. Không đợi guard_output đầy đủ, vì đây là rủi ro tin cậy.
3. LLM thật trong slice (không mock để qua build). Fake LLM chỉ dùng cho test xác định trong CI.
4. Mọi stub tạm phải có ticket và phải được gỡ trước M2. Stub không có ticket không được qua gate.
5. Router, guard_input đầy đủ, memory, eval đầy đủ để sang M2.

---

## 2. Milestones đề xuất (cắt theo giá trị, có exit criteria)

| Mốc | Nội dung | Effort (1 dev) | Exit / gate |
|---|---|---|---|
| **M0 Cổng và nền** | A1 (probe model + spike identity + spike LangGraph); CI skeleton (lint, pytest có service Postgres, `alembic check`, vitest hello); đóng băng contract OpenAPI cho auth/refund/chat; trả lời decision list (mục 7) | ~4d | G0: probe đạt tool calling; spike identity đạt; CI xanh; contract v0 đóng băng |
| **M1 Lát dọc: hoàn tiền end-to-end** | A2; A3 (tập con: users, products, orders, order_items, refunds, refund_events, conversations tối thiểu, notifications); A4 đầy đủ; A5 (request_refund, lookup_order, get_refund_status, identity); A6 thin (agent⇄tools, confirm interrupt, scope tool); A7 tập con (POST /v1/chat JSON, refund decision/payout/cancel, /me/notifications); B1; B5 chỉ hàng đợi hoàn tiền | ~25d BE-chain (1 BE) / ~20d (2 BE) | G1: demo script chạy trên compose sạch; test state machine hoàn tiền; privilege matrix; IDOR; LLM thật qua 5 kịch bản hoàn tiền |
| **M2 Checkout thật và chat đủ** | A6 đầy đủ (router dính, guard_input/output, memory TTL); A7 đầy đủ (SSE, lease, cancel-pending, rate limit); A8 (eval ~20 ca); B2; B3; B4; B5 đủ (thanh toán, đơn); B6; B7 phần e2e 3 luồng | ~20d (1 BE + 1 FE song song) | G2: **phát hành cùng lúc A7 + B1 + B2** (red-team #12); race test tồn kho; price tamper; idempotency; SSE qua nginx thật; eval ca cứng pass |
| **M3 Hardening và vận hành** | A9 (/ready, worker, compose prod, security review, docs/); B7 (Playwright đầy đủ, security review phía FE); runbook; sao lưu/khôi phục; pilot nhân viên | ~7d | G3: mục 5 (DoD M3) |

Tổng: M0 4d + M1 ~25d + M2 ~20d + M3 ~7d ≈ 56d BE-chain (1 BE) cộng FE song song. Với 1 dev toàn bộ: ~61d (~12-13 tuần). Với 1 BE + 1 FE: đường găng BE ~45-50 ngày làm việc (~9-10 tuần), FE xong sớm hơn. Với 2 BE + 1 FE: ~38-40 ngày (~8 tuần). Các con số này là ước lượng, chưa có dữ liệu burn thực.

Thứ tự phát hành đề xuất: M1 cho nội bộ/demo; M2 là release công khai đầu tiên; M3 là điều kiện đưa vào vận hành thật.

---

## 3. Effort và capacity

### 3.1 Ước lượng lại từng phase

Giả định: 1 developer senior, dùng AI coding hỗ trợ, tính cả viết test, không tính nội dung KB và công việc của bên nghiệp vụ. Mỗi "d" = 1 ngày làm việc hiệu dụng.

**Plan A (claim 22d → ước lượng ~36d, khoảng 34-40d)**

| Phase | Claim | Ước lượng | Lý do chênh |
|---|---|---|---|
| 1 Preflight | 1 | 2 | 7 spike + probe 3 nhóm model + identity spike là hard gate |
| 2 Alembic foundation | 2 | 3 | 3 role, service migrate, env theo tiến trình, pool budget, lỗi Windows async loop |
| 3 Schema + seed | 3 | 5 | 7 revision chỉnh tay (CHECK, partial unique, HNSW, trigger, GRANT), test quyền cho 3 role. Chưa gồm nội dung KB |
| 4 Auth + RBAC | 3 | 5 | argon2, refresh family + ân hạn, token_version, rate limit Postgres, CLI, CSRF header, fail-closed, ~10 test bảo mật |
| 5 MCP v2 | 2.5 | 4 | 7 tool, token ký theo lời gọi, replay cache, decorator audit, test SQL injection |
| 6 Agent graph v2 | 4 | 6 | router dính, guard_output có buffer, confirm interrupt, batch trộn, memory TTL, viết lại test cũ |
| 7 API v2 | 3 | 5 | ~13 endpoint, SSE, lease, cancel-pending, state machine refund, OpenAPI, sửa api.ts/chat-widget |
| 8 Observability + eval | 1.5 | 2.5 | Phoenix có auth, redaction, 20 ca eval, harness |
| 9 Hardening + docs | 2 | 3.5 | /ready, worker (service mới), compose prod, security review, 7 file docs |
| **Tổng** | **22** | **~36** | |

**Plan B (claim 16d → ước lượng ~25d, khoảng 24-27d)**

| Phase | Claim | Ước lượng | Lý do chênh |
|---|---|---|---|
| 1 Frontend auth | 1.5 | 2.5 | Chưa có test runner; single-flight; logout cleanup (red-team #13) |
| 2 SSE + notifications | 2 | 3 | Parser SSE, 409/cancel-pending, nginx location riêng, bell + poll |
| 3 Checkout | 3 | 5 | Idempotency theo hash (red-team #1), expected_total (#5), qty/slug, 2 test đua, IDOR, 3 trang, cart-drawer |
| 4 Payments | 2.5 | 3.5 | State machine + event + 2 provider + mark-transferred (webhook nếu giữ +0.5d) |
| 5 Staff console | 3 | 4.5 | 5 API mới + 3 hàng đợi + chi tiết + CSP/XSS + xử lý 409 |
| 6 Order lifecycle | 2 | 3 | State machine, helper tồn kho dùng chung với B3, job hết hạn, thông báo |
| 7 E2E + hardening | 2 | 3.5 | Playwright từ 0, 3 luồng e2e trên compose, security review, runbook |
| **Tổng** | **16** | **~25** | |

### 3.2 Phase không thực tế (ưu tiên xử lý)

- **A3 (3d):** dễ trượt nhất của Plan A. Tách thành A3a (schema + role + test quyền) và A3b (seed + KB chunking). KB song ngữ tách khỏi phase.
- **A6 (4d):** tách thin (M1) và full (M2) như mục 1.2.
- **A4 (3d) và A9 (2d):** bảo mật tự xây. Thêm thời gian review bảo mật vào, không chỉ "rà soát" ở cuối.
- **B3 (3d):** red-team đã thêm idempotency theo hash, expected_total, validate số lượng. Đây là đường tiền, cần test đua trước khi qua.
- **B7 (2d):** Playwright chưa có hạ tầng. Cần ít nhất 0.5d dựng và ổn định test (red-team đã đề xuất nhưng chưa vào effort).

### 3.3 Hạng mục bị thiếu (chưa có phase nào sở hữu)

| Hạng mục | Ước lượng | Đề xuất owner / mốc |
|---|---|---|
| Hạ tầng test + CI (GitHub Actions: lint, pytest với Postgres service, alembic check, pip-audit, npm audit, vitest) | 1-1.5d | PM giao BE lead; M0 (hiện A8 đặt CI rất muộn trong khi A2/A4 đã cần `alembic check` và `pip-audit`) |
| Test frontend (Vitest + Testing Library) và Playwright | 1d | FE lead; M0 (vitest), M2 (playwright) |
| Deploy config: env theo môi trường, secret management, TLS/HSTS, volume backup | 1.5d | Ops; M1 (dev/staging), M3 (prod) |
| Sao lưu và khôi phục Postgres (drill `pg_dump` + restore) | 0.5d | Ops; M3 |
| Runbook: migration roll-forward, xoay JWT_SECRET/MCP_CONTEXT_KEY, vận hành nhân viên | 1d | BE lead + PM; M3 |
| Nội dung KB song ngữ vi/en (10-15 tài liệu: hoàn tiền, bảo hành, vận chuyển, đổi trả) | Không dev, 3-5 ngày nội dung | Chủ cửa hàng / content; bắt đầu M0, xong trước M2 |
| Chính sách hoàn tiền bằng văn bản (thời hạn, điều kiện, ngưỡng) | Không dev, 1-2 ngày | Chủ cửa hàng; trước M1 (agent cần chính sách để hoạt động) |
| Đào tạo nhân viên, quy trình đối soát sao kê chuyển khoản | Không dev | Chủ cửa hàng + PM; M3 pilot |
| Backfill payment cho đơn cũ/seed (red-team #10) | 0.5d | B-BE; M2 |
| Tài liệu: `docs/` chưa có. Plan A P9 tạo, Plan B P7 cập nhật, không phase nào phụ thuộc đúng | 1d | docs-manager; M3 |
| Cấu hình rate limit dùng chung cho orders/quote (red-team #8) | 0.5d | BE-B; M2 |

---

## 4. Kiểm tra nhất quán giữa hai plan

Ký hiệu: "A P#" = Plan A phase, "B P#" = Plan B phase. Đường dẫn đầy đủ nằm trong thư mục `plans/261023-1010-...` và `plans/261023-1100-...`.

| ID | Vấn đề | File tham chiếu | Đề xuất sửa |
|---|---|---|---|
| C1 | Owner migration `orders`: A P3 định nghĩa rev `0004_orders` và viết "Plan B thêm cột bằng revision riêng". B P3 tạo migration `addresses_and_order_totals` thêm cột vào orders. Red-team #10 yêu cầu gộp, nhưng rev 0004 chưa được viết | A P3 (bảng Architecture, dòng 0004); B P3 (Architecture, dòng migration mới) | A P3 là owner duy nhất của bảng orders. Đưa luôn cột tổng/phí ship/note/expires_at/order_no vào rev 0004. B P3 không mở migration orders |
| C2 | Hai nguồn địa chỉ: A P3 `orders.shipping_address jsonb`; B P3 bảng `addresses` (PII) | A P3 (0004); B P3 (Architecture) | Bỏ `addresses` (snapshot trong order), đúng red-team #10. Nếu giữ địa chỉ đã lưu: user quyết (mục 7) |
| C3 | `orders.payment_status` trùng với `payments.status`; trạng thái COD không xác định | B P3 (Architecture); B P4 (payments); A P3 (CHECK order status) | Bỏ `orders.payment_status`, suy ra từ payments. Quyết định COD bắt đầu ở `processing` hay `pending_payment` (mục 7) |
| C4 | Điều kiện hoàn tiền: A P3/P5 chỉ dựa `delivered_at`. B P4 chỉ coi payment `paid` mới đủ điều kiện. Chưa có điều kiện `payment.status=paid` ở A | A P5 (lookup_order, request_refund); B P4; B P6 (bước 4) | Thêm `payment.status=paid` và `sum(refunds) <= payment.amount` vào điều kiện của A P5 (red-team #3) |
| C5 | Quyền role `mcp`: A P3 chỉ cấp SELECT trên orders/order_items/refunds/kb_*. Không có `payments`. B P4/P3 không có GRANT nào (red-team #9). A P5 và B P3 đều cần đọc trạng thái thanh toán qua MCP | A P3 (phần Quyền theo role); B P3 (tools/orders.py); B P4 | Mỗi revision của B phải có GRANT và test quyền (theo quy tắc của A P3). Cấp SELECT `payments` cho `mcp`, không cấp `addresses` |
| C6 | Ba bảng event: `refund_events` (A P3), `payment_events` (B P4), `order_events` (B P6). Red-team #15 đề xuất gộp một `status_events` | A P3; B P4; B P6 | Quyết định gộp hay giữ riêng (mục 7). Nếu giữ riêng, tất cả đều INSERT-only và có GRANT |
| C7 | Ánh xạ trạng thái refund ↔ payment không định nghĩa: A có `paid_out`; B đặt payment `refunded` khi payout. Hoàn tiền một phần chưa rõ | A P3 (refunds); B P4 (Architecture, dòng hoàn tiền) | Định nghĩa bảng ánh xạ trong A P7 (refund service). Quyết định partial (mục 7) |
| C8 | Hai scheme idempotency khác nhau: A P5 dùng `thread_id:tool_call_id`; B P3 dùng header `Idempotency-Key` + hash (red-team #1) | A P5 (refunds); B P3 (orders) | Giữ theo miền, ghi rõ trong docs. Không cần thống nhất, nhưng phải có test cho từng cái |
| C9 | Worker: B P6 "dùng lại worker của A P9", nhưng B P6 không khai báo phụ thuộc A P9. Worker là phase cuối (~ngày 45). Job hết hạn chuyển khoản (24h) không có chỗ chạy trước đó | B P6 (frontmatter, Architecture); A P9 (bước 2) | Thêm A P9 (phần worker skeleton) vào M1/M2, hoặc làm hết hạn lazy khi đọc (không phụ thuộc worker) |
| C10 | Thiếu artifact cho staff: B P5 cần "kết quả kiểm tra điều kiện" và "trích đoạn hội thoại gắn yêu cầu". A P3 không có cột snapshot điều kiện trên refunds; A P7 không có endpoint trích đoạn; role `app` đọc `conversations` là được nhưng chưa có API | B P5 (Architecture, dòng hoàn tiền); A P3 (refunds); A P7 (bảng endpoint) | Thêm `eligibility_snapshot jsonb` vào refunds (A P3). Thêm endpoint `GET /v1/staff/refunds/{id}` kèm trích đoạn (A P7) |
| C11 | Thiếu cột/enum thông báo: A P3 `notifications(type, payload)` không định nghĩa enum. B P6 tạo thông báo cho mọi bước đơn; red-team #15 đề xuất chỉ cho hoàn tiền/xác nhận thanh toán | A P3; B P6 (Architecture); B P2 (poll 30s) | Định nghĩa enum `type` trong A P3. Chốt phạm vi thông báo (mục 7) |
| C12 | File frontend bị nhiều phase cùng sửa, không có owner: `frontend/src/api.ts` (A P7 bước 1; B P1 viết lại qua http-client); `frontend/src/components/chat-widget.tsx` (A P7; B P1; B P2); `frontend/nginx.conf.template` (A P4; B P1; B P2); `frontend/src/components/site-layout.tsx` (B P1, P2, P5) | A P4, A P7; B P1, B P2, B P5 | Chia owner: B P1 sở hữu api.ts và nginx (phần frontend); A P4 chỉ mô tả thay đổi backend (X-Forwarded-For, bỏ API key) và giao cho B P1 làm. A P7 bỏ phần sửa frontend, chuyển sang B P1/B P2 |
| C13 | Release gate: A P7 và B P1 đều ghi "phát hành cùng nhau" nhưng B plan.md chỉ ghi B1. B P2 phụ thuộc A P7 (SSE) | B plan.md (bảng phase); A plan.md (Dependencies) | Gate = A P7 + B P1 + B P2 (red-team #12). Ghi vào cả hai plan.md |
| C14 | Config module: B P4 sửa `backend/app/config.py` (BANK_*). A P2 thay bằng `backend/app/settings/{api,migrate,mcp}.py`, không có `config.py` | B P4 (Related Code Files); A P2 (Create settings) | B P4 dùng `ApiSettings`. Sửa đường dẫn trong B P4 |
| C15 | Phụ thuộc thiếu trong frontmatter B: B P3 cần A P5 (sửa tools/orders.py); B P5 cần B3 và B6 (đổi trạng thái đơn, danh sách đơn); B P6 cần A P9 (worker); B P7 cần A P8/A P9 (docs/, eval) | Frontmatter `dependencies` của B P3, P5, P6, P7 | Cập nhật frontmatter theo đồ thị mục 1.1 |
| C16 | Giỏ hàng có đường vào checkout thứ hai: `frontend/src/components/cart-drawer.tsx` tồn tại, B P3 chỉ liệt kê `cart-page.tsx` | B P3 (Related Code Files); `frontend/src/components/cart-drawer.tsx` | Thêm cart-drawer vào B P3 (red-team đã ghi nhận) |
| C17 | Seed và fixture: A P3 seed mặc định tắt (`SEED_DEMO_DATA=false`) và chưa có đơn đã giao có payment. B P7 e2e cần dữ liệu cố định (đơn giao, payment) | A P3 (seed); B P7 (bước 1) | Thêm fixture e2e vào A P3 (bật qua env profile test). Owner: BE lead |
| C18 | Test infra: A dùng pytest (chưa khai báo trong plan), B P1 dùng Vitest, B P7 dùng Playwright. Không phase nào dựng hạ tầng, CI đến A P8 | A P1-A P8; B P1; B P7 | Chuyển vào M0 (mục 3.3) |
| C19 | Tham chiếu "Plan B thêm job vào worker" và "Plan A P7 phát hành với B P1" đúng về ý nhưng các cụm như "tất cả", "B3", "Plan A p4" trong frontmatter B không đọc được bằng máy (ck plan) | Frontmatter B P1-P7 | Chuẩn hoá dạng `261023-1010-backend-alembic-and-langgraph-agent#4` (xem mục 6) |
| C20 | Điểm tham chiếu sai trong A P7: "Plan B phase 1 phát hành cùng" nhưng SSE thuộc B P2 | A P7 (Overview); A plan.md (Dependencies) | Sửa thành B P1 + B P2 |

Không có mâu thuẫn về tên sự kiện SSE (`status`, `message`, `confirm_required`, `done`, `error`): A P7 và B P2 khớp nhau. Không có mâu thuẫn về tên route staff (`routes_staff_refunds.py` ở A, `routes_staff_{payments,orders,summary}.py` ở B không trùng tên file).

---

## 5. Risk register (top 10)

L = likelihood (xác suất), I = impact (tác động). Owner là vai trò, chưa gán tên người.

| # | Rủi ro | L | I | Owner | Giảm thiểu / trigger |
|---|---|---|---|---|---|
| R1 | Model chat tự host (`your-api-model-host`) không tool calling hoặc structured output ổn định | M | H | BE lead | A P1 là cổng cứng. Đề xuất ngưỡng: tool calling đúng ≥ 95% trên bộ probe 30 lượt (vi + en). Không đạt thì đổi model hoặc đổi thiết kế trước A5. Trigger: lỗi parse > 5% ở M1 |
| R2 | Endpoint LLM và embedding không có SLA, một host, có thể treo/rớt (kể cả Qwen3-Embedding 1024 chiều, 2048 token) | M-H | H | Ops | Timeout + retry có trần; semaphore LLM; embedding lỗi → trigram + log cảnh báo (A P5); `/ready` báo trạng thái; reindex chạy riêng. Trigger: p95 > ngưỡng 3 ngày liên tiếp |
| R3 | Docker Desktop bắt buộc cho test/dev; Windows 11 Home cần WSL2; máy dev chưa chắc đã có | M | M | PM + từng dev | A P1 bước 7 kiểm tra sớm. CI dùng Postgres service container để không phụ thuộc Docker local. Có đường cài Postgres local có pgvector |
| R4 | Ước lượng lạc quan: 38d claim so với ~61d thực tế | H | H | PM | Re-baseline theo mục 3; cắt theo D10 và red-team; theo dõi burn theo milestone; ngưỡng trượt >20% ở M1 thì họp cắt phạm vi |
| R5 | Mâu thuẫn schema và scope giữa hai plan (C1-C7, C10) dẫn tới rework migration | H | H | BE lead | Một owner schema (A P3). Sửa trước `/ck:cook`. Mỗi revision có GRANT và test quyền |
| R6 | Lỗi tiền và tồn kho: oversell, refund kép, race hết hạn với xác nhận chuyển khoản, huỷ đơn đã trả không có đường hoàn tiền (red-team Critical 1-3, High 4-8) | H (nếu chưa sửa) | H | BE-B + reviewer | Áp dụng 3 Critical + High liên quan trước B3. Test đua bắt buộc ở G2 |
| R7 | Auth và danh tính MCP tự xây: spike thất bại hoặc có lỗ hổng (phát lại, alg confusion, IDOR) | M | H | BE lead + security reviewer | Spike là cổng cứng (A1). Test tấn công trong A4/A5. `pip-audit`. Rà soát bảo mật ở M3 và trước G2 |
| R8 | Contract churn A7 ↔ B1/B2; phải phát hành ba phase cùng lúc (C13) | H | H | PM + FE lead | Đóng băng OpenAPI v0 ở M0. FE dựng bằng mock theo contract. Gate G2 ghi rõ |
| R9 | Không có CI và test infra hiện tại; CI đặt ở A8. Regression không được bắt sớm | H | M | PM | CI skeleton ở M0 (mục 3.3). Không merge khi CI đỏ |
| R10 | Nội dung KB song ngữ, chính sách hoàn tiền, bộ eval và quy trình đối soát chuyển khoản phụ thuộc người không phải dev | H | M | Chủ cửa hàng (product owner) | Chính sách hoàn tiền bằng văn bản trước M1. KB 10-15 tài liệu trước M2. Eval ca cứng do product owner duyệt |

Rủi ro theo dõi (chưa vào top 10): môi trường Windows (async psycopg cần Selector loop, line endings); key person (một dev giữ toàn bộ BE); chi phí và rate limit khi dùng LLM host ngoài (nếu có).

Cập nhật risk register: không có rủi ro nào được đóng vì chưa có bằng chứng (probe/spike chưa chạy). Rủi ro mới so với plan: R4, R8, R9, R10 (red-team không đề cập).

---

## 6. Vệ sinh plan (phải sửa trước `/ck:cook`)

| # | Việc | Plan | Mức |
|---|---|---|---|
| H1 | Thêm mục "Red Team Review" vào plan.md của B, ghi rõ 15 phát hiện đang chờ quyết định, chưa áp dụng | B | Bắt buộc |
| H2 | Chuẩn hoá phụ thuộc: bỏ "Plan A p4", "tất cả", "B3" dạng tự do; dùng `plan-id#phase` và danh sách số phase. Kiểm tra bằng `ck plan` | Cả hai | Bắt buộc |
| H3 | Mỗi phase file thiếu các mục: **Todo List** (checkbox), **Context Links**, **Next Steps**, **Security Considerations** (development-rules yêu cầu). Hiện 0/16 file có Todo List | Cả hai | Bắt buộc |
| H4 | Thêm trường `milestone: M0-M3` và `owner: role` vào frontmatter từng phase; thêm `effort_range` (min/max) | Cả hai | Bắt buộc |
| H5 | plan.md A: tách "22d đã gồm đệm 30%" thành bảng; cập nhật theo ước lượng mục 3 (~36d). Ghi giả định 1 dev | A | Bắt buộc |
| H6 | plan.md B: "Tổng ~16 ngày" chưa gồm red-team (+test infra, +idempotency, +cart-drawer). Cập nhật ~25d | B | Bắt buộc |
| H7 | plan.md B: sửa câu "phase 1 và 2 làm song song với phase 3"; sửa gate release (C13) | B | Bắt buộc |
| H8 | Đồng bộ trạng thái: bảng "Status" trong plan.md và `status:` trong frontmatter phase phải khớp; xác minh `ck plan check` cập nhật được cả hai. Không xác nhận được thì ghi vào unresolved | Cả hai | Bắt buộc |
| H9 | Đường dẫn `pyproject.toml` và `backend/...`: ghi rõ `pyproject.toml` ở root (đang là file root). Dockerfile và compose path phải khớp | A | Nên |
| H10 | Plan B không có D-ID. Ghi "tuân theo D8, D9, D10 của A" và nêu decision riêng của B (D-B1...) | B | Nên |
| H11 | Repo có file `.env` chứa khoá (không đọc nội dung trong báo cáo này). Đảm bảo `.env` không commit; `.env.example` là nguồn chuẩn | Repo | Bắt buộc (bảo mật) |
| H12 | Cập nhật `docs/` là phạm vi chung, không để hai plan cùng tạo. Chỉ A P9 tạo file gốc, B P7 chỉ bổ sung mục vận hành | Cả hai | Nên |

Checklist trước khi chạy `/ck:cook`:
- H1, H2, H3, H4, H5, H6, H7, H8 đã xong
- C1, C2, C3, C4, C5, C9, C13, C15 đã xử lý (đây là các mục chặn schema và phụ thuộc)
- Quyết định mục 7 từ 1 đến 6 đã có câu trả lời
- Probe A1 đã chạy hoặc có kế hoạch chạy trước khi bắt đầu A2

---

## 7. Danh sách quyết định cho người dùng (tối đa 10, kèm mặc định khuyến nghị)

Theo quy tắc review-audit-self-decision: các mục dưới chạm vào quyết định đã chốt (D8, D10) hoặc phạm vi, nên hỏi trước khi cắt.

| # | Quyết định | Mặc định khuyến nghị | Lý do / ảnh hưởng |
|---|---|---|---|
| 1 | Chấp nhận lát dọc M1 (hoàn tiền end-to-end) trước router/guard/eval đầy đủ? | **Có**, theo điều kiện mục 1.2 | Demo ~ngày 20-22 BE thay vì ~ngày 25+; lộ rủi ro tích hợp sớm |
| 2 | Chốt "release = A7 + B1 + B2" (red-team #12) | **Có** | Không có B1/B2, API v2 làm vỡ giao diện cũ |
| 3 | D8 đã chốt "có sẵn interface cổng". Red-team #15 đề xuất bỏ webhook và abstraction. Giữ interface hay bỏ? | **Giữ `PaymentProvider` nhỏ (2 class), bỏ route webhook** (hybrid). Không tự cắt D8 | Đúng quy tắc không cắt quyết định đã xác nhận; giảm code chết |
| 4 | COD bắt đầu `processing` hay `pending_payment`? Payment COD `pending` đến khi giao và thu tiền? | **`processing` ngay khi đặt; payment `pending` đến khi nhân viên đánh dấu đã thu** | Đơn COD không cần chờ tiền; hoàn tiền chỉ khi `paid` (C4) |
| 5 | `mark-transferred` có gia hạn `expires_at`? Hết hạn có áp dụng cho `awaiting_confirmation`? | **Không gia hạn. Hết hạn chỉ tác động `pending`, không đụng `awaiting_confirmation`**; nhân viên xử lý quá hạn bằng tay (red-team #2) | Tránh huỷ đơn khi tiền đã nhận |
| 6 | Hoàn tiền một phần đặt payment thành `refunded`? | **Chỉ `refunded` khi tổng đã hoàn = số tiền payment.** Trước đó giữ `paid` và theo dõi qua refunds | Ràng buộc `sum(refunds) <= amount` (C7) |
| 7 | Đơn đã thanh toán nhưng bị huỷ: ai thấy? Có tự mở yêu cầu hoàn tiền không? | **Chỉ nhân viên thấy trong hàng đợi; khách thấy "đang xử lý hoàn tiền"; huỷ đơn `paid` tự mở refund `pending_staff`** | Red-team #3 Critical; không có đường hoàn tiền là lỗ hổng tiền |
| 8 | Phạm vi UX: địa chỉ đã lưu, quote riêng, dashboard, chuông thông báo poll 30s | **Cắt địa chỉ đã lưu (snapshot trong order), cắt dashboard. Giữ thông báo nhưng chỉ cho hoàn tiền và xác nhận thanh toán; poll 60s; toast, không chuông** | Red-team #15; chuông nằm trong overview B nên cần xác nhận |
| 9 | Có vai trò `admin` tách khỏi `staff` ở console? Có cần thông báo/duyệt hai người cho hoàn tiền lớn? | **Không. Chỉ `staff`, `admin` là CLI tạo. Không có ngưỡng hai người duyệt ở v1** | YAGNI; A D2 đã chốt nhân viên duyệt, không ngưỡng tự động |
| 10 | Năng lực đội và môi trường: số dev, ai phụ trách KB và chính sách, CI trên GitHub hay nền khác, có chạy HTTP demo (ảnh hưởng cookie `Secure`) | **2 dev (1 BE + 1 FE); CI GitHub Actions ở M0; demo HTTP chỉ localhost (`Secure` bật theo ENV); staging và prod bắt buộc HTTPS; chủ cửa hàng chịu trách nhiệm chính sách + KB** | Quyết định này đổi lịch chính: 1 dev ~12-13 tuần, 2 dev ~8-10 tuần |

---

## 8. Blocker, thay đổi phạm vi, hành động kế tiếp

### 8.1 Blocker (chưa có task nào bị kẹt quá 1 phiên vì chưa ai bắt đầu)

| Blocker | Ảnh hưởng | Owner | Đường gỡ |
|---|---|---|---|
| A1 probe + spike chưa chạy | Chặn toàn bộ A2+ | BE lead | Chạy `probe_model.py` và spike identity; ghi kết quả vào plan.md |
| 10 quyết định mục 7 chưa có câu trả lời | Chặn B3-B6 và sửa plan | Người dùng | Trả lời theo mặc định hoặc chỉnh |
| Năng lực đội chưa xác định | Lịch không tin được | PM + người dùng | Trả lời quyết định 10 |
| Docker Desktop trên máy dev chưa rõ | Chặn test tích hợp local | Từng dev | Kiểm tra sau A1 bước 7; dùng CI service container nếu không có |

### 8.2 Thay đổi phạm vi đã ghi nhận

| ID | Thay đổi | Trạng thái | Lý do | Tác động |
|---|---|---|---|---|
| S1 | A: cắt Prometheus, LLM judge, baseline ±2, load test, lớp `repos/`, 11→7 tool (D10) | Đã áp dụng trong A | Red-team #14, scope critic | Giảm ~3-4d so với bản gốc |
| S2 | A: lát dọc M1 (vertical slice) | Đề xuất, chưa áp dụng | Red Team Review của A | Cần quyết định 1 |
| S3 | B: áp dụng 15 phát hiện red-team (3 Critical, 10 High, 2 Medium) | Chưa áp dụng, chờ quyết định | Red-team Plan B | Tăng ~3-4d (idempotency, ledger tồn kho, rate limit, CSP, logout); giảm ~2d (cắt webhook, địa chỉ, dashboard) |
| S4 | B: gộp `status_events` hoặc giữ 3 bảng event | Chưa quyết | Red-team #15; C6 | Tiết kiệm ~0.5d nếu gộp |
| S5 | Thêm hạng mục hạ tầng (test, CI, deploy, backup, runbook, KB) vào mục 3.3 | Đề xuất | Không có owner trong plan hiện tại | +~6-7d (một phần không phải dev) |

Giá trị tổng sau thay đổi: ~61d (1 dev), đã gồm S1 và S3 ước lượng trung tính, chưa gồm S5 (nếu tính thêm S5: ~65-68d).

### 8.3 Hành động kế tiếp (owner, định nghĩa hoàn thành)

| # | Hành động | Owner | Định nghĩa hoàn thành |
|---|---|---|---|
| 1 | **Hoàn tất plan**: áp dụng H1-H12 và C1-C20 vào hai bộ plan | Agent chính (controller) | `ck plan` xác thực được cả hai; không còn free-text phụ thuộc; mọi phase có Todo List; không còn "Plan A p#" trong frontmatter; H1-H8 đánh dấu xong. Đây là ưu tiên số 1. Không chuyển sang code khi plan còn mâu thuẫn |
| 2 | Trả lời 10 quyết định mục 7 | Người dùng | Ghi vào decision log của plan.md A (D-ID mới) và B (D-B#) |
| 3 | Chạy A1 probe, spike identity, spike LangGraph | BE lead | `probe-report.json` không chứa secret; test spike identity pass (replay/expired/tamper/thiếu context fail-closed); go/no-go ghi vào A plan.md |
| 4 | Dựng CI skeleton và test infra (pytest + PG service, vitest, `alembic check`, pip-audit, npm audit) | PM giao BE lead + FE lead | Pipeline xanh trên nhánh chính với test hello; có badge |
| 5 | Đóng băng OpenAPI v0 cho auth, refund, chat | FE lead + BE lead | File contract trong `docs/` hoặc `plans/` có version; có mock cho FE |
| 6 | Viết chính sách hoàn tiền bằng văn bản | Chủ cửa hàng | Văn bản được duyệt; agent dùng làm nguồn cho điều kiện và trần số tiền |
| 7 | Cập nhật plan.md với bảng milestone M0-M3 và DoD (mục 5) | PM | Cả hai plan.md có bảng milestone; ước lượng đã thay bằng số mới |

---

## 9. Definition of Done và gate theo milestone

### 9.1 Quy tắc chất lượng chung
- Mọi endpoint có test quyền (khách, nhân viên, khách khác đều bị từ chối đúng cách).
- Mọi thay đổi trạng thái tiền có event INSERT-only và có actor.
- Không có `user_id` trong request model (grep gate, A P7 bước 1).
- `alembic check` sạch; mỗi revision có GRANT và test quyền.
- CI đỏ thì không merge.
- Không có stub nào qua milestone mà không có ticket.

### 9.2 DoD theo milestone

**M0 (G0):**
- `probe-report.json` có kết luận tool calling, structured output, tool_choice, embedding 1024 chiều, chất lượng vi/en.
- Spike identity MCP đạt: token ký theo lời gọi, hết hạn bị từ chối, thiếu context fail-closed.
- CI xanh: lint, pytest với PG service, `alembic check` (skeleton), vitest hello, pip-audit.
- Contract v0 cho auth/refund/chat đóng băng.
- Decision list (mục 7) đã có câu trả lời.

**M1 (G1), demo hoàn tiền end-to-end:**
- Test state machine refund: chuyển không hợp lệ bị từ chối; hai yêu cầu song song chỉ tạo một bản ghi; gửi lại sau khi bị từ chối được; nhân viên không tự duyệt yêu cầu của mình; số tiền chi khớp số đã duyệt.
- Test quyền: role `mcp` không đọc `users`, `refresh_tokens`, `addresses`; role `app` không UPDATE `refund_events`.
- IDOR: khách A không đọc/resume/huỷ được đơn/refund/thread của khách B.
- `request_refund` không bao giờ chuyển tiền; không tool nào nhận `user_id` từ LLM.
- Rule "không khẳng định đã hoàn tiền" có trong code ở M1.
- Demo script chạy trên compose sạch, LLM thật, 5 kịch bản hoàn tiền (kết quả ghi lại).
- Không có stub nào thiếu ticket.

**M2 (G2), release công khai (A7 + B1 + B2):**
- Race test: 2 người mua sản phẩm còn 1; 2 request cùng Idempotency-Key; giá giả bị bỏ qua; huỷ đồng thời với giao hàng; hết hạn chuyển khoản đua với xác nhận.
- Test resume trễ hơn TTL token ký vẫn chạy (ký tại thời điểm thực thi).
- SSE qua nginx thật trong compose (không chỉ Vite dev). `proxy_buffering off` được kiểm chứng.
- Eval ca cứng (hoàn tiền, an toàn): đạt 100% trên model thật, chạy 3 lần liên tiếp, không ca nào fail (đề xuất: pass = 3/3).
- Ca chức năng (tư vấn, tra đơn, chính sách): báo cáo, không chặn. Không có baseline ±2 (D10).
- E2E 3 luồng trên compose (LLM giả cho luồng xác định): đăng ký → COD → đơn; chuyển khoản → xác nhận → processing; hoàn tiền end-to-end.
- Hai tab không bị đăng xuất; refresh trong ân hạn không thu hồi họ.

**M3 (G3), vận hành:**
- Review bảo mật: không còn mục Critical/High mở (IDOR, giá, máy trạng thái tiền, cookie/CSRF, XSS console nhân viên, SQLi, token MCP).
- `pip-audit` và `npm audit` không có mục high trở lên chưa xử lý.
- Drill sao lưu và khôi phục Postgres thành công (ghi thời gian khôi phục).
- Profile prod không publish cổng 8000 và DB; `/ready` xanh.
- Runbook đã kiểm chứng: roll-forward migration, xoay JWT_SECRET/MCP_CONTEXT_KEY, vận hành nhân viên (hoàn tiền, xác nhận chuyển khoản, đối soát).
- `docs/` có 7 file, khớp code.
- Có ít nhất một buổi hướng dẫn nhân viên thật, nhân viên làm được luồng không hỗ trợ.

---

## 10. Câu hỏi chưa giải quyết

1. Kết quả probe model (tool calling, structured output) là gì? Chưa có dữ liệu, toàn bộ lịch phụ thuộc vào đây.
2. Endpoint `your-api-model-host` có SLA, giới hạn rate, và có tài khoản/key cho môi trường staging không? Hay chỉ dùng được một lần từ máy dev?
3. Năng lực đội: số dev, ngày bắt đầu mong muốn, deadline demo/release cứng?
4. Có CI nền tảng nào được phép (GitHub Actions, GitLab, nội bộ)? Repo hiện không có `.github`.
5. Máy dev có Docker Desktop và WSL2 chưa?
6. Ai sở hữu chính sách hoàn tiền, nội dung KB song ngữ, và bộ eval (chủ cửa hàng hay người khác)?
7. Có môi trường HTTP công khai (demo) không? Ảnh hưởng cookie `Secure` và CSRF.
8. Ngưỡng tool calling để qua G0 (đề xuất 95%) và tiêu chí pass eval (đề xuất 3/3) có được chấp nhận không?
9. Đối soát chuyển khoản: nhân viên đối chiếu thủ công theo sao kê hay có file xuất từ ngân hàng? Ảnh hưởng khối lượng B5.
10. Nhà cung cấp pgvector và image Postgres (managed hay tự host) cho môi trường prod: có được quyền `CREATE EXTENSION` không?

---

**Status:** DONE_WITH_CONCERNS
**Summary:** Đã đối chiếu 16 phase file, 2 plan.md, red-team B và mã nguồn hiện có. Effort thực tế ~61d (1 dev) thay vì 38d. Đề xuất M0-M3 với lát dọc hoàn tiền ở M1, release gate A7+B1+B2, 20 mâu thuẫn liên plan cần sửa, 10 quyết định cho người dùng. Báo cáo: plans/reports/from-project-manager-to-planner-plan-a-and-b-delivery-review-report.md
**Concerns/Blockers:** (1) Plan chưa đủ điều kiện `/ck:cook`: mâu thuẫn schema orders/addresses/payments, phụ thuộc thiếu, thiếu Todo List. Agent chính phải hoàn tất việc này trước. (2) Probe model và spike identity chưa chạy: toàn bộ lịch M1+ chưa có căn cứ. (3) Red-team B chờ 10 quyết định, trong đó có D8 đã xác nhận cần người dùng xác nhận trước khi cắt. (4) Không có CI, test runner FE, hay owner hạ tầng. (5) Không đọc file `.env` theo chính sách privacy.
