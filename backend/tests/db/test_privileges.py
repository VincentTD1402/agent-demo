"""Quyền theo role: mcp không thấy dữ liệu nhạy cảm, bảng audit/sự kiện chỉ-thêm, grants của revision == grants của bootstrap."""
import psycopg
import pytest
from alembic import command
from psycopg.errors import ForeignKeyViolation, InsufficientPrivilege, RestrictViolation, UndefinedColumn

from app.db import bootstrap
from app.db.langgraph_setup import LANGGRAPH_TABLES
from app.db.roles import prepare_cluster
from app.settings.migrate import ROLE_APP, ROLE_MCP, ROLE_MIGRATOR
from app.shop.seed_data import DEMO_CUSTOMER_ID, ORDER_OTHER_CUSTOMER_ID, ORDER_REFUND_ELIGIBLE_ID
from tests.db.conftest import expect_error

INSERT_EVENT = "INSERT INTO status_events (entity_type, entity_id, to_status) VALUES ('order', 'A100', 'delivered')"
INSERT_AUDIT = (
    "INSERT INTO tool_audit_log (user_id, tool_name, status) VALUES (%s, 'lookup_order', 'ok')"
)
INSERT_REFUND = (
    "INSERT INTO refunds (order_id, user_id, source, requested_amount_vnd, reason, idempotency_key)"
    " VALUES (%s, %s, 'customer_request', 1000, 'lỗi', 'k1') RETURNING id"
)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM users",
        "SELECT email FROM users",
        "SELECT * FROM refresh_tokens",
        "SELECT * FROM conversations",
        "SELECT * FROM orders",
        "SELECT shipping_address FROM orders",
        "SELECT payout_info_enc FROM refunds",
        "SELECT * FROM refunds",
        "SELECT count(*) FROM refunds WHERE payout_info_enc IS NOT NULL",
        "SELECT * FROM notifications",
        "SELECT * FROM support_tickets",
        "SELECT * FROM status_events",
        "SELECT * FROM tool_audit_log",
    ],
)
def test_mcp_cannot_read_sensitive_data(connect_as, query):
    expect_error(connect_as(ROLE_MCP), InsufficientPrivilege, query)


def test_mcp_reads_orders_only_through_view_without_address(connect_as):
    conn = connect_as(ROLE_MCP)
    row = conn.execute("SELECT id, status, total_vnd FROM orders_for_agent WHERE id = %s", (ORDER_REFUND_ELIGIBLE_ID,))
    assert row.fetchone()[1] == "delivered"
    columns = {d.name for d in conn.execute("SELECT * FROM orders_for_agent").description}
    assert not columns & {"shipping_address", "note", "idempotency_key", "request_hash"}
    expect_error(conn, UndefinedColumn, "SELECT shipping_address FROM orders_for_agent")


def test_mcp_reads_catalog_kb_items_and_refund_columns_except_payout(connect_as):
    conn = connect_as(ROLE_MCP)
    for query in (
        "SELECT count(*) FROM products", "SELECT count(*) FROM product_embeddings", "SELECT count(*) FROM order_items",
        "SELECT count(*) FROM kb_documents", "SELECT count(*) FROM kb_chunks",
        "SELECT id, order_id, status, requested_amount_vnd, decision_note FROM refunds",
    ):
        conn.execute(query)


def test_mcp_can_insert_where_allowed_and_nothing_else(connect_as):
    conn = connect_as(ROLE_MCP)
    refund_id = conn.execute(INSERT_REFUND, (ORDER_REFUND_ELIGIBLE_ID, DEMO_CUSTOMER_ID)).fetchone()[0]
    assert refund_id is not None  # RETURNING id cần SELECT trên cột id (được cấp)
    conn.execute(INSERT_AUDIT, (DEMO_CUSTOMER_ID,))
    conn.execute("INSERT INTO support_tickets (user_id, category, summary) VALUES (%s, 'other', 'x')", (DEMO_CUSTOMER_ID,))
    for statement in (
        # sự kiện trạng thái và thông báo do API ghi: mcp không có INSERT
        INSERT_EVENT,
        f"INSERT INTO notifications (user_id, type) VALUES ('{DEMO_CUSTOMER_ID}', 'ticket_updated')",
        "UPDATE refunds SET status = 'approved'",
        "UPDATE products SET stock = 0",
        "DELETE FROM refunds",
        "INSERT INTO orders (id, user_id, status, subtotal_vnd, total_vnd, shipping_address)"
        f" VALUES ('X', '{DEMO_CUSTOMER_ID}', 'processing', 1, 1, '{{}}')",
        "INSERT INTO kb_documents (slug, lang, title, category, body) VALUES ('s', 'vi', 't', 'c', 'b')",
        "INSERT INTO users (email, full_name) VALUES ('x@y.z', 'x')",
    ):
        expect_error(conn, InsufficientPrivilege, statement)


