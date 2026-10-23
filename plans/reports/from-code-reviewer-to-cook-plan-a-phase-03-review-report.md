# Plan A phase 3 review (uncommitted vs e92ab22)

Scope: 7 revisions (0002-0007), models, roles.py, mcp_server/db.py+server.py, seed, kb/reindex, payout encryption, compose/.env.example, frontend chat-widget, deployment-guide. Ruff clean (re-ran). No file over 200 lines (max test_migrations.py 198). I did not re-run pytest (needs a TEST_DATABASE_URL Postgres); relied on the implementer's 141-pass claim plus reading tests by name.

Verdict: no leak of `users`, `shipping_address` or `payout_info_enc` to `mcp` found. Main issues are unguarded data-destroying migrations and the MCP refund behaviour change that is not communicated to the agent or the user.

## Critical
None.

## High

H1. Migrations 0004/0005 delete orders and refunds with no guard. `migrations/versions/20261023_0004_orders_items_and_agent_view.py:48-49` (`DELETE FROM refunds; DELETE FROM orders`), 0005 `:30`, and the downgrades at 0004 `:111-112`, 0005 `:79`.
- Scenario: any DB at 0001 head that holds real rows gets them silently destroyed. This includes the `stamp 0001` recipe in the deployment guide and any environment where MCP `issue_refund` already wrote refunds. A restore from `pg_dump` is the only recovery.
- This also contradicts the "roll-forward-only" policy: downgrade is destructive too.
- Fix: at the top of 0004 and 0005 `upgrade()`, run `SELECT count(*)`. If the count is greater than 0 and the `-x allow_destroy_legacy_orders=true` flag (read via `context.get_x_argument`) is absent, `raise RuntimeError("refusing to drop N legacy orders/refunds; ...")`. Better: migrate rows when possible (map text `user_id` to users), and fail if it cannot.
- Add a test: seed 0001-shape rows, `upgrade head` fails without the flag, succeeds with it.
- Also guard the downgrades the same way.

H2. MCP `issue_refund` now creates `pending_staff`, but the agent and the customer are not told. `mcp_server/server.py:63-83`, `mcp_server/db.py:62-85`, `agent/prompts.py:11-12`.
- It returns `{"ok": True, "already_refunded": False, ...}` with no `status` or pending message.
- The tool docstring still says "Hoàn tiền ... không hoàn lần hai". `REFUND_POLICY` (`server.py:17-20`) says "mỗi đơn hoàn một lần" and never mentions staff review or a 7-day window.
- The prompt says the HITL approval card is the approver, so the model will naturally tell the customer "đã hoàn tiền" while no money moved. D2 (plan.md:61) says money moves only after staff approval.
- `lookup_order.refunded_vnd` now reports a pending request's requested amount as "refunded". This is a semantic change presented as unchanged. The report calls it "additive", but the meaning of an existing field changed.
- Fix:
  - Return `status: "pending_staff"` and `message: "Đã tiếp nhận, chờ nhân viên duyệt"`.
  - Update the docstring and `REFUND_POLICY`.
  - Expose `refund_status` in the prompt guidance.
  - Do not fill `refunded_vnd` unless the status is `paid_out`.
  - No test covers the agent-facing wording; `tests/test_agent_graph.py` uses a stub tool.

H3. MCP refund rules are weaker than the plan, and the DB does not backstop them. `mcp_server/server.py:74-77`.
- The cap is `order.total_vnd`, which includes shipping. The plan requires goods only, minus the already-refunded part.
- `delivered_at` (already in the view) is never checked against `REFUND_WINDOW_DAYS`. A delivered order from a year ago is accepted.
- `delivered` + `delivered_at IS NULL` is allowed by the schema (no CHECK), so a window check would have nothing to read. Add `CHECK (status <> 'delivered' OR delivered_at IS NOT NULL)`.
- This was weak before the phase, but phase 3 now owns the refund schema and the window column.

## Medium

M1. `mcp` has table-wide INSERT on `refunds` (`db/roles.py:48` `MCP_INSERT_TABLES`, 0005 `:84`), plus `notifications`, `support_tickets` and `status_events`.
- A compromised or confused MCP can insert `status='paid_out'`, `approved_amount_vnd`, `decided_by`, `payout_info_enc`, or a refund for a user who does not own the order. There is no composite FK `(order_id, user_id)` and no CHECK that status is `pending_staff` on insert.
- The plan lists INSERT for mcp, but column-level INSERT is available. Fix: `GRANT INSERT (order_id, user_id, source, requested_amount_vnd, reason, idempotency_key, thread_id) ON refunds TO mcp`. Also add a BEFORE INSERT trigger (or CHECK) forcing `status='pending_staff'`.
- Same idea for `status_events` and `notifications`: mcp can forge staff-decision events for any user.

