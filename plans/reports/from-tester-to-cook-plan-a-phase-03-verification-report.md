# Plan A phase 3 (schema models + seed): independent verification

Scope: uncommitted phase-3 changes on `main` (HEAD `e92ab22`). Implementer claims treated as unverified.
Temp DBs/containers used and removed. Live stack untouched.

## Results overview

| # | Area | Result | Key evidence |
|---|------|--------|--------------|
| 1a | `check.sh` with TEST_DATABASE_URL, run 1 | PASS | rc 0, ruff ok, pytest 141 passed / 1 skipped, pip-audit ok, FE typecheck ok, npm audit 0 high |
| 1b | same, run 2 (flake check) | PASS | identical 141 / 1, no flakes |
| 1c | no DB env | PASS (fails as required) | rc 1, "THẤT BẠI: thiếu cấu hình DB"; pytest 48 passed / 94 skipped |
| 1d | `SKIP_DB_CHECKS=1` | PASS | rc 0 with `!!! SKIPPED-DB-CHECKS` warning, not "TẤT CẢ ĐẠT" |
| 2a | bootstrap fresh DB (upgrade head + seed) | PASS | rc 0, alembic check: no new ops |
| 2b | downgrade 0001, then base, then head | PASS | each rc 0; check clean after round trip |
| 2c | seed x3 on same DB | PASS | counts identical run A/B/C |
| 2d | seed off (`SEED_DEMO_DATA=false`) | PASS | products 0, users 0, all tables 0 |
| 2e | legacy 0001-shape DB (SQL rows) then bootstrap | PASS | legacy orders L1/L2 + refund removed, 16 products kept, seed ok, re-seed no-op |
| 3 | privilege + constraint probes (fresh DB) | PASS 84/84 | see section 3 |
| 4a | isolated stack `-p p3verify`: migrate | PASS | exit 0 |
| 4b | api / mcp-server health | PASS | both healthy; frontend up |
| 4c | GET /v1/products contract vs HEAD and api.ts | PASS | 16 rows; same key set; types match |
| 4d | 5 MCP tools, tenant isolation, issue_refund idempotency | PASS 19/19 | run inside api container over internal network |
| 4e | frontend typecheck | PASS | `npm run typecheck` rc 0 |
| 4f | isolated stack teardown (`down -v`) | PASS | 0 containers, 0 volumes, 0 networks left |
| 5 | `demo-user` leftovers | PASS with notes | only intentional negatives and history docs |
| 6 | secrets in diff, real `.env` | PASS with 1 low note | 3008 added lines scanned, no real secret |
| 7 | live stack untouched | PASS | 5 containers same IDs, uptime uninterrupted, `agent-demo_pgdata` intact |
| - | spec grep: `payment_status`, `addresses`, `refund_events`, `orders.items` | PASS | only in guard test |

**Blocking failures: none.** Non-blocking notes in section 8.

## 1. check.sh

- Run 1 and 2 with `TEST_DATABASE_URL` (temp `pgvector/pgvector:pg17`, port 55439): both `TẤT CẢ ĐẠT`, about 46 s pytest each.
- The 1 skipped test is the real-embedding integration test (`RUN_EMBEDDING_INTEGRATION=1` needed). Embedding host not called.
- Without DB env: script exits 1 as the spec requires. Without DB, pytest runs 48 and skips 94 DB-gated tests, so the gate is the only thing blocking a green run.
- Frontend has no `test` script, so "SKIP frontend tests" is expected.

## 2. Migrations and seed (manual, temp DB)

- Revision chain 0001 to 0007 applied in one bootstrap run. Migrator, app and mcp roles created.
- Round trip: `downgrade 0001` (current = 0001), `downgrade base` (rc 0; only extensions and LangGraph tables remain; extensions kept by design), `upgrade head` (rc 0). `alembic check` returns "No new upgrade operations" before and after.
- Seed counts after first load (identical on runs 2 and 3):