@pytest.mark.parametrize(
    "statement",
    [
        # refunds: không tự đặt trạng thái, số tiền duyệt, người duyệt, thông tin chi trả
        "INSERT INTO refunds (order_id, user_id, source, requested_amount_vnd, reason, idempotency_key, status)"
        f" VALUES ('A100', '{DEMO_CUSTOMER_ID}', 'customer_request', 1, 'x', 'p1', 'paid_out')",
        "INSERT INTO refunds (order_id, user_id, source, requested_amount_vnd, reason, idempotency_key, approved_amount_vnd)"
        f" VALUES ('A100', '{DEMO_CUSTOMER_ID}', 'customer_request', 1, 'x', 'p2', 1)",
        "INSERT INTO refunds (order_id, user_id, source, requested_amount_vnd, reason, idempotency_key, decided_by)"
        f" VALUES ('A100', '{DEMO_CUSTOMER_ID}', 'customer_request', 1, 'x', 'p3', '{DEMO_CUSTOMER_ID}')",
        "INSERT INTO refunds (order_id, user_id, source, requested_amount_vnd, reason, idempotency_key, payout_info_enc)"
        f" VALUES ('A100', '{DEMO_CUSTOMER_ID}', 'customer_request', 1, 'x', 'p4', 'x')",
        # status_events/tool_audit_log/support_tickets/notifications: không giả actor, lùi mốc thời gian, tự xử lý phiếu
        "INSERT INTO status_events (entity_type, entity_id, to_status, actor_id)"
        f" VALUES ('refund', 'r', 'approved', '{DEMO_CUSTOMER_ID}')",
        "INSERT INTO status_events (entity_type, entity_id, to_status, at) VALUES ('refund', 'r', 'approved', now())",
        f"INSERT INTO tool_audit_log (user_id, tool_name, status, at) VALUES ('{DEMO_CUSTOMER_ID}', 't', 'ok', now())",
        f"INSERT INTO support_tickets (user_id, category, summary, status) VALUES ('{DEMO_CUSTOMER_ID}', 'other', 'x', 'closed')",
        f"INSERT INTO support_tickets (user_id, category, summary, assigned_to) VALUES ('{DEMO_CUSTOMER_ID}', 'other', 'x', '{DEMO_CUSTOMER_ID}')",
        f"INSERT INTO notifications (user_id, type, read_at) VALUES ('{DEMO_CUSTOMER_ID}', 'ticket_updated', now())",
    ],
)
def test_mcp_insert_is_limited_to_content_columns(connect_as, statement):
    expect_error(connect_as(ROLE_MCP), InsufficientPrivilege, statement)


def test_mcp_refund_insert_always_lands_as_pending_and_for_the_order_owner(connect_as):
    conn = connect_as(ROLE_MCP)
    row = conn.execute(INSERT_REFUND.replace("RETURNING id", "RETURNING status, approved_amount_vnd, decided_by"),
                       (ORDER_REFUND_ELIGIBLE_ID, DEMO_CUSTOMER_ID)).fetchone()
    assert row == ("pending_staff", None, None)
    # đơn B200 thuộc khách khác: khoá ngoại ghép (order_id, user_id) chặn hoàn tiền cho đơn không phải của mình
    expect_error(conn, ForeignKeyViolation, INSERT_REFUND.replace("'k1'", "'k9'"), (ORDER_OTHER_CUSTOMER_ID, DEMO_CUSTOMER_ID))


def _append_row(conn: psycopg.Connection, table: str) -> None:
    if table == "status_events":
        conn.execute(INSERT_EVENT)
    else:
        conn.execute(INSERT_AUDIT, (DEMO_CUSTOMER_ID,))


@pytest.mark.parametrize("table", ["status_events", "tool_audit_log"])
def test_app_cannot_update_or_delete_append_only_tables(connect_as, table):
    conn = connect_as(ROLE_APP)
    _append_row(conn, table)
    conn.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 - tên bảng cố định
    expect_error(conn, InsufficientPrivilege, f"UPDATE {table} SET id = id")  # noqa: S608
    expect_error(conn, InsufficientPrivilege, f"DELETE FROM {table}")  # noqa: S608
    expect_error(conn, InsufficientPrivilege, f"TRUNCATE {table}")