M2. The single live-refund unique index blocks Plan B's `system_cancel_paid` refund when the customer already has a pending request (0005 `:75-78`).
- A paid order is cancelled while a `customer_request` is `pending_staff`. Inserting the system refund raises a unique violation; Plan B must handle it by updating the existing row.
- The KB policy text says "trừ phần đã hoàn" (implying multiple partial refunds), yet `paid_out` is live forever, so a second partial refund is impossible. That is an internal spec contradiction.
- Decide: either scope the index by `source`, or drop the "minus already refunded" wording and allow only a single full refund.

M3. No state-consistency CHECKs on `refunds`. Missing:
- `status IN ('approved','paid_out')` requires `approved_amount_vnd`, `decided_by` and `decided_at` to be NOT NULL.
- `paid_out` requires `payout_reference` and `paid_out_at`.
- `rejected` requires `decision_note`.
- Without them, a staff-route bug yields a `paid_out` refund with no reference or approver.
- Also `orders.total_vnd = subtotal_vnd + shipping_fee_vnd` is not enforced.
- Also `refunds.requested_amount_vnd` can exceed the order total at the DB level.

M4. Append-only tables conflict with the anonymisation promise. `tool_audit_log.args` and `status_events.note` are free-form (they can hold PII), and the trigger blocks every UPDATE, so erasure cannot be done (0006 `:20-24`).
- No redaction is enforced in the DB or in code. The spec says "args redacted", but no writer code exists yet, and `mcp` can insert arbitrary JSON.
- Fix options: restrict the trigger to non-PII columns, or add a redaction function that the writer must call, with a test.
- The trigger is row-level only. TRUNCATE is not blocked (only the owner has it, which the report acknowledges). The owner can also `ALTER TABLE ... DISABLE TRIGGER`. This is acceptable for the stated threat model; document it. A `BEFORE TRUNCATE` statement trigger is a cheap addition.

M5. `orders.id` TEXT (A100-style) for Plan B. This is a design choice, not a defect.
- Consequences:
  - Checkout needs a collision-safe code generator with retry. A guessable sequential code is also an enumeration risk; the MCP user filter is the only protection.
  - Every FK (`refunds`, `order_items`, `support_tickets`) is text, and `order_id.strip().upper()` normalisation lives only in MCP.
  - The OpenAPI v0 `Order.id` type was not checked.
- Recommend deciding now, because changing the type later means rewriting FKs.
- Suggestion: keep a uuid PK plus a unique `code` column, or add `CHECK (id ~ '^[A-Z0-9]{3,16}$')`.

M6. `EMBEDDING_DIMS` is configurable, but the models and 0003/0007 hard-code `Vector(1024)`. If someone sets `EMBEDDING_DIMS=768`, the LangGraph store becomes 768 while the KB and product columns stay 1024, and `HttpEmbeddingClient` rejects the vectors at reindex with a misleading error. Either pin the setting to 1024 (validator) or document that it is fixed.

M7. Reindex robustness (`kb/reindex.py:44-56, 129`).
- No advisory lock: two concurrent runs can interleave `_sync_kb_chunks` (the autocommit delete/insert) with embedding updates. `mcp` can see chunk sets that are partially rewritten.
- The timeout is per HTTP call only; there is no overall budget. A hung endpoint with many batches runs for a long time.
- Products that become inactive keep stale rows in `product_embeddings`.
- `kb_documents.version` is not bumped, and nothing deletes chunks for removed docs (the FK cascade handles it).
- Add `pg_try_advisory_lock` and `--max-seconds`.

M8. Seed gating (`shop/seed.py:56-66`, `.env.example`).
- Staff is gated by `ENV=dev` and a strong password: OK. But demo customers (UUID ids fixed in a public frontend bundle) are seeded whenever `SEED_DEMO_DATA=true`, regardless of `ENV`.
- Recommend refusing `SEED_DEMO_DATA=true` when `ENV!=dev`, or at least logging a warning.
- `.env.example` ships `ENV=dev` and `SEED_DEMO_DATA=true`, so a copy-paste to production is dangerous (the compose default is production, but the file overrides it).
- `PasswordHasher()` uses argon2-cffi defaults. Phase 4 must use the same parameters, or login will rehash.

M9. Client-controlled identity is now a hard-coded public UUID, so anyone can read the demo user's orders by sending that UUID to the chat. That is unchanged from before and fixed by phase 4, but the deployment guide should say that the demo seed is not a production-safe identity. `chat-widget.tsx:17-24` silently replaces any stored non-UUID `shopbot_user_id` with the demo UUID: an intentional contract change, and the `setItem` path at `:103` still accepts any string.

## Low

L1. `refresh_tokens.replaced_by ON DELETE SET NULL` (0002 `:50`): cleaning up an old token breaks reuse-detection chains. Prefer a `revoked_at`-based cleanup job, keep `family_id` revocation, and do not delete rows within the family's TTL. `app` has DELETE on this table.

L2. `users`: nothing forces email normalisation. `uq_users_email_lower` is unique on `lower(email)`, so login must query `lower(email)` or the index will not be used. `password_hash` nullable is fine, but phase 4 must reject NULL (noted).

