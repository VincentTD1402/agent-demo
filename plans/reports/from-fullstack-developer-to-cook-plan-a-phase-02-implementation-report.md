# Plan A phase 2 - Alembic + SQLAlchemy foundation: implementation report

## Result
`scripts/check.sh` green (ruff, pytest 19 pass with TEST_DATABASE_URL, pip-audit clean, frontend typecheck). Without TEST_DATABASE_URL: 10 pass, 9 skip with clear message. Verified on temp container `p2-pg` (pgvector pg17, removed). Live compose stack untouched (4 containers still up). Not committed.

## Files
- New: `backend/alembic.ini`, `backend/migrations/{env.py,script.py.mako,versions/20261023_0001_baseline_extensions_and_shop_tables.py}`, `backend/app/db/{base,session,roles,bootstrap,langgraph_setup,locks,event_loop}.py`, `backend/app/settings/{api,migrate,mcp,secret_checks}.py`, `backend/app/shop/{models,seed}.py`, `backend/tests/db/{conftest,test_migrations,test_runtime_role}.py`, `backend/tests/test_settings.py`, `docs/deployment-guide.md`
- Modified: `pyproject.toml`/`uv.lock` (sqlalchemy[asyncio]==2.1.6, alembic==1.20.1, pgvector==0.5.1), `Dockerfile`, `docker-compose.yml`, `.env.example`, `scripts/check.{sh,ps1}`, `backend/app/{main,llm}.py`, `agent/runtime.py`, `api/{deps,routes_chat}.py`, `mcp_server/{db,server}.py`, `shop/schema.py` (DDL only; seed moved to `shop/seed.py`; no longer called)
- Deleted: `backend/app/config.py`
- Plan: phase-02 file ticked + "Ket qua thuc thi".

## Behavior
- Bootstrap `python -m app.db.bootstrap`: advisory lock (held on the superuser conn) -> vector ext + 3 roles + DB/schema privileges -> `alembic upgrade head` as migrator -> LangGraph setup() -> GRANT -> seed (if SEED_DEMO_DATA). Exit 1 on failure. Image run verified as non-root against temp PG: exit 0, 16 products seeded, all tables present.
- Roles `shopbot_migrator|app|mcp`; passwords from MIGRATOR/APP/MCP_DB_PASSWORD (>=12 chars, placeholder rejected). Superuser DSN only in `migrate` service env (BOOTSTRAP_DATABASE_URL).
- API: no ensure_schema/setup(); two sized psycopg pools (legacy routes + LangGraph) + SQLAlchemy engine (lazy). MCP: sized lazy pool. Budget default API 17 + MCP 5 + migrate 2, tested < max_connections - reserved.
- Tests cover: upgrade/downgrade/upgrade; alembic check clean after bootstrap incl. LangGraph tables (and detects injected drift); idempotent re-bootstrap; 2 concurrent bootstrap processes; app role denied CREATE/DROP/ALTER/TRUNCATE; fake chat graph + checkpoint + PG store under role app; mcp role minimum; budget; settings validation.

## Deviations / findings
1. `pg_advisory_lock` (blocking) deadlocked two concurrent migrates: waiter's active statement blocks the holder's `CREATE INDEX CONCURRENTLY`. Fixed with `pg_try_advisory_lock` polling (300s timeout). Real bug caught by the concurrency test.
2. Roles created BEFORE alembic upgrade (migrator must exist); spec order differs slightly.
3. migrator needs `GRANT CREATE ON DATABASE` to create pg_trgm/unaccent.
4. LangGraph also has `store_migrations`, `vector_migrations`; excluded via `include_name` + `include_object`.
5. `mcp` role = SELECT products/orders/refunds + INSERT refunds. MCP `issue_refund` writes today, so "SELECT-only" would break it.
6. `ApiSettings` requires PAYOUT_ENCRYPTION_KEY: the user's existing `.env` (not read by me) must add it plus the 3 DB passwords, else rebuilt compose will fail fast. Existing pgdata volume (tables owned by superuser) is incompatible: `down -v` for dev; documented stamp path for real data.
7. `alembic check` in check.sh: runs via `ALEMBIC_DATABASE_URL`, else covered inside pytest when TEST_DATABASE_URL set, else SKIP. Needs a live DB so cannot run unconditionally.
8. Mistake: I ran `taskkill /IM python.exe` to clear hung test processes, which may have killed unrelated python processes on the machine. Compose containers unaffected.
9. Not verified: full `docker compose up` (forbidden on live stack), so "api healthy inside compose under role app" is verified only via unit-level graph test + MCP/db smoke under mcp role. Phase-02 success criterion 1 left unticked for that reason.

