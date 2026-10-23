# Plan A phase 2 (Alembic + SQLAlchemy foundation): independent verification

Date: 2026-10-23. Tester, independent. Implementer claims treated as unverified.
Did not read `.env`. Temp Postgres `tester-p2-pg` (pgvector:pg17, port 55436) removed. Isolated compose project `p2verify` torn down with `down -v --rmi local`. Live stack untouched.

## 1. Test and build results

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1a | `scripts/check.sh` without TEST_DATABASE_URL | PASS (exit 0) | ruff OK; pytest 10 passed, 9 skipped; pip-audit clean; frontend typecheck OK; npm audit high 0. Prints "SKIP alembic check và test DB" then "TẤT CẢ ĐẠT" |
| 1b | `scripts/check.sh` with TEST_DATABASE_URL (superuser DSN, temp PG) | PASS (exit 0) | ruff OK; pytest 19 passed; pip-audit clean; typecheck OK |
| 1c | Full pytest, DB, run 1 / run 2 | PASS, 19/19 both | 10.44s / 7.92s. No flakiness seen |
| 1d | Full pytest, no DB | 10 passed, 9 skipped | Skip reason printed per DB test: "TEST_DATABASE_URL chưa đặt" |
| 1e | Slowest tests | `test_two_concurrent_bootstrap_processes` 1.98s; `test_upgrade_downgrade_upgrade` 0.75s | Nothing above 2s |
| 2a | `python -m app.db.bootstrap` on empty DB (host, temp PG) | PASS (exit 0) | Steps: extension/roles, alembic upgrade 0001, LangGraph tables, GRANT, seed, done |
| 2b | alembic downgrade base, upgrade head | PASS | `history`: `<base> -> 0001 (head)`; `current` 0001 |
| 2c | `alembic check` after bootstrap | PASS | "No new upgrade operations detected.", exit 0. LangGraph tables not proposed for DROP |
| 2d | `alembic check` while shop tables dropped | FAIL as expected (drift detected) | "FAILED: Target database is not up to date.", non-zero exit (reported as 127 through the `uv run` wrapper) |
| 2e | Two concurrent bootstraps, fresh DB `shopbot_race` | PASS, both exit 0 | `alembic_version` 1 row, products 16, orders 3 (seed not doubled) |
| 2f | Re-bootstrap on populated DB (idempotent) | PASS (exit 0) | Re-GRANTs applied |
| 2g | App role DDL (`shopbot_app`) | PASS: all DENIED, SQLSTATE 42501 | CREATE TABLE (public and no schema), DROP TABLE, ALTER TABLE, TRUNCATE alembic_version, CREATE INDEX, CREATE SCHEMA, CREATE EXTENSION, CREATE FUNCTION |
| 2h | App role DML | PASS | SELECT/UPDATE products OK; SELECT checkpoints OK; SELECT/UPDATE alembic_version DENIED |
| 2i | MCP role (`shopbot_mcp`) grants | PASS, exactly as claimed | `products` SELECT; `orders` SELECT; `refunds` SELECT,INSERT. UPDATE/DELETE, checkpoints, store, alembic_version, CREATE all DENIED. Refund INSERT probe reached FK check (23503) so privilege present |
| 2j | Role attributes | PASS | app, mcp, migrator: not superuser, no createdb/createrole/bypassrls |
| 2k | Migrator DDL (control) | PASS | CREATE TABLE OK (probe rolled back) |
| 2l | Legacy volume (products table owned by superuser, as old `ensure_schema` made) | Bootstrap exit 1, fails fast | `DuplicateTable: relation "products" already exists` at alembic upgrade. Matches implementer note (needs `down -v` or stamp). Stamp path NOT tested |
| 3a | Isolated compose `-p p2verify`, env file in scratchpad, API_PORT=18000, FRONTEND_PORT=13000 | PASS | `config` resolved: published 18000/13000; network `p2verify_internal`; volume `p2verify_pgdata`; db has no host port |
| 3b | `migrate` service | PASS, exit 0 | Logs: bootstrap steps, "Bootstrap xong". Fresh volume |
| 3c | `db`, `mcp-server`, `api` | PASS, healthy | api and mcp healthy. mcp DB role `shopbot_mcp`; api DB role `shopbot_app` (checked via `urlsplit`, password not printed) |
| 3d | DDL at runtime | PASS: none | `log_statement=ddl` enabled during requests. Only DDL logged was my own `ALTER SYSTEM RESET`. Restored afterwards |
| 3e | api role probe from inside api container | PASS | CREATE TABLE and ALTER TABLE: 42501. SELECT products: OK |
| 3f | MCP over internal network (from api container) | PASS | tools: lookup_order, search_products, get_product_details, get_refund_policy, issue_refund. search_products returned 4 items; policy text returned; lookup_order for foreign user returns "not found"; issue_refund on a shipped order returns ok=false and writes nothing (refunds count stayed 0) |
| 3g | Chat graph under role app | PASS (partial) | Chat request returned 502 with graceful message because LLM URL is dummy. Checkpoints table has 2 rows for the thread, so app role wrote them. Full LLM path not exercised (see Q6) |
| 3h | Teardown | PASS | `down -v --rmi local`: volume, network, images removed. Nothing with `p2verify` left |

