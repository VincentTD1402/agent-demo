"""Tạo 3 role DB và cấp quyền tối thiểu.

- migrator: sở hữu bảng, có DDL; chỉ bước migrate dùng.
- app: SELECT mọi bảng nghiệp vụ + DML tối thiểu (APP_WRITE) + DML bảng LangGraph, không DDL.
- mcp: đúng những gì MCP server cần (MCP_*), tuyệt đối không thấy users/refresh_tokens/conversations,
  bảng orders (chỉ view orders_for_agent) và cột refunds.payout_info_enc.

Mỗi revision Alembic tự cấp quyền cho bảng nó tạo; `apply_grants` là nguồn duy nhất để cấp lại toàn bộ
(thu hồi hết rồi cấp lại). Hai nơi phải cho cùng kết quả: tests/db/test_privileges.py so sánh ACL của hai đường.
"""
import psycopg
from psycopg import sql

from app.db.langgraph_setup import LANGGRAPH_TABLES
from app.settings.migrate import ROLE_APP, ROLE_MCP, ROLE_MIGRATOR, MigrateSettings

# Quyền ghi của app trên bảng nghiệp vụ. Không DELETE trên đơn/hoàn tiền/người dùng (xoá dữ liệu cá nhân là
# ẩn danh hoá); bảng sự kiện và audit chỉ INSERT (kèm trigger chặn UPDATE/DELETE).
APP_WRITE: dict[str, tuple[str, ...]] = {
    "users": ("INSERT", "UPDATE"),
    "refresh_tokens": ("INSERT", "UPDATE", "DELETE"),
    "products": ("UPDATE",),
    "orders": ("INSERT", "UPDATE"),
    "order_items": ("INSERT", "UPDATE"),
    "refunds": ("INSERT", "UPDATE"),
    "conversations": ("INSERT", "UPDATE", "DELETE"),
    "support_tickets": ("INSERT", "UPDATE"),
    "notifications": ("INSERT", "UPDATE"),
    "status_events": ("INSERT",),
    "tool_audit_log": ("INSERT",),
}
# mcp chỉ SELECT: orders_for_agent là view không có địa chỉ giao
MCP_SELECT_TABLES = (
    "products", "product_embeddings", "orders_for_agent", "order_items", "kb_documents", "kb_chunks",
)
# refunds: mọi cột trừ payout_info_enc (khớp revision tạo bảng)
MCP_REFUND_COLUMNS = (
    "id", "order_id", "user_id", "source", "requested_amount_vnd", "approved_amount_vnd", "reason", "status",
    "idempotency_key", "thread_id", "decided_by", "decision_note", "payout_reference", "created_at", "decided_at",
    "paid_out_at",
)
# mcp chỉ INSERT theo cột (đúng những cột công cụ cần đặt): refunds.status luôn lấy DEFAULT 'pending_staff' nên mcp
# không tạo được yêu cầu 'paid_out'; không đặt approved_amount/decided_by/payout_*. Sự kiện trạng thái và thông báo do API ghi, mcp không có INSERT trên status_events/notifications.
MCP_INSERT_COLUMNS: dict[str, tuple[str, ...]] = {
    "refunds": ("order_id", "user_id", "source", "requested_amount_vnd", "reason", "idempotency_key", "thread_id"),
    "tool_audit_log": ("thread_id", "user_id", "tool_name", "args", "status", "latency_ms"),
    "support_tickets": ("user_id", "thread_id", "order_id", "category", "summary", "priority"),
}
MCP_SEQUENCES = ("tool_audit_log_id_seq",)
# Bảng hạ tầng mà app không được đụng
_APP_EXCLUDED_TABLES = ("alembic_version",)


def _ident(name: str) -> sql.Identifier:
    return sql.Identifier(name)


def _idents(names) -> sql.Composed:
    return sql.SQL(", ").join(_ident(n) for n in names)


