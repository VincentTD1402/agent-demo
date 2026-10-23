---
phase: 3
title: "Schema models and seed"
status: completed
priority: P1
effort: "5d"
milestone: "M1 (tập con) + M2 (còn lại)"
dependencies: ["261023-1010-backend-alembic-and-langgraph-agent#2"]
---

# Phase 3: Schema models and seed

## Overview

Khai báo toàn bộ bảng bằng model SQLAlchemy, sinh và duyệt tay các revision Alembic, cấp quyền theo role ngay trong từng revision, và tách seed. **Plan này là chủ duy nhất của schema `users/orders/order_items/refunds/support_tickets/notifications/status_events/kb_*`; Plan B chỉ thêm `payments` (và view/grant liên quan).**

## Requirements

- Functional: đủ bảng cho catalog, người dùng/đăng nhập, đơn (đủ cột cho checkout của Plan B), hoàn tiền, hội thoại, phiếu hỗ trợ, thông báo, knowledge base vector.
- Non-functional: ràng buộc ở DB (CHECK, FK, unique một phần) là lớp bảo vệ cuối; bảng sự kiện chỉ INSERT; quyền role nằm trong migration nên không trôi khi thêm bảng.

## Architecture (revisions theo thứ tự)

| Rev | Nội dung |
|-----|----------|
| `0001_extensions` | `vector`, `pg_trgm`, `unaccent` + hàm bọc `immutable_unaccent()`; downgrade no-op |
| `0002_users_auth` | `users(id uuid, email unique lower, password_hash argon2id, full_name, phone, role CHECK customer/staff/admin, is_active, token_version int, memory_consent_at timestamptz null, created_at)`; `refresh_tokens(id, user_id fk, token_hash, family_id, expires_at, revoked_at, replaced_by)` |
| `0003_catalog` | `products` (slug unique, name, category, brand, price_vnd, old_price_vnd, rating, stock>=0, specs jsonb, description, image_url, is_active); index category + trigram trên `immutable_unaccent(name)`; `product_embeddings(product_id, model, embedding vector(1024), content_hash)` + HNSW cosine |
| `0004_orders` | `orders(id, user_id fk, status CHECK(pending_payment, processing, shipped, delivered, cancelled), subtotal_vnd, shipping_fee_vnd, total_vnd, shipping_address jsonb **(bản chụp địa chỉ lúc đặt, nguồn duy nhất)**, note, carrier, tracking_code, expires_at null, delivered_at (ghi một lần), stock_released_at null, idempotency_key, request_hash, created_at)`, `UNIQUE(user_id, idempotency_key)`; `order_items(order_id fk, product_id fk, product_name snapshot, unit_price_vnd, qty CHECK 1..10)`. Không còn cột `items` jsonb, không có `payment_status` (suy ra từ `payments`, Plan B) |
| `0005_refunds` | `refunds(id uuid, order_id fk, user_id fk, source CHECK(customer_request, system_cancel_paid), requested_amount_vnd, approved_amount_vnd, reason, status CHECK(pending_staff, approved, rejected, paid_out, cancelled), idempotency_key unique, thread_id, payout_info_enc bytea null (tài khoản nhận tiền, **mã hoá cấp ứng dụng** bằng `PAYOUT_ENCRYPTION_KEY`, khách điền sau, chỉ staff/admin giải mã khi chi trả; log/trace không chứa giá trị) <!-- Updated: Validation Session 1 - mã hoá payout_info_enc -->, decided_by fk, decision_note, payout_reference, timestamps)`; **unique một phần `(order_id) WHERE status IN ('pending_staff','approved','paid_out')`**: mỗi đơn tối đa một yêu cầu "sống", sau chi trả không tạo thêm; bị từ chối/huỷ thì gửi lại được; `idempotency_key` theo từng lần gửi (`thread_id:tool_call_id`) |
| `0006_conversations_support` | `conversations(thread_id uuid pk **do server sinh**, user_id fk, title, status open/handoff/closed, running_since timestamptz null (lease), last_message_at, deleted_at)`; `tool_audit_log(thread_id, user_id, tool_name, args redacted, status, latency_ms)`; **`support_tickets(id uuid, user_id fk, thread_id, order_id null, category CHECK(human_requested, complaint_legal, exchange_or_address, defective, refund_dispute, other), summary, priority CHECK(normal, high), status CHECK(open, in_progress, resolved, closed), assigned_to fk null, due_at, resolution_note, created_at, resolved_at)`**; `notifications(user_id, type CHECK(refund_decided, refund_paid_out, payment_confirmed, payment_rejected, ticket_updated), payload jsonb, read_at)` + index `(user_id, read_at)`; **`status_events(entity_type CHECK(order, payment, refund, ticket), entity_id, from_status, to_status, actor_id null=system, note, at)`** — một bảng sự kiện chung, thay cho `refund_events` |
| `0007_knowledge_base` | `kb_documents(slug, lang CHECK vi|en, title, category, body, version; unique(slug, lang))`; `kb_chunks(document_id fk cascade, idx, content, embedding vector(1024), tsv tsvector)` + HNSW + GIN |