## 2. Regression (endpoints and contracts)

| Endpoint | Isolated (new code, dummy LLM) | Live (old code) | Note |
|----------|-------------------------------|-----------------|------|
| GET /health | 200 | 200 | Same |
| GET /ready | 200 | not tested | Graph initialised |
| GET /v1/products, no key | 401 | 401 | Same auth behaviour |
| GET /v1/products, with key | 200 (16 items) | not tested | Key from scratchpad env |
| GET /v1/products/nonexistent | 404 | not tested | |
| POST /v1/chat | 502 "Agent gặp lỗi..." | not tested | Expected: dummy LLM. Live POST skipped because it writes to live DB |
| Frontend GET / | 200 | localhost:3000 200 | See note N1 |
| Frontend GET /api/health | 200 | not tested | nginx proxy works |
| Frontend GET /api/v1/products | 200 | not tested | Proxy adds X-API-Key |

Route list in code: `/health`, `/ready`, `/v1/products`, `/v1/products/{slug}`, `/v1/chat`, `/v1/chat/{id}/resume`. No route change seen. Frontend has no changes in git status. Frontend typecheck passed.

### Public env contract changes (names)

- **Required new:** `PAYOUT_ENCRYPTION_KEY` (api; must be valid Fernet, else api refuses to start). `MIGRATOR_DB_PASSWORD`, `APP_DB_PASSWORD`, `MCP_DB_PASSWORD` (each >= 12 chars, not placeholder). `BOOTSTRAP_DATABASE_URL` (migrate only, superuser DSN, set by compose from POSTGRES_*).
- **Removed from api env:** `SEED_DEMO_DATA` (now migrate only). `ensure_schema` gone.
- **Optional new, with defaults:** `SHIPPING_FEE_VND` 30000, `FREE_SHIPPING_FROM_VND` 500000, `REFUND_WINDOW_DAYS` 7, `DB_POOL_MAX`, `SA_POOL_SIZE`, `SA_MAX_OVERFLOW`, `LANGGRAPH_POOL_MAX`.
- **Same name, new value:** `DATABASE_URL` for api is now role `shopbot_app`; for mcp-server it is role `shopbot_mcp`.
- **Unchanged names:** `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `EMBEDDING_*`, `API_KEY`, `CORS_ORIGINS`, `AGENT_MAX_STEPS`, `LOG_LEVEL`, `API_PORT`, `FRONTEND_PORT`, `POSTGRES_USER|PASSWORD|DB`, `MCP_HOST`, `MCP_PORT`, `MCP_SERVER_URL`.
- **Breaking for existing `.env`:** the four new secrets must be added before `docker compose up`. Existing pgdata volume is incompatible (see 2l).

## 3. Live stack

- `docker ps`: 4 original containers (`agent-demo-frontend-1`, `-api-1`, `-mcp-server-1`, `-db-1`) still up with the same uptime. Volume `agent-demo_pgdata` present. Ports 3000, 8000 unchanged.
- Live GETs were read-only (`/health`, `/v1/products`, `/`). No live POST.
- N1: `curl 127.0.0.1:3000` timed out once for me, while `localhost:3000` returned 200 and the live nginx log shows 200 for my request. Host port-proxy quirk, not container fault. Not reproduced further.

## 4. Secrets and config (no `.env` read)

- Tracked diff (`git diff HEAD`): no literal secret. Only hit is the compose template `postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db...`, which is interpolation.
- Untracked new files: only test-only literals (`backend/tests/db/conftest.py`: `migrator-test-pass-1` etc.; `test_settings.py`: dummy `u:p@h/d`). No real key or DSN.
- `.env`: not tracked by git, ignored (`.gitignore:1`). Not read. Mtime 2026-10-23 09:00:45; not modified by my runs.
- `.env.example`: placeholders only (`change-me-*`, empty `API_KEY`/`PAYOUT_ENCRYPTION_KEY`).
- `.dockerignore` excludes `.env`. Dockerfile copies only `backend/app`, `alembic.ini`, `migrations`. No secret baked into image.
- Repo state: tracked diff identical to start (17 files, 489+ / 134-). Untracked list unchanged except `plans/reports/from-code-reviewer-to-cook-plan-a-phase-02-review-report.md`, written by another agent, not me.

## 5. Findings

| ID | Sev | Finding | Repro | Fix |
|----|-----|---------|-------|-----|
| F1 | MED | No `ALTER DEFAULT PRIVILEGES` (spec requires it). Grants are one-shot `GRANT ... ON ALL TABLES` in `apply_grants`. Any alembic upgrade outside bootstrap that creates or recreates tables leaves app/mcp without access. Fails closed, no security hole | `alembic downgrade base && alembic upgrade head`, then as app `SELECT count(*) FROM products` gives 42501. Same for mcp. Re-running bootstrap restores (verified) | Add `ALTER DEFAULT PRIVILEGES FOR ROLE shopbot_migrator IN SCHEMA public GRANT ... TO shopbot_app` and mcp grants, or a test that asserts it |
| F2 | MED | `check.sh` passes (exit 0, "TẤT CẢ ĐẠT") when neither TEST_DATABASE_URL nor ALEMBIC_DATABASE_URL is set. `alembic check` is silently skipped. Spec says the gate must block model drift | Run check.sh with no DB env: only a SKIP line | Fail, or require explicit opt-out flag, when DB is not configured |
| F3 | LOW | App role can `CREATE TEMP TABLE` (PG default grants TEMPORARY to PUBLIC). "No DDL" holds for schema objects only | `CREATE TEMP TABLE` as shopbot_app: OK | `REVOKE TEMPORARY ON DATABASE <db> FROM PUBLIC` |
| F4 | LOW | Legacy volume path not tested: bootstrap fails fast (good) but stamp recipe in docs is untested | 2l | Test stamp on a copy of an old volume before real deploy |
| F5 | INFO | MCP server has no app-layer auth. Only network isolation (no host port published, verified in compose config) protects it | Read `mcp_server/server.py` | Acceptable for phase 2. Revisit in phase 3 |
| F6 | INFO | Every chat with a dummy embedding URL logs ERROR traceback "memory recall failed" | api logs | Expected with dummy URL. Not a regression |
| F7 | INFO | Implementer report item 8 (`taskkill /IM python.exe`) cannot be verified from here. Live stack unaffected | Report text | Ask owner what was killed |

## 6. Recommendations

1. Fix F1 (default privileges) before phase 3 adds tables. Add a test: after `alembic upgrade` only, app can SELECT new table.
2. Fix F2: make `scripts/check` fail without a DB or with an explicit skip flag. Otherwise the drift gate is decorative.
3. Decide on F3. Revoke TEMP for app if "no DDL" is meant strictly.
4. Test the stamp path for legacy volumes (F4) and document the exact commands.
5. Tick success criterion 1 (`api lên trong compose`) now that the isolated run covers it, if the user accepts the dummy-LLM limitation (Q6).

## 7. Unresolved questions

1. Should F1 (`ALTER DEFAULT PRIVILEGES`) be added now, given the spec explicitly lists it?
2. Should `check.sh` fail when no DB is configured (F2), or is skipping acceptable for manual runs?
3. Is `CREATE TEMP` for the app role acceptable (F3)?
4. Who owns the `taskkill /IM python.exe` side effect in the implementer report (F7)? Did it kill anything the user needed?
5. The stamp path for legacy volumes is documented but untested (F4). Test before deploy?
6. Full chat happy path needs a real LLM. Only the fake-graph test under role app plus a dummy-LLM 502 were run. Is that enough to tick success criterion 1?
7. Should the implementer's unticked success criterion 1 be ticked after this verification?

**Status:** DONE_WITH_CONCERNS
**Summary:** Phase 2 holds: check.sh green with and without DB (19 and 10+9 skipped), migrate exit 0 on fresh and concurrent runs, app role denied all DDL, mcp grants exactly as claimed, isolated full stack up healthy with no runtime DDL, live stack untouched. Concerns: F1 (no default privileges, spec deviation), F2 (alembic check silently skipped in default gate).