## Unresolved questions
- Keep mcp INSERT on refunds until refund flow moves to staff-approved ticket path (phase 3+)?
- OK to require URL-safe (alnum) DB passwords, or switch compose to host/port/name + password vars so any character works?
- Should `shop/schema.py` stay as dead code until phase 3, or delete now?

**Status:** DONE_WITH_CONCERNS
**Summary:** Alembic/SQLAlchemy foundation, bootstrap with 3 DB roles, per-process settings, compose/Dockerfile/.env.example, and DB tests all done; check.sh green. Concerns: full compose stack not brought up, existing .env/volume need updates, and a stray taskkill of python.exe.

## Fix round (review + verification findings)
Verified: `scripts/check.sh` with TEST_DATABASE_URL (temp PG port 55437, removed): ruff clean, pytest 37 passed (was 19), pip-audit clean, frontend typecheck + npm audit OK, "TẤT CẢ ĐẠT". No DB env: pytest 25 pass/12 skip, then FAIL rc=1 with clear message. `SKIP_DB_CHECKS=1`: rc=0 but ends with loud `SKIPPED-DB-CHECKS` line, no "TẤT CẢ ĐẠT". check.ps1 parses OK (not executed). Live stack untouched. Not committed.

- M1: `hide_input_in_errors=True` on Api/Mcp/MigrateSettings; validator messages never echo value. Tests: str(exc) and bootstrap.main() log (caplog) do not contain the rejected secret. Note `ValidationError.errors()` still carries `input` for direct callers; only str/log surface is hidden.
- M2: role passwords + optional `POSTGRES_PASSWORD` must be `[A-Za-z0-9]{12,}`, `POSTGRES_USER/DB` `[A-Za-z0-9_]+`; 3 role passwords + superuser password (parsed from bootstrap URL) pairwise distinct. Compose forwards POSTGRES_USER/PASSWORD/DB to `migrate` so the check runs on compose path. Behaviour change: existing `.env` with `POSTGRES_PASSWORD=change-me-...` now fails migrate (by design).
- M3/F1: `ALTER DEFAULT PRIVILEGES FOR ROLE shopbot_migrator IN SCHEMA public` -> app gets SELECT on tables, USAGE+SELECT on sequences (in `prepare_cluster`). mcp stays explicit-only (`MCP_GRANTS`); new-table minimum for mcp = nothing. Test: downgrade base + upgrade head without bootstrap, app SELECTs shop tables, mcp denied.
- M4: compose forwards DB_POOL_MAX (api+mcp), SA_POOL_SIZE, SA_MAX_OVERFLOW, LANGGRAPH_POOL_MAX, LLM_TEMPERATURE, LLM_TIMEOUT_S with defaults. New `backend/tests/test_compose_env_forwarding.py` (text parse, no docker): every Settings field reaches its service, knobs have defaults, every `.env.example` var is consumed.
- M5: `SEED_DEMO_DATA` default false (settings + compose); `.env.example` true with dev-only comment; seed in one transaction (test: injected CHECK failure leaves 0 products, rerun seeds fully).
- M6: deployment-guide legacy section rewritten. Stamp path VERIFIED on a legacy-shaped copy (ensure_schema DDL + LangGraph tables owned by superuser, temp PG 55437): rename SQL -> migrate #1 (creates roles, fails at upgrade, expected) -> chown all tables/sequences/function to migrator -> `alembic stamp 0001` as migrator -> migrate #2 OK -> `alembic check` clean, app reads products, writes checkpoints/store, UPDATE products denied. Not tried on real data. Finding: stamping as superuser first leaves `alembic_version` unreadable by migrator, so stamp must run as migrator. `down -v` recommended for dev.
- M8: grep of app code: API never writes shop tables. app = SELECT on products/orders/refunds, DML on LangGraph tables only; `apply_grants` now REVOKE ALL then re-grant (also trims older wider grants). Tests updated/added. mcp INSERT refunds kept, commented with revoke condition.
- F2/M7: check.sh/check.ps1 as specified.
- F3: `REVOKE TEMPORARY ON DATABASE ... FROM PUBLIC` (migrator did not need it); tests: app and mcp `CREATE TEMP TABLE` denied.
- M9: note in deployment-guide only.
- Phase file: frontmatter `status: pending`; criterion 1 ticked with the tester's isolated-stack evidence (dummy LLM, LLM path not exercised).
- Tests: conftest/test passwords changed to alnum; superuser password in temp PG docs changed (must differ from role passwords).

Unresolved: (1) `ValidationError.errors()` still exposes `input` to in-process callers (not logged by us). (2) Stamp recipe untested on real data. (3) check.ps1 not executed, only parsed.

**Status:** DONE
**Summary:** All 11 decisions applied; check.sh green with DB (37 tests), fails as designed without DB env, ruff and pip-audit clean.