**Quyền theo role (trong revision, có test):**
- `app`: DML trên bảng nghiệp vụ; trên `status_events`, `tool_audit_log` chỉ `INSERT`/`SELECT` (kèm trigger chặn UPDATE/DELETE).
- `mcp`: `SELECT` trên catalog, `product_embeddings`, `orders` **trừ cột `shipping_address`** (dùng view `orders_for_agent` không có địa chỉ), `order_items`, `kb_*`, `refunds` **trừ `payout_info_enc`**; `INSERT` trên `refunds`, `status_events`, `tool_audit_log`, `support_tickets`, `notifications`. **Không** thấy `users`, `refresh_tokens`, `conversations`. Plan B thêm view tóm tắt thanh toán cho `mcp`.

Vector 1024 chiều (Qwen3-Embedding-0.6B, tối đa 2048 token): chunk KB ≤ ~400 token; truy vấn dùng tiền tố `Instruct: ...\nQuery: ...`.

**Thông số chính sách (cấu hình, chủ shop xác nhận):** `REFUND_WINDOW_DAYS=7` từ `delivered_at`; trần hoàn = tổng tiền hàng đã thực thu, không gồm phí ship (trừ lỗi từ shop), trừ phần đã hoàn; `MAX_QTY_PER_LINE=10`; phí ship và ngưỡng miễn phí ở `config` (nguồn duy nhất cho cả client). KB văn bản chính sách phải ghi đúng các số này (sinh từ cùng cấu hình khi seed).

## Related Code Files

- Create: `backend/app/db/models/{user,catalog,order,refund,conversation,support,knowledge}.py`, `backend/migrations/versions/*` (7 file), `backend/app/shop/seed.py`, `backend/app/kb/{chunking,reindex}.py`, `backend/tests/db/test_{constraints,privileges}.py`
- Modify: `backend/app/shop/seed_data.py` (user demo id **UUID** thay `demo-user`; `order_items`; tài liệu KB song ngữ vi/en: hoàn tiền, bảo hành, vận chuyển, trả góp, đổi trả; fixture e2e: đơn đã giao đủ điều kiện hoàn, đơn đang giao, đơn COD), `backend/app/api/routes_products.py`
- Delete: `backend/app/shop/schema.py`, `backend/app/shop/repo.py`, `backend/app/mcp_server/db.py` (đọc cột `items` cũ), cột `orders.items`

## Implementation Steps