| Table | Rows |
|-------|------|
| products | 16 |
| users | 3 (2 customers + staff demo) |
| orders | 4 (A100, A101, A102, B200) |
| order_items | 5 |
| kb_documents | 10 (5 topics x vi/en) |
| kb_chunks, product_embeddings, refunds, tickets, conversations, events, audit | 0 |

- Legacy path: created 0001-shape tables via `alembic upgrade 0001` as migrator, then inserted SQL rows in 0001 shape: 16 products (real slugs), orders L1 (delivered, `items` jsonb, text `user_id='demo-user'`), L2 (processing), refund on L1. Then bootstrap on new code. Result: L1/L2 and legacy refund deleted (as the implementer documented), products kept, seed completed, second seed no-op, `alembic check` clean, head 0007.
- Seed off: no products, users or orders created.

## 3. Privileges and constraints (probe driver on fresh migrated DB, 84 probes)

Probes run as the real login roles inside a savepoint each; expected SQLSTATE compared with actual.

| Group | Probes | Result | Notes |
|-------|--------|--------|-------|
| mcp reads | 17 | 17 PASS | users, refresh_tokens, conversations, orders (table + shipping_address), refunds.payout_info_enc and `SELECT *` on refunds all 42501. `orders_for_agent` has no shipping_address (42703). Allowed: refunds minus payout, orders_for_agent, products, product_embeddings, order_items, kb_*. status_events and tool_audit_log not readable by mcp |
| mcp writes | 9 | 9 PASS | INSERT allowed on refunds, status_events, tool_audit_log, support_tickets, notifications (rolled back). INSERT on orders/users, UPDATE status_events, DELETE tool_audit_log denied |
| app denied | 13 | 13 PASS | UPDATE/DELETE on status_events and tool_audit_log, DELETE on orders/refunds/users/products, TRUNCATE orders, CREATE TABLE (public schema), ALTER/DROP/CREATE INDEX (not owner) all 42501 |
| app allowed | 4 | 4 PASS | SELECT payout_info_enc and users (app reads PII per spec); INSERT status_events and tool_audit_log |
| trigger vs owner | 4 | 4 PASS | migrator (table owner) UPDATE/DELETE on status_events and tool_audit_log blocked by `forbid_row_change` trigger. SQLSTATE 23001 (see note N3) |
| refund live rules | 4 + 6 | 10 PASS | one live request per order (23505 on second pending_staff and on approved while live); rejected row does not block; resubmit after reject OK; after paid_out a new request is 23505; cancelled OK |
| refund checks | 7 | 7 PASS | requested > 0, source enum, status enum, approved in (0, requested], UNIQUE(idempotency_key) |
| orders | 5 | 5 PASS | UNIQUE(user_id, idempotency_key) (same user 23505, other user OK); status enum; total >= 0 |
| order_items | 4 | 4 PASS | qty 0 and 11 rejected (23514); 1 and 10 accepted |
| products / users | 4 | 4 PASS | stock -1 rejected, 0 OK; role 'owner' rejected; email unique case-insensitive (23505) |
| delivered_at write-once | 4 | 4 PASS | set once OK; re-set, clear, and change all rejected by trigger (23001) |

Total 84: 84 PASS on the clean run (`probe-clean.txt` in scratchpad).

Harness history (not product defects, disclosed for transparency):
- First run: 8 FAIL. 4 were my wrong expectation of trigger SQLSTATE (P0001 vs actual 23001). 2 were a test collision on PK (order_id, product_id) for two lines of the same product in one transaction. 2 were a later run on the same DB hitting committed rows. Fixed expectations, used a different product, and ran on a fresh DB. Clean run 84/84.

## 4. Isolated full stack (`-p p3verify`)