L3. `thread_id` on `refunds`, `support_tickets` and `tool_audit_log` has no FK (intentional, documented).

L4. Downgrade of 0005/0004 does not restore the grants/shape exactly like 0001, but `test_migrations` covers the round trip. The `REVOKE ... ON orders FROM shopbot_app` in the 0004 downgrade revokes something 0001 never granted (harmless).

L5. Product search switched to `immutable_unaccent(name) ILIKE`, which is accent-insensitive; the brand/description OR-branches cannot use any index. The EXPLAIN test runs with `enable_seqscan=off` on about 400 rows and therefore proves only that the index is usable. Fine for a demo; note it.

L6. `lookup_order` JOINs refunds on a live status, so only one row can match (the unique index guarantees it). OK.

## Checks requested, outcome

- `orders_for_agent`: a plain view (owner = migrator, not `security_invoker`), so `mcp` needs no grant on `orders`. The column list is explicit: no `shipping_address`, `note`, `idempotency_key` or `request_hash`. It does expose all users' rows by design, with the `user_id` filter in the MCP query. `apply_grants` revokes all, then re-grants the view. OK.
- `refunds` column-level grant: the list matches `payout_info_enc` exclusion in both 0005 and `roles.py`; a test compares ACLs. OK. INSERT is table-wide (M1).
- SECURITY DEFINER: none used. `immutable_unaccent` is schema-qualified, IMMUTABLE and STRICT. The trigger functions run as invoker. No `search_path` risk.
- `delivered_at` write-once: `BEFORE UPDATE OF delivered_at` allows NULL to value, blocks any change after. Correct. It is not enforced on INSERT (fine) and a delivered order can have NULL (H3).
- Partial unique index semantics: transitions pending to cancelled or rejected free the slot; approved to rejected also frees it (check that the staff route forbids that). M2 covers the cross-source conflict.
- Idempotency: `UNIQUE(user_id, idempotency_key)` allows multiple NULLs, correct. The MCP key is a random uuid per call, so there is no retry idempotency at the key level; it relies on the live-order index. Acceptable for v1.
- CHECK enums vs spec and OpenAPI v0: refund status/source, ticket category/priority/status, notification types and user roles all match `docs/api/openapi-v0.yaml`. Order status matches the spec. Money >= 0: present for price, subtotal, fee and total.
- Payout encryption: Fernet, the key comes from `ApiSettings.payout_encryption_key` (validated), nothing logged, errors carry no data. No call sites yet. The migrate role has no key; fine. `.env.example` has an empty `PAYOUT_ENCRYPTION_KEY=` (pre-existing).
- KB chunking: 1200 chars is about 400 tokens for Vietnamese by assumption; the hard model limit is 2048, so there is margin. `content_hash` includes the model name, so changing the model re-embeds.
- Alembic autogenerate exclusions: `env.py` still imports the new models package; the implementer added a test that `alembic check` detects dropping 7 hand-written indexes. OK.
- Frontend: only `chat-widget.tsx` changed, and the default id is now the seed UUID. Old conversations tied to `demo-user` in checkpoints are unreachable (ownership mismatch) after the switch; acceptable for a demo.
- Windows loop note: the claim that psycopg async needs a Selector loop on Windows is correct and known. The Linux container is unaffected. Consider a `WindowsSelectorEventLoopPolicy` guard in the MCP `__main__` for local dev (Low).
- `docs/deployment-guide.md`: matches the code (role table, revision list, reindex command, ENV gating). Gaps: it does not mention that the demo seed ignores `ENV` for customers (M8), and it does not warn that the `stamp 0001` recipe now destroys orders (it does, in one sentence; make the pre-upgrade guard from H1 the documented path).
- Files over 200 lines: none. Comments contain no plan/finding codes.

## Unresolved questions
1. Is destroying legacy orders/refunds acceptable for any environment other than the local dev stack? If yes, H1 is a guard only. If no, a data migration is needed.
2. Should a customer be able to get more than one refund per order (partial, then rest)? This decides M2 and the KB wording.
3. Keep `orders.id` TEXT, or add uuid PK plus `code` (M5)? Needed before Plan B phase 4.
4. Should the MCP `issue_refund` return the pending status wording now, or wait for MCP v2 (phase 5)? Customer-facing wording is wrong in the meantime (H2).
5. Does the staff decision route allow `approved -> rejected`? The partial index would then free the slot after approval.

**Status:** DONE_WITH_CONCERNS
**Summary:** The schema, grants and triggers are sound (no leak of users, address or payout data to mcp; owner-proof append-only for UPDATE/DELETE; write-once `delivered_at`). Needs fixing before merge or release: unguarded DELETE in 0004/0005 (H1), `issue_refund` returning no pending status while the prompt and policy still imply immediate refund (H2), and missing 7-day window, shipping-excluded cap and `delivered_at` CHECK (H3). Medium items cover mcp's table-wide INSERT on refunds, a unique-index conflict for Plan B's system refund, missing state CHECKs, and seed gating.