def _upsert_role(conn: psycopg.Connection, role: str, password: str) -> None:
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
    verb = "ALTER" if exists else "CREATE"
    # CREATE/ALTER ROLE không nhận bind parameter cho mật khẩu nên dùng literal đã escape
    conn.execute(
        sql.SQL("{} ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}").format(
            sql.SQL(verb), _ident(role), sql.Literal(password)
        )
    )


def prepare_cluster(conn: psycopg.Connection, s: MigrateSettings) -> None:
    """Bước cần superuser: extension `vector` (không phải trusted), tạo role, quyền database/schema.
    Idempotent; gọi khi đang giữ khoá bootstrap."""
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    _upsert_role(conn, ROLE_MIGRATOR, s.migrator_db_password.get_secret_value())
    _upsert_role(conn, ROLE_APP, s.app_db_password.get_secret_value())
    _upsert_role(conn, ROLE_MCP, s.mcp_db_password.get_secret_value())
    db = _ident(s.database_name)
    for role in (ROLE_MIGRATOR, ROLE_APP, ROLE_MCP):
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(db, _ident(role)))
    # CREATE trên database để migrator tạo được extension "trusted" (pg_trgm, unaccent)
    conn.execute(sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(db, _ident(ROLE_MIGRATOR)))
    # Mặc định PUBLIC được TEMPORARY: thu lại để app/mcp không tạo được cả bảng tạm
    conn.execute(sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC").format(db))
    # Không role nào ngoài migrator được tạo object trong schema public (Postgres < 15 mặc định cho phép)
    conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    conn.execute(sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(_ident(ROLE_MIGRATOR)))
    for role in (ROLE_APP, ROLE_MCP):
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(_ident(role)))
    # Bảng/sequence do migrator tạo sau này tự cấp tối thiểu cho app: chỉ đọc. Quyền ghi và quyền của mcp
    # luôn cấp rõ ràng (trong từng revision và trong apply_grants).
    migrator, app = _ident(ROLE_MIGRATOR), _ident(ROLE_APP)
    conn.execute(
        sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT SELECT ON TABLES TO {}").format(migrator, app)
    )
    conn.execute(
        sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {}").format(
            migrator, app
        )
    )


def _grant(conn: psycopg.Connection, privileges, tables, role: str) -> None:
    conn.execute(
        sql.SQL("GRANT {} ON TABLE {} TO {}").format(
            sql.SQL(", ").join(sql.SQL(p) for p in privileges), _idents(tables), _ident(role)
        )
    )


def apply_grants(conn: psycopg.Connection) -> None:
    """Đặt lại toàn bộ quyền của app và mcp. Chạy bằng migrator (chủ bảng) sau khi mọi bảng (Alembic + LangGraph)
    đã tồn tại. Thu hồi hết rồi cấp lại nên chạy nhiều lần vẫn đúng và cũng thu lại quyền rộng của bản cũ."""
    app, mcp = _ident(ROLE_APP), _ident(ROLE_MCP)
    for role in (app, mcp):
        conn.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(role))
        conn.execute(sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {}").format(role))

    conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(app))
    conn.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(app))
    for table, privileges in APP_WRITE.items():
        _grant(conn, privileges, [table], ROLE_APP)
    existing = {r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()}
    for table in sorted(LANGGRAPH_TABLES & existing):
        _grant(conn, ("INSERT", "UPDATE", "DELETE"), [table], ROLE_APP)
    for table in _APP_EXCLUDED_TABLES:
        conn.execute(sql.SQL("REVOKE ALL ON TABLE {} FROM {}").format(_ident(table), app))

    _grant(conn, ("SELECT",), MCP_SELECT_TABLES, ROLE_MCP)
    conn.execute(
        sql.SQL("GRANT SELECT ({}) ON TABLE refunds TO {}").format(_idents(MCP_REFUND_COLUMNS), mcp)
    )
    for table, columns in MCP_INSERT_COLUMNS.items():
        conn.execute(sql.SQL("GRANT INSERT ({}) ON TABLE {} TO {}").format(_idents(columns), _ident(table), mcp))
    conn.execute(sql.SQL("GRANT USAGE ON SEQUENCE {} TO {}").format(_idents(MCP_SEQUENCES), mcp))