1. Viết model; `alembic revision --autogenerate`, đọc lại từng revision, chỉnh tay (CHECK, index một phần, HNSW, trigger, view, GRANT); `downgrade` (extension: no-op).
2. `seed.py`: **chỉ seed khi bảng còn trống**, mặc định tắt (`SEED_DEMO_DATA=false`); staff demo chỉ khi `ENV=dev`, mật khẩu từ env; có fixture e2e cố định (id đơn, user) để Plan B dùng.
3. Embedding tách khỏi cổng `migrate`: `python -m app.kb.reindex` có timeout, chạy riêng; `/ready` báo số dòng thiếu embedding (phase 9).
4. Test: ràng buộc (refund trùng "sống" bị chặn, sau `paid_out` không tạo thêm, gửi lại sau khi bị từ chối được, qty ngoài 1..10, stock<0, role sai, `UNIQUE(user_id, idempotency_key)`), quyền (`mcp` không đọc `users`/`payout_info_enc`/`shipping_address`; `app` không UPDATE `status_events`), downgrade, seed 2 lần không nhân đôi, `EXPLAIN` tìm kiếm dùng index.

## Todo List

- [x] Viết 7 module model + revision 0002-0007 (0001 đã có từ phase 2), rà tay
- [x] Role/GRANT/view trong từng revision + test quyền
- [x] Seed idempotent + fixture e2e + KB song ngữ
- [x] Test ràng buộc và downgrade

## Success Criteria

- [x] `upgrade head` sạch; `alembic check` sạch; downgrade đảo ngược được (trừ extension)
- [x] Test quyền pass: `mcp` không thấy dữ liệu nhạy cảm; bảng audit không sửa/xoá được
- [x] Seed 2 lần: số dòng không đổi; seed tắt thì không tạo tài khoản nào
- [x] Không còn cột/bảng trùng giữa Plan A và Plan B (grep `payment_status`, `addresses`, `refund_events`, `orders.items` sạch)

## Kết quả thực thi

Kiểm chứng trên Postgres tạm (`pgvector/pgvector:pg17`, đã xoá): `scripts/check.sh` với `TEST_DATABASE_URL` xanh (ruff sạch, pytest 141 pass + 1 skip tích hợp embedding thật, pip-audit sạch, typecheck + npm audit frontend). `docker compose config` hợp lệ (env giả). Smoke qua HTTP: 5 tool MCP của server thật bằng role `mcp` + `/v1/products` bằng role `app` trên schema mới.

- Revision: 0002 users/refresh_tokens, 0003 catalog (+embedding), 0004 orders/order_items/view `orders_for_agent`, 0005 refunds, 0006 hội thoại/phiếu/thông báo/`status_events`/`tool_audit_log`, 0007 KB. 0001 không sửa; 0004-0005 biến đổi `orders`/`refunds` của 0001 tại chỗ và xoá đơn/hoàn tiền cũ (dữ liệu mẫu), chạy được trên DB đã seed và DB trống.
- Quyền: trong từng revision + `apply_grants` (nguồn cấp lại duy nhất); test so ACL hai đường. `mcp` chỉ đọc đơn qua view, refunds theo cột (trừ `payout_info_enc`). `app` không DELETE đơn/hoàn tiền/người dùng (hẹp hơn "DML" của spec: xoá dữ liệu cá nhân là ẩn danh hoá).
- Lệch spec: giữ `shop/repo.py` (truy vấn sản phẩm dùng chung, vẫn được `routes_products` và MCP dùng) và viết lại `mcp_server/db.py` tại chỗ thay vì xoá (MCP v2 là phase 5); `schema.py` đã xoá; tài liệu KB ở `app/kb/documents.py` (giữ `seed_data.py` dưới 200 dòng); thêm cột `kb_chunks.content_hash` và `products.is_active`; `password_hash` cho phép NULL (khách demo chưa đăng nhập được); thêm trigger `delivered_at` ghi một lần.
- Embedding: `python -m app.kb.reindex` (role migrator, timeout, idempotent theo `content_hash`); test dùng client giả, test tích hợp thật bị bỏ qua trừ khi `RUN_EMBEDDING_INTEGRATION=1`. Chưa gọi host embedding thật trong lần này.
- Danh tính: agent vẫn lấy `user_id` từ body chat; id nay là UUID, frontend mặc định đổi sang UUID demo cố định, MCP coi `user_id` không phải UUID là không tìm thấy.