- Compose copied to scratchpad with absolute build contexts. `--project-directory` set to scratchpad, so the repo `.env` is never loaded. Env values generated (random alphanumeric passwords, Fernet key, dummy LLM/embedding URLs at 127.0.0.1:9, `SEED_DEMO_DATA=true`, `ENV=dev`, `STAFF_DEMO_PASSWORD`). Host ports 18000 (api) and 13000 (frontend).
- Services: db (internal only), migrate exit 0, mcp-server healthy, api healthy, frontend running.
- Logs: 0 tracebacks or ERROR lines in migrate, api, mcp-server, frontend.
- Product contract (`GET /v1/products` on the isolated api):
  - 16 rows. Keys identical to HEAD `repo.py` `_COLS` (slug, name, category, brand, price_vnd, old_price_vnd, rating, stock, specs, description, image_url).
  - Types match `frontend/src/api.ts` `Product`: numbers, `specs` is `Record<string,string>`, `old_price_vnd` and `image_url` nullable.
  - `rating` is `numeric(2,1)` in both HEAD 0001 and now.
  - No API key: 401. Unknown slug: 404. Frontend nginx `/api/v1/products` proxy: 200.
  - Route file `routes_products.py` unchanged vs HEAD. Repo query changed in the intended way: `is_active` filter and `immutable_unaccent` name search.
- MCP tools (19/19 PASS, run in api container against `http://mcp-server:8001/mcp`):
  - Tool set is exactly the 5 tools.
  - lookup_order: own A100 found; id normalisation ok; **tenant isolation**: DEMO gets not-found for OTHER's B200, OTHER sees B200; non-UUID user_id gives not-found; no shipping_address in output.
  - search_products, get_product_details (found and not found), get_refund_policy: ok.
  - issue_refund: shipped A101 refused; other customer's B200 refused; amount 0 and above total refused; first call creates request; second call returns `already_refunded: true` with amount still 1000. DB has exactly 1 refund row for A100 (live).
- Teardown: `down -v --remove-orphans` on p3verify only. 0 containers, volumes, networks left. Built images `p3verify-*` remain locally (not removed; harmless, remove with `docker image rm` if wanted).
- Frontend typecheck (`npm run typecheck`): rc 0.

## 5. `demo-user` references

| Location | Kind | Verdict |
|----------|------|---------|
| `backend/tests/db/test_shop_queries.py:95` | test asserting non-UUID `demo-user` is not found | intentional negative |
| `backend/tests/db/test_migrations.py:81` | legacy-shape row insert for upgrade test | intentional |
| `frontend/src/components/chat-widget.tsx:22` | comment on stale localStorage value | OK |
| `plans/**` (spec, implementer and reviewer reports) | history | OK |
| `frontend/dist/**` bundle | stale build output | gitignored (`frontend/.gitignore`), not in diff, not served from repo |

`seed_data.py` no longer has `demo-user`. `docs/` has no references. Chat widget default is `11111111-1111-4111-8111-111111111111`, which matches seed `DEMO_CUSTOMER_ID`. Stale non-UUID localStorage values are ignored.

## 6. Secrets

- Scanned 3008 added lines (tracked diff plus untracked new files) for private keys, AWS/OpenAI-style keys, DSNs with passwords, and Fernet-shaped keys. No real secret found.
- Only hit: `backend/tests/db/test_seed.py:15` `STAFF_PASSWORD = "StaffDemoPass1234"`. Test fixture literal, not used by product code. Low.
- `.env.example` is tracked; secret fields hold `change...` placeholders or are empty.
- `.env` and `backend/.env` are git-ignored and not tracked. Real `.env` content was never read (only `git check-ignore` on names).

## 7. Live stack

- Baseline (taken before any action) and after: same 5 containers (`agent-demo-{frontend,api,mcp-server,migrate,db}-1`), same IDs, api/mcp/db still healthy with uptime uninterrupted (no restart). `agent-demo-migrate-1` still exited 0 from earlier run.
- Volume `agent-demo_pgdata` untouched. migrate was never run against it.
- Other `techkids-*` containers, exited, not touched.