@pytest.mark.parametrize("table", ["status_events", "tool_audit_log"])
def test_trigger_blocks_update_and_delete_even_for_table_owner(connect_as, table):
    conn = connect_as(ROLE_MIGRATOR)
    _append_row(conn, table)
    expect_error(conn, RestrictViolation, f"UPDATE {table} SET id = id")  # noqa: S608
    expect_error(conn, RestrictViolation, f"DELETE FROM {table}")  # noqa: S608


def test_app_write_surface_matches_business_rules(connect_as):
    conn = connect_as(ROLE_APP)
    conn.execute("UPDATE orders SET carrier = 'GHN' WHERE id = 'A101'")
    conn.execute("UPDATE products SET stock = stock WHERE slug = 'iphone-16-128gb'")
    conn.execute("INSERT INTO notifications (user_id, type) VALUES (%s, 'refund_paid_out')", (DEMO_CUSTOMER_ID,))
    for statement in (
        "DELETE FROM orders", "DELETE FROM refunds", "DELETE FROM users", "DELETE FROM products",
        "DELETE FROM order_items",
        "UPDATE kb_documents SET title = 'x'", "INSERT INTO kb_chunks (document_id, idx, content) VALUES (1, 99, 'x')",
        "UPDATE product_embeddings SET model = 'x'", "SELECT * FROM alembic_version",
    ):
        expect_error(conn, InsufficientPrivilege, statement)


def test_app_can_write_refund_payout_column_but_mcp_cannot_see_it(connect_as):
    conn = connect_as(ROLE_APP)
    conn.execute(INSERT_REFUND, (ORDER_REFUND_ELIGIBLE_ID, DEMO_CUSTOMER_ID))
    conn.execute("UPDATE refunds SET payout_info_enc = %s", (b"ciphertext",))
    assert conn.execute("SELECT payout_info_enc FROM refunds").fetchone()[0] == b"ciphertext"


def _acl_snapshot(url: str) -> set[tuple[str, str, str, str]]:
    """(bảng/sequence, cột hoặc '', role, quyền) của app/mcp, bỏ bảng LangGraph và alembic_version."""
    query = """
        SELECT c.relname, '', r.rolname, a.privilege_type
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles r ON r.oid = a.grantee
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v', 'S') AND r.rolname IN (%(app)s, %(mcp)s)
        UNION ALL
        SELECT c.relname, att.attname, r.rolname, a.privilege_type
        FROM pg_attribute att JOIN pg_class c ON c.oid = att.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN LATERAL aclexplode(att.attacl) a JOIN pg_roles r ON r.oid = a.grantee
        WHERE n.nspname = 'public' AND r.rolname IN (%(app)s, %(mcp)s)
    """
    with psycopg.connect(url) as conn:
        rows = conn.execute(query, {"app": ROLE_APP, "mcp": ROLE_MCP}).fetchall()
    ignored = LANGGRAPH_TABLES | {"alembic_version"}
    return {tuple(r) for r in rows if r[0] not in ignored and not r[0].startswith(("store", "checkpoint"))}


def test_grants_after_upgrade_only_equal_grants_after_bootstrap(fresh_db, shared_bootstrapped_db):
    """Revision cấp quyền cho bảng của mình; apply_grants (nguồn cấp lại duy nhất) phải cho đúng cùng kết quả."""
    with psycopg.connect(fresh_db.bootstrap_database_url, autocommit=True) as su:
        prepare_cluster(su, fresh_db)
    command.upgrade(bootstrap.alembic_config(fresh_db.migrator_database_url), "head")
    upgrade_only = _acl_snapshot(fresh_db.bootstrap_database_url)
    bootstrapped = _acl_snapshot(shared_bootstrapped_db.bootstrap_database_url)

    assert upgrade_only, "snapshot rỗng: truy vấn ACL sai"
    assert ("orders_for_agent", "", ROLE_MCP, "SELECT") in bootstrapped
    assert ("refunds", "payout_info_enc", ROLE_MCP, "SELECT") not in bootstrapped
    assert upgrade_only == bootstrapped, (
        f"chỉ có ở upgrade: {sorted(upgrade_only - bootstrapped)}; chỉ có ở bootstrap: {sorted(bootstrapped - upgrade_only)}"
    )