### Vòng sửa sau review (đã kiểm chứng: `scripts/check.sh` có `TEST_DATABASE_URL` xanh, 192 pass + 1 skip; ruff, pip-audit sạch; test ACL upgrade == bootstrap xanh; smoke MCP trên DB tạm)

- [x] Migration 0004/0005 (upgrade và downgrade) từ chối khi `orders`/`refunds` còn dòng, trừ `-x allow_destroy_legacy_orders=true`; bootstrap/compose truyền qua `ALLOW_DESTROY_LEGACY_ORDERS` (mặc định false); test: từ chối khi có dòng, qua khi trống, qua khi có cờ
- [x] `issue_refund` trả trạng thái thật (`pending_staff`, `already_requested`, `request_id`, `message_key`); docstring, chính sách, prompt agent, chuỗi frontend nói rõ "gửi yêu cầu, tiền chưa hoàn"; `lookup_order.refunded_vnd` chỉ khi `paid_out`, thêm `pending_refund_vnd`
- [x] `delivered` bắt buộc `delivered_at` (CHECK); `issue_refund` kiểm tra hạn (ngày 7 được, ngày 8 bị từ chối) và trần = tiền hàng trừ khoản hoàn "sống" (không gồm phí ship); `McpSettings.refund_window_days`
- [x] mcp INSERT theo cột (refunds, status_events, tool_audit_log, support_tickets, notifications); `refunds.status` luôn DEFAULT `pending_staff`; khoá ngoại ghép `(order_id, user_id)`
- [x] Chỉ mục "sống" tách theo nguồn (`customer_request` / `system_cancel_paid`); KB: "trừ số tiền đã chi trả"
- [x] CHECK: `paid_out` cần `payout_reference` + `approved_amount_vnd`; `approved`/`rejected` cần `decided_by` + `decided_at`; `total_vnd = subtotal_vnd + shipping_fee_vnd`
- [x] Ghi chú redaction (ghi lúc ghi, ở lớp audit) trong deployment-guide; hiện không có code ghi `tool_audit_log`/`status_events`
- [x] `EMBEDDING_DIMS` phải bằng 1024 (Api/Mcp/MigrateSettings); reindex: khoá advisory không chờ, `--max-seconds`, xoá embedding sản phẩm ẩn; khách demo chỉ seed ở `ENV=dev`; seed dừng khi thiếu sản phẩm mẫu; test tìm kiếm có dấu qua MCP; ghi chú SQLSTATE 23001 và chuyển trạng thái do app bảo đảm
- [ ] Còn mở (chủ ý, không làm ở phase này): kiểm tra "đã thanh toán" khi có bảng `payments` (Plan B); `orders.id` giữ TEXT; M9 (danh tính phía client) do phase 4

## Risk Assessment

Đổi model embedding sau này: revision `ALTER COLUMN ... TYPE vector(M)` + `reindex` (roll-forward). Autogenerate bỏ sót index một phần/HNSW/trigger/view → luôn rà tay. Embedding host treo không được làm treo deploy (đã tách khỏi `migrate`).

## Security Considerations

PII (`phone`, `shipping_address`, `payout_info_enc`) chỉ đọc bởi `app` đúng route và staff; `mcp` bị chặn ở mức cột/view. Bản ghi audit chỉ-thêm; yêu cầu xoá dữ liệu cá nhân xử lý bằng ẩn danh hoá trường PII, giữ sự kiện.

## Next Steps

Phase 4 (auth) và 5 (MCP) làm song song. Plan B phase 4 thêm `payments` và view cho `mcp`.
