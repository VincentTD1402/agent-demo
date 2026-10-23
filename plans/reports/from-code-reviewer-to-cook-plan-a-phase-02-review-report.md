# Plan A phase 2 review (Alembic + SQLAlchemy foundation)

Scope: uncommitted diff vs 449ca87. ruff clean; pytest 10 pass / 9 skip (no TEST_DATABASE_URL here; DB tests not re-run by me, reviewed by reading). No code file >200 lines (max 104). No Critical issues. Superuser DSN isolation, SQL quoting, lock release, non-root image all OK (see Positive).

## Critical
None.

## High
None blocking. Items M1/M2/M3 are the ones to fix before phase 3.

## Medium

M1. Rejected secrets echoed into logs. `settings/migrate.py:35` + `settings/secret_checks.py` + `db/bootstrap.py:34,55`. `MigrateSettings()` is built inside `run()` under `try/except -> log.exception`. Pydantic ValidationError prints `input_value='<raw value>'` (verified by running it: `input_value='sh0rtSECRET'`). Scenario: operator sets a too-short/near-miss password (e.g. real password minus 1 char) -> full value lands in `docker logs migrate`/log aggregator. Same for `ApiSettings.payout_encryption_key` (`settings/api.py:51`: a typo'd Fernet key is printed at API startup). Fix: `model_config = SettingsConfigDict(hide_input_in_errors=True)` on all 3 settings classes.

M2. Password charset rule documented but not enforced; URLs built unencoded. `.env.example:22`, `docs/deployment-guide.md:24` say "chi chu-so" but `require_strong_secret` only checks length/prefix. Compose builds `postgresql://shopbot_app:${APP_DB_PASSWORD}@db...` (`docker-compose.yml` mcp-server/api DATABASE_URL) and `BOOTSTRAP_DATABASE_URL: ...${POSTGRES_PASSWORD}@db` with no encoding. Scenario: `APP_DB_PASSWORD=ab/cd#ef12345` passes validation, migrate succeeds (make_url re-encodes for migrator), api fails at runtime with an obscure DNS/auth error; a `$` also gets compose-interpolated. Fix: validator `^[A-Za-z0-9]{12,}$` for the 3 role passwords (cheap, matches doc), or compose host/port/user/password vars and build DSN in settings. Also POSTGRES_PASSWORD (superuser, pre-existing) has the same URL problem in BOOTSTRAP_DATABASE_URL.

M3. No default privileges for future tables (spec says `ALTER DEFAULT PRIVILEGES`/GRANT; impl only re-GRANTs `ALL TABLES` in `db/roles.py:57 apply_grants`). Scenario: phase 3 adds a table; dev runs `alembic upgrade` directly (spec requirement "chay duoc local") or a future LangGraph version adds a table via a path other than bootstrap -> `shopbot_app` gets "permission denied" at runtime, not at deploy. Fix: in `prepare_cluster` (or apply_grants) `ALTER DEFAULT PRIVILEGES FOR ROLE shopbot_migrator IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO shopbot_app; ... GRANT USAGE,SELECT ON SEQUENCES TO shopbot_app` (run as/for migrator). Keep mcp explicit-only.

M4. Pool-size knobs inert in compose. `.env.example:47-52` documents `DB_POOL_MAX/SA_POOL_SIZE/SA_MAX_OVERFLOW/LANGGRAPH_POOL_MAX`, but `docker-compose.yml` api and mcp-server `environment:` do not forward them (env_file was removed; every var is now an explicit allow-list). Scenario: operator scales budget for 3 replicas by editing .env -> no effect, budget math in deployment-guide wrong. Same silent loss for `LLM_TEMPERATURE`/`LLM_TIMEOUT_S` (were reachable via old `env_file: .env`, no longer forwarded) = accidental behaviour change. Fix: forward them with `${VAR:-default}`.

M5. Demo seeding defaults ON in production paths. `settings/migrate.py:24` (`seed_demo_data: bool = True`) and compose `SEED_DEMO_DATA: ${SEED_DEMO_DATA:-true}`. Scenario: prod .env omits the flag -> fake products and delivered demo orders (refund-eligible) are inserted into the prod DB at first deploy. Fix: default false in settings+compose; keep `true` only in `.env.example` for dev. Related low: `shop/seed.py:15-33` runs autocommit, non-transactional; crash mid-seed leaves partial products, re-run sees count>0 and never completes -> wrap in one transaction.

M6. Existing-volume migration path in docs is incomplete/inaccurate. `docs/deployment-guide.md:14`. (a) Old DB: LangGraph tables are also superuser-owned; `setup()` succeeds (IF NOT EXISTS), `apply_grants` as migrator silently grants nothing on them -> API starts, first chat -> permission denied. Doc only mentions shop tables. (b) After `alembic stamp 0001` index/constraint names differ from models (`products_category_idx` vs `ix_products_category`, `products_pkey` vs `pk_products`, check-constraint names) -> `alembic check` reports drift forever; `immutable_unaccent()`/`pg_trgm`/`unaccent` are skipped by stamp (currently unused by repo.py, which only uses ILIKE, but latent). Fix doc: change owner of ALL tables incl. LangGraph + sequences, rename indexes/constraints (or write a reconcile revision), create the function.

M7. `scripts/check` is fail-open for the new gate. `scripts/check.sh:15-23`, `check.ps1:16-20`. With neither `ALEMBIC_DATABASE_URL` nor `TEST_DATABASE_URL`, check prints SKIP and exits green: 9 DB tests + `alembic check` never run, so "chan model lech migration" is not enforced by default (it was green-with-skip in my run). Acceptable only if CI sets one var; at minimum document in the Success Criteria, or make check fail unless `SKIP_DB=1`.

M8. App role broader than needed. `db/roles.py:53-54`: `shopbot_app` gets INSERT/UPDATE/DELETE on products/orders/refunds. API code only reads products (`api/routes_products.py`, `shop/repo.py`) and LangGraph tables; no shop-table writes exist. Scenario: SQL-injection/bug in API can rewrite orders or insert refunds, bypassing MCP checks. Fix: app = SELECT on shop tables now, DML only on LangGraph tables (`LANGGRAPH_TABLES` already exists); widen in the phase that adds writes. Spec text said "DML on business + LangGraph" so this is a spec-vs-least-privilege call; ask user.

M9. Role password in server logs. `db/roles.py:28`: `CREATE/ALTER ROLE ... PASSWORD '<literal>'`. Quoting/injection is safe (`sql.Literal`, `sql.Identifier`; role names are constants, db name from URL goes through Identifier). But Postgres logs the statement text (log_statement=ddl, or log_min_error_statement on any error in that statement) with the cleartext password. Fix: send a SCRAM-SHA-256 verifier computed client-side (`psycopg`/passlib-free: hashlib+pbkdf2) or `SET log_statement='none'; SET log_min_error_statement=panic` (superuser-settable) for the session before role statements.

## Low

L1. Plan bookkeeping honesty: phase file frontmatter `status: completed` while Success Criteria #1 is unticked; todo item 3 ("chay API bang role app") is ticked though only the graph/saver was exercised under role app, not `main.lifespan`/compose. Set status to in-progress/"completed-with-caveat" or tick only after one compose run on a throwaway project name (`docker compose -p p2test`). Also deviations from spec not marked: one shared pool for saver+store (spec: pool riêng), roles created before upgrade (noted), no `ALTER DEFAULT PRIVILEGES` (M3), `pgvector` dep added but unused (`grep` finds no import; YAGNI + extra pip-audit surface; drop until `Vector` model exists).

L2. `GRANT CREATE ON DATABASE` to migrator (`roles.py:40`) lets it create schemas; needed for trusted extensions only. Acceptable; consider REVOKE after upgrade. PUBLIC still has TEMP on the DB, so app/mcp can `CREATE TEMP TABLE` (the "no DDL" test only tries public). Consider `REVOKE TEMP ON DATABASE ... FROM PUBLIC`.

L3. No check that the 3 role passwords are distinct / differ from POSTGRES_PASSWORD; equal passwords collapse least-privilege. Add to `MigrateSettings` model_validator. Placeholder check is prefix-only (`secret_checks.py:6`).

L4. `ApiSettings`/`McpSettings` never verify the connected role (e.g. API accidentally given the superuser DSN works silently). Optional startup assertion: `SELECT rolsuper OR has_database_privilege(current_user,current_database(),'CREATE')` -> refuse to start.

L5. Role names are cluster-global (`shopbot_*`); two databases on one cluster with different .env passwords clobber each other (`_upsert_role` ALTERs every run). Document.

L6. `ensure_schema` kept as dead DDL (`shop/schema.py`), signature changed (dropped seed arg); no callers (grep clean). Spec says delete after phase 3: fine, but DDL there will drift from models.

L7. `include_object` index branch (`env.py:34`) is redundant once `include_name` filters tables; harmless. Advisory lock: no `connect_timeout` on `psycopg.connect(s.bootstrap_database_url)` (`bootstrap.py:34`); compose waits for db healthy so low. Poll timeout 300s fixed; holder legitimately slower (big backfill migration later) makes the waiter fail -> compose stack exits non-zero though holder succeeds. Make timeout configurable.

L8. MCP role test (`test_runtime_role.py:57`) never exercises the real MCP paths (`get_order` LEFT JOIN refunds, `create_refund` INSERT..ON CONFLICT..RETURNING, then SELECT). Add one test calling `mcp_server.db` functions under role mcp, otherwise a missing grant (e.g. RETURNING needs SELECT) is only caught in prod.

L9. Process: implementer ran `taskkill /IM python.exe` machine-wide (report item 8). Ask user whether anything else (other dev servers) died; not a code issue.

## (a) Acceptance criteria
- Alembic+env.py+include_object: met (tests: drift detected, LangGraph excluded; also `store_migrations`, `vector_migrations` handled).
- migrate service + roles + LangGraph GRANT: met except default privileges (M3).
- setup() removed from runtime.py: met (`agent/runtime.py` no DDL). API-as-app: partially (graph only; see L1).
- Settings per process + budget: met (formula in docs; math 17+5+2 < 97 ok; actual migrate peak = lock conn + 1 = 2, correct). Test only checks defaults, not compose overrides (M4).
- Success #1 unticked: honest. #2/#3 ticked: plausible per tests (not re-run here).
- Non-functional "roll-forward-only, downgrade no-op for extension": met (`versions/...0001:84-88`; downgrade drops tables+function only).

## (b) Regression walk
Config.Settings deleted: grep of app, backend/tests, scripts, docs, compose finds no remaining `app.config`/`get_settings` users; all migrated to `get_api_settings` (deps.py, routes_chat.py x3, llm.py, main.py, runtime.py) and `get_mcp_settings` (server.py, mcp_server/db.py). `backend/scripts/spike_langgraph.py` uses own env, fine. Agent graph: `open_runtime(s, pool)` signature changed, only caller main.py updated; saver/store on shared pool autocommit+dict_row as LangGraph requires; pool starvation unlikely (no nested acquisition), >5 concurrent chats queue with 30s PoolTimeout (previously serialized on 1 conn). MCP tools search/lookup/issue_refund: SQL unchanged, now pooled lazily; grants cover them (SELECT products/orders/refunds, INSERT refunds; FK check needs no extra privilege). /v1/products, /v1/chat: responses unchanged. `server.py` now reads settings at import: importing it without DATABASE_URL raises (only entrypoint imports it; tests do not).
MCP INSERT on refunds justified: `issue_refund` -> `create_refund` writes today. Keep; no UPDATE/DELETE granted, good. Revoke when refund flow moves to staff-approved ticket. DB itself does not enforce delivered/<=total (tool code does) - consider CHECK/trigger later.

## (c) Contract changes
Intentional: new required env `PAYOUT_ENCRYPTION_KEY`, `MIGRATOR/APP/MCP_DB_PASSWORD`; `BOOTSTRAP_DATABASE_URL`; `DATABASE_URL` now role app/mcp (superuser only in migrate); new optional `SHIPPING_FEE_VND`, `FREE_SHIPPING_FROM_VND`, `REFUND_WINDOW_DAYS`, pool vars; `SEED_DEMO_DATA` moved to migrate; 3 roles; extensions pg_trgm/unaccent; `immutable_unaccent()`; naming-convention constraint/index names; seed moved out of API start; old pgdata incompatible (documented).
Accidental: LLM_TEMPERATURE/LLM_TIMEOUT_S/pool vars no longer reach api (M4); index/constraint renames affect stamped legacy DBs (M6); `.env.example` copied verbatim now fails migrate on placeholder passwords (intended, but note in README quickstart). API response shapes, MCP tool signatures: unchanged.

## (d) Patterns
Follows existing style (Vietnamese docstrings, kebab-less snake modules, psycopg dict_row, pydantic-settings). Plan-reference rule: no phase/finding codes found in code comments. Dockerfile: non-root appuser retained, migrations root-owned read-only, `.dockerignore` excludes tests/.env. Compose: no `env_file` on any app service; superuser DSN only on `migrate`; mcp and api each get only their own role DSN; api does not receive MIGRATOR/MCP passwords. Good.

## (e) Lint/type/build
ruff clean. No mypy configured. Image build not run by me. Windows: `db/event_loop.py` Selector loop via `asyncio.run(loop_factory=...)` (3.12+) correct; used by bootstrap/tests only; alembic uses sync engine.

## Positive
Advisory lock design (try-lock polling, session lock released on conn close incl. crash, finding about CREATE INDEX CONCURRENTLY deadlock is real and well-documented); sql.Identifier/Literal used throughout, `f"...{table}"` in seed is constant-only; idempotent re-bootstrap + concurrent-process + drift tests; LangGraph exclusions verified by `alembic check` test; `REVOKE CREATE ON SCHEMA public FROM PUBLIC` handles PG<15; `:?` guards fail fast.

## Unresolved questions
1. M8: should `shopbot_app` be SELECT-only on shop tables until a phase needs writes?
2. M5: OK to flip seed default to false (user-confirmed business choice earlier was "true"? .env.example previously default true in old Settings) - user call.
3. M2: enforce alnum passwords (simple) vs host/port/password vars (more flexible)?
4. Will CI set TEST_DATABASE_URL so M7 is enforced?
5. Phase 3+: do we need pre-existing-volume migration at all (dev-only data?) - decides effort for M6.
6. MCP tools take `user_id` from LLM tool arguments; mcp role can read all orders, so tenant isolation rests on the graph injecting the real user_id (pre-existing, out of scope; confirm in phase 3).

**Status:** DONE_WITH_CONCERNS
**Summary:** No critical/high defects; role isolation, SQL quoting, lock handling and no-DDL app role hold up. Fix before phase 3: secret echo in validation errors (M1), unenforced password charset (M2), missing default privileges (M3), un-forwarded pool env vars (M4), seed default-on (M5), incomplete legacy-volume doc (M6).
