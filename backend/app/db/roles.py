"""Tạo 3 role DB và cấp quyền tối thiểu.

- migrator: sở hữu bảng, có DDL; chỉ bước migrate dùng.
- app: SELECT bảng nghiệp vụ + DML bảng LangGraph, không DDL (API dùng; API chưa ghi bảng nghiệp vụ nào).
- mcp: chỉ đúng quyền MCP server cần (khai báo trong MCP_GRANTS).
"""
import psycopg
from psycopg import sql

from app.db.langgraph_setup import LANGGRAPH_TABLES
from app.settings.migrate import ROLE_APP, ROLE_MCP, ROLE_MIGRATOR, MigrateSettings

# Bảng mà MCP server đọc/ghi: tra đơn, tìm sản phẩm, ghi hoàn tiền (idempotent qua khoá chính).
# INSERT refunds là tạm thời: tool issue_refund hiện ghi thẳng bảng này. Thu hồi khi hoàn tiền chuyển sang
# luồng nhân viên duyệt (API/nhân viên ghi, MCP chỉ còn SELECT).
MCP_GRANTS: dict[str, tuple[str, ...]] = {
    "products": ("SELECT",),
    "orders": ("SELECT",),
    "refunds": ("SELECT", "INSERT"),
}
# Bảng hạ tầng mà app không được đụng
_APP_EXCLUDED_TABLES = ("alembic_version",)


def _ident(name: str) -> sql.Identifier:
    return sql.Identifier(name)


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
    # Bảng/sequence do migrator tạo sau này (kể cả khi chạy `alembic upgrade` trực tiếp, không qua bootstrap)
    # tự cấp tối thiểu cho app: chỉ đọc. Quyền ghi và quyền của mcp luôn cấp rõ ràng trong apply_grants.
    migrator, app = _ident(ROLE_MIGRATOR), _ident(ROLE_APP)
    conn.execute(
        sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT SELECT ON TABLES TO {}").format(migrator, app)
    )
    conn.execute(
        sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {}").format(
            migrator, app
        )
    )


def apply_grants(conn: psycopg.Connection) -> None:
    """Đặt quyền app (SELECT bảng nghiệp vụ, DML bảng LangGraph) và quyền tối thiểu cho mcp.
    Chạy bằng migrator (chủ của các bảng) sau khi mọi bảng (Alembic + LangGraph) đã tồn tại.
    Thu hồi hết rồi cấp lại nên chạy nhiều lần vẫn đúng và cũng thu lại quyền rộng của phiên bản cũ."""
    app = _ident(ROLE_APP)
    conn.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(app))
    conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(app))
    conn.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(app))
    existing = {r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()}
    for table in sorted(LANGGRAPH_TABLES & existing):
        conn.execute(sql.SQL("GRANT INSERT, UPDATE, DELETE ON TABLE {} TO {}").format(_ident(table), app))
    for table in _APP_EXCLUDED_TABLES:
        conn.execute(sql.SQL("REVOKE ALL ON TABLE {} FROM {}").format(_ident(table), app))
    for table, privileges in MCP_GRANTS.items():
        conn.execute(
            sql.SQL("GRANT {} ON TABLE {} TO {}").format(
                sql.SQL(", ").join(sql.SQL(p) for p in privileges), _ident(table), _ident(ROLE_MCP)
            )
        )
