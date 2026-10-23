# Plan A phase 3 - Schema models and seed: implementation report

## Result
`TEST_DATABASE_URL=... bash scripts/check.sh` green: ruff clean, pytest **141 passed, 1 skipped** (optional real-embedding integration test, needs `RUN_EMBEDDING_INTEGRATION=1`), pip-audit clean, frontend typecheck + npm audit OK, "TẤT CẢ ĐẠT". `docker compose config -q` valid (dummy env file, no values printed). Temp container `p3-pg` (pgvector pg17, port 55438) removed; live compose stack untouched (4 containers still up). Not committed.

Scripted smoke on temp DB (real server/queries): bootstrap CLI rc 0; MCP server over Streamable HTTP as role `mcp` called all 5 tools (lookup own order OK, other customer's order not found, search, details, policy, issue_refund new -> already_refunded on repeat, shipped order refused); `/v1/products` via real router under role `app` (contract fields/types unchanged, tested in pytest); reindex CLI without EMBEDDING_BASE_URL exits 2 with clear message. Real embedding host NOT called.

## Files
- New models `backend/app/db/models/{__init__,user,catalog,order,refund,conversation,support,knowledge}.py`; revisions `backend/migrations/versions/20261023_000{2..7}_*.py`.
- New `backend/app/kb/{chunking,documents,embedding_client,reindex}.py`, `backend/app/security/payout_encryption.py`.
- Modified: `db/roles.py` (declarative grants), `db/bootstrap.py`, `settings/migrate.py`, `shop/{repo,seed,seed_data}.py`, `mcp_server/{db,server}.py`, `migrations/env.py`, `docker-compose.yml`, `.env.example`, `pyproject.toml`/`uv.lock` (httpx moved to main deps), `docs/deployment-guide.md`, `frontend/src/components/chat-widget.tsx`, phase-03 file (ticked + "Kết quả thực thi", frontmatter stays `pending`).
- Deleted: `app/shop/models.py` (superseded), `app/shop/schema.py` (no references).
- Tests new: `tests/db/{test_constraints,test_privileges,test_seed,test_search_indexes,test_kb_reindex,test_shop_queries,test_schema_has_no_duplicate_concepts}.py`, `tests/{test_kb_chunking,test_payout_encryption}.py`; extended `test_migrations.py`, `test_runtime_role.py`, `conftest.py`.

## Design notes
- Revisions: 0002 users/refresh_tokens; 0003 catalog (is_active, stock>=0, trigram on `immutable_unaccent(name)`, product_embeddings + HNSW cosine); 0004 orders (uuid user FK, address snapshot, delivered_at write-once trigger, UNIQUE(user_id, idempotency_key)), order_items (qty 1..10), view `orders_for_agent`; 0005 refunds (uuid PK, partial unique live request, approved<=requested, `payout_info_enc bytea`); 0006 conversations, tool_audit_log, support_tickets, notifications, status_events (+ `forbid_row_change` trigger on the two append-only tables, blocks even owner); 0007 kb_documents/kb_chunks (HNSW + GIN on generated tsvector, `embedding` nullable). 0001 untouched; 0004/0005 transform its tables in place and DELETE legacy orders/refunds (demo data; text user_id cannot map to users). Valid on seeded DB (tested: seed 0001-shape rows -> head -> 0001 -> base -> head) and on empty DB. Catalog rows kept.
- Grants: in each revision AND `roles.apply_grants` (single re-apply source). Test compares ACL (table + column level) after upgrade-only vs after bootstrap: equal. mcp: SELECT products/product_embeddings/order_items/kb_*/`orders_for_agent`, refunds column-level minus `payout_info_enc`; INSERT refunds/status_events/tool_audit_log/support_tickets/notifications. mcp has no access to users/refresh_tokens/conversations/orders table. app: SELECT all; INSERT/UPDATE on orders, order_items, refunds, users, tickets, notifications; UPDATE products; INSERT only on status_events/tool_audit_log.
- Search: `repo.search_products` now matches name with `immutable_unaccent(name) ILIKE immutable_unaccent(q)` (accent-insensitive superset of old behaviour) OR brand/description ILIKE, filters `is_active`. EXPLAIN tests (trigram, HNSW product + kb, GIN tsv) use `enable_seqscan = off` on ~400 rows: they prove the indexes are usable by the exact expressions/operators, not scale performance. Trigram test uses the name predicate alone (an OR with unindexed brand/description cannot use the index).
- `alembic check` detects dropping any of the hand-written indexes (test added for 7 of them); trigram index declared via `func.immutable_unaccent(...)` + `postgresql_ops` so Alembic can compare it.
- KB seed: 5 topics x vi/en = 10 docs, numbers from REFUND_WINDOW_DAYS / SHIPPING_FEE_VND / FREE_SHIPPING_FROM_VND (tested with non-default values). Texts are demo placeholders: shop owner must confirm (warranty/installment wording avoids invented numbers). Chunking: max 1200 chars (~400 tokens at ~3 chars/token for Vietnamese, documented), paragraph -> sentence -> word boundaries.
- Reindex: `python -m app.kb.reindex` runs as migrator (compose: `docker compose run --rm migrate python -m app.kb.reindex`), httpx client with timeout, `content_hash = sha256(model + text)`; second run = zero calls (tested), model/content change re-embeds only affected rows, partial failure keeps progress. Needs `EMBEDDING_BASE_URL` (no fallback to LLM base URL).
- Seed: only into empty tables; default off; staff demo only `ENV=dev` + `STAFF_DEMO_PASSWORD` (argon2id via argon2-cffi directly, strength-checked); fixed UUIDs + order ids A100 (delivered 2d ago, refund-eligible), A101 shipped, A102 COD (shipping fee from settings), B200 other customer. MigrateSettings gained: ENV, STAFF_DEMO_PASSWORD, SHIPPING_FEE_VND, FREE_SHIPPING_FROM_VND, REFUND_WINDOW_DAYS, EMBEDDING_{MODEL,BASE_URL,API_KEY,TIMEOUT_S}; compose + `.env.example` forward them (compose forwarding test still enforces parity).
- Encryption helper `app/security/payout_encryption.py` (Fernet), unit-tested; no decrypt call sites.

## MCP / identity behaviour
- Same 5 tool names/signatures/returns. Additive: `lookup_order` also returns `refund_status`; `refunded_vnd` = requested amount of the live refund (pending_staff/approved/paid_out), `items` still `[{"name","qty"}]`. `issue_refund` now inserts a `pending_staff` request (no money out), idempotent per order via the partial unique index; each call gets a random `mcp:<uuid>` idempotency key (no thread/tool_call id at this layer).
- Identity: agent still takes `user_id` from the chat request body and forces it into tool args (unchanged). Required minimal changes: `user_id` is now a UUID; MCP treats non-UUID as "not found"; frontend default `demo-user` -> fixed demo UUID (and ignores a stale non-UUID value in localStorage). API schema pattern already allows UUIDs.

## Deviations from spec
1. Kept `shop/repo.py` and rewrote `mcp_server/db.py` in place instead of deleting (still referenced by `routes_products` and MCP; MCP v2 is later). `routes_products.py` needed no edit (repo carries the change).
2. KB docs in `app/kb/documents.py`, not `seed_data.py` (200-line limit).
3. app grants narrower than "DML on business tables": no DELETE on orders/refunds/users/products (PII erasure = anonymisation; financial records not deletable).
4. Extras not in spec: `kb_chunks.content_hash`, `products.is_active`, `orders.delivered_at` write-once trigger, `approved_amount <= requested` CHECK, partial index on pending-payment expiry.
5. `users.password_hash` nullable (demo customers cannot log in until auth sets a password); phase 4 login must reject NULL.
6. `thread_id` on refunds/support_tickets/tool_audit_log has no FK to conversations (these must outlive conversation retention).
7. `status_events`/`tool_audit_log` cannot be purged with DELETE (trigger blocks owner too); retention job must use TRUNCATE/partitioning.
8. Ran into a Windows-only issue (pre-existing): MCP server run directly on Windows uses ProactorEventLoop and psycopg async cannot connect; smoke forced a Selector loop. Linux container unaffected. DB tests use sync tests + `run_async` for the same reason.
9. Real `.env`, live volume not touched; no `taskkill`.

## Unresolved questions
- Existing dev `.env` / pgdata volume: after this phase, `migrate` on an old volume deletes legacy orders/refunds (documented); confirm that is acceptable for the live dev stack (needs `down -v` or stamp recipe anyway).
- Keep `orders.id` as TEXT order code (A100-style, matches MCP tool inputs) for Plan B checkout, or move to uuid + separate human code?
- Should `issue_refund` (MCP v1) also write a `status_events` row now? Skipped (MCP v2 redesign); mcp already has INSERT on it.
- Owner sign-off still needed for KB wording (warranty/installment/exchange) and exchange window (currently tied to REFUND_WINDOW_DAYS).
- Embedding endpoint (`your-api-model-host/embed/v1`) not exercised in this run; run the optional integration test once with `RUN_EMBEDDING_INTEGRATION=1` and EMBEDDING_* in the environment.

**Status:** DONE_WITH_CONCERNS
**Summary:** Schema (7 models, revisions 0002-0007, grants, view, triggers, indexes), seed + bilingual KB, reindex command, payout encryption and MCP/products rewrite are done; check.sh green with 141 tests on a temp DB. Concerns: legacy dev orders/refunds are discarded on migrate, repo.py/db.py kept instead of deleted, real embedding host not exercised.

---

## Fix round (review + verification findings)

Verified on temp `pgvector/pgvector:pg17` (port 55440, removed after): `scripts/check.sh` with `TEST_DATABASE_URL` rc 0 = ruff ok, pytest 192 passed / 1 skipped (was 141/1), pip-audit clean, FE typecheck + npm audit clean. Without DB env: rc 1 ("thiếu cấu hình DB"), pytest 53 pass / 140 skip. ACL-equality test (`upgrade only == bootstrap`) green, `alembic check` clean. MCP smoke (bootstrap temp DB, 5 tools through `FastMCP.call_tool` as role `mcp`): serialization ok, issue_refund -> `pending_staff`, repeat -> `already_requested`, shipped refused.

Edited 0004/0005/0006 in place (phase-3 revisions are uncommitted/unreleased, so no new revision; ACL test proves revisions == `apply_grants`).

- H1: `app/db/legacy_order_guard.py`; 0004/0005 upgrade+downgrade raise RuntimeError (counts + how to allow) when orders/refunds have rows, unless `-x allow_destroy_legacy_orders=true`. Wired `ALLOW_DESTROY_LEGACY_ORDERS` (default false) -> `MigrateSettings.allow_destroy_legacy_orders` -> `bootstrap.alembic_config` -> alembic x-arg; compose + `.env.example` + deployment-guide. Tests `test_migration_legacy_data_guard.py` (refuses with rows and leaves DB intact, passes empty, passes with flag, 0005 own guard, downgrade guards, bootstrap wiring).
- H2: `issue_refund` returns `{ok, status, already_requested, request_id, order_id, amount_vnd, message_key, message}`; failures `{ok:false, message_key, message}`. **Dropped `already_refunded`** (misleading name; only old tests used it). Docstring, `get_refund_policy`, agent prompt, approval card label and chat widget strings say request sent to staff, money NOT refunded. `lookup_order`: `refunded_vnd` = sum approved only for `paid_out`; new `pending_refund_vnd`; `refund_status` kept.
- H3: CHECK `delivered_has_delivered_at`; seed already sets delivered_at (no other code sets delivered). `issue_refund` enforces window (calendar days in Asia/Ho_Chi_Minh, `McpSettings.refund_window_days`, compose forwards `REFUND_WINDOW_DAYS`) and cap = sum(order_items) - live refunds (shipping excluded). Tests: day 7 ok / day 8 refused, cap, shipping excluded, committed subtracted. **"Payment paid" is NOT checked** (no payments table until Plan B): code comment + doc; delivered orders treated as paid, so an uncollected delivered COD order is not blocked yet.
- M1: mcp INSERT column-level on refunds (no status/approved/decided/payout cols, so status = DEFAULT `pending_staff`, `paid_out` impossible), status_events (no actor_id, at), tool_audit_log (no at), support_tickets (no status/assigned_to/resolved), notifications (no read_at). Composite FK `(order_id,user_id)->orders(id,user_id)` (new `uq_orders_id_user_id`). Source of truth `MCP_INSERT_COLUMNS` in `roles.py`. Residual risk documented: mcp can still write valid-enum events/notifications for any user_id; recommend dropping those two INSERTs if MCP v2 does not need them.
- M2: live unique index split: `uq_refunds_live_customer_request_per_order`, `uq_refunds_live_system_cancel_per_order`. KB vi/en wording now "trừ số tiền đã chi trả hoàn cho đơn đó". Model and ON CONFLICT updated.
- M3: CHECKs `paid_out_has_payout_fields`, `decided_has_decider`, `orders.total_is_subtotal_plus_shipping`.
- M4: doc note only; grep confirms no app code writes `tool_audit_log` / `status_events`.
- M6: `FIXED_EMBEDDING_DIMS=1024` validator in Api/Mcp/MigrateSettings (compose forwards it to mcp too). M7: reindex advisory lock ns 7102 (non-blocking, exit 0), `--max-seconds` (exit 3), stale product embeddings deleted. M8: customers + orders seeded only at `ENV=dev` (test conftest uses env=dev). N1: search test asserts 6 spellings of "củ sạc" through MCP return exactly `anker-sac-20w`, nonsense returns []. N2: seed raises on missing demo product (rolled back). N3/N4: documented.
- Left as-is: `orders.id` TEXT (Plan B decides code generation), SQLSTATE 23001 (documented), M9 (phase 4).
- Other: new helper `tests/db/refund_rows.py`; `run_with_mcp` fixture moved to `tests/db/conftest.py`; new test files for refund rules, integrity checks, reindex lock/budget, legacy guard; privilege tests for column-level INSERT.

Unresolved questions:
- Plan B: once `payments` exists, add the "paid" condition to `issue_refund` (and exclude unpaid COD); confirm the shop wants delivered-but-uncollected COD refused.
- Drop mcp INSERT on `status_events`/`notifications` now (YAGNI, removes forged-event risk) or keep for MCP v2?
- Staff route must forbid `approved -> rejected` and any move out of `paid_out` (app-enforced).

**Status:** DONE_WITH_CONCERNS
**Summary:** All review/verification findings applied; check.sh green (192 pass, 1 skip), fails without DB env, ruff + pip-audit clean, ACL equality green, MCP smoke ok. Concern: "payment paid" refund check deferred to Plan B (no payments table).