## 8. Non-blocking observations

- N1 (weak test): `search_products` accent check uses query `dien thoai`, returns 0 rows, and only asserts the result is a list. It does not prove accent folding through MCP. Accent behaviour is only covered by DB tests. Suggest a query that matches a product name with diacritics.
- N2 (silent partial order): `seed.py` `_seed_orders` inserts `order_items` with `INSERT ... SELECT ... FROM products WHERE slug=...`. If the demo product rows are missing, the order is created with total from the code constants and zero item rows, with no error. Only reachable with a partially populated catalog. Suggest failing the seed or asserting item count.
- N3 (error code): append-only and write-once triggers raise SQLSTATE 23001 (restrict_violation), not P0001. Blocking works. Retention or API error mapping should match 23001. Spec does not name a code.
- N4 (status machine in app only): DB enforces CHECK on status values, not transitions. Probes show `approved` to `paid_out` and `rejected` to new `pending_staff` accepted by DB. Partial unique index guards the live-request rule. Transition rules (e.g. `paid_out` terminal) depend on the app.
- N5 (data loss on upgrade, documented): migrate on an old dev volume deletes legacy orders and refunds. Verified on legacy-shape DB. Implementer already lists this as an open question.
- N6 (identity, out of phase scope): agent still takes `user_id` from chat body. Unchanged from HEAD; the UUID change does not add protection.

## 9. Recommendations / next steps (priority)

1. Decide N2: fail seed when demo products are missing, or assert item count. Small change.
2. Decide N4: add DB transition guard (trigger) or document app-only enforcement in phase 4/5 plan.
3. Fix N1 test to use a diacritic product-name query.
4. Map trigger SQLSTATE 23001 in the phase 4/5 error layer (N3).
5. Optional: remove leftover `p3verify-*` images.

## Unresolved questions

1. Is SQLSTATE 23001 acceptable for append-only and write-once triggers, or should they raise P0001 or a custom code for clearer handling?
2. Should refund and order status transitions be enforced at DB level (trigger), or is app-only enforcement intended?
3. Should seed fail loudly when demo products are missing (N2)?
4. Is silent deletion of legacy dev orders and refunds on migrate acceptable for the live dev volume? Needs owner sign-off before running migrate on `agent-demo_pgdata`.
5. Keep the test-only staff password literal in `test_seed.py`, or move to env?
6. Remove the local `p3verify-*` images?

## Notes on the run

- A stray `curl -o /tmp_unused` was issued (no URL, so nothing was written; `ls` confirms the path does not exist). A later cleanup attempt on that path was blocked by a safety check and was not retried or worked around. Nothing to clean.
- Throwaway passwords, Fernet keys and env files live only in the scratchpad (`C:\Users\ADMIN\AppData\Local\Temp\claude\C--Users-ADMIN-Desktop-code-agent-demo\d679f958-dfab-47ba-938d-35a19fb62c9e\scratchpad\`). Temp DBs and the temp container were removed with the container.
- Probe output: `scratchpad\probe-clean.txt`, `scratchpad\probe-clean.json`. Check logs: `scratchpad\check-db-run1.log`, `check-db-run2.log`, `check-nodb.log`.

**Status:** DONE_WITH_CONCERNS
**Summary:** Phase 3 holds up under independent checks: check.sh green twice with DB (141 pass, 1 embedding skip), correctly fails without DB, migrations round-trip cleanly, seed is idempotent, legacy 0001-shape data upgrades, 84/84 privilege and constraint probes pass, and an isolated full stack passes product contract, 5 MCP tools with tenant isolation, and refund idempotency. Live stack untouched. Concerns are non-blocking: silent partial order seeding (N2), DB-level status transitions not enforced (N4), and trigger SQLSTATE 23001 to map (N3).
