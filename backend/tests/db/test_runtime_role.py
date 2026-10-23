"""API chạy được bằng role `app` (không DDL); MCP chỉ có quyền tối thiểu; ngân sách kết nối nằm trong giới hạn."""
import uuid

import psycopg
import pytest
from cryptography.fernet import Fernet
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.agent.graph import build_graph
from app.db.event_loop import run_async
from app.db.langgraph_setup import LANGGRAPH_TABLES
from app.settings.api import ApiSettings
from app.settings.mcp import McpSettings
from app.settings.migrate import ROLE_APP, ROLE_MCP
from tests.db.conftest import role_url

EMBEDDING_DIMS = 1024


class ConstantEmbeddings(Embeddings):
    """Embedding cố định để không cần server AI; test này chỉ kiểm tra quyền ghi/đọc của role app."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.01] * EMBEDDING_DIMS for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.01] * EMBEDDING_DIMS


class FakeLLM(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_app_role_cannot_run_ddl(bootstrapped_db):
    with psycopg.connect(role_url(bootstrapped_db, ROLE_APP), autocommit=True) as conn:
        for statement in (
            "CREATE TABLE rogue (id int)",
            "CREATE TEMP TABLE rogue_temp (id int)",
            "DROP TABLE products",
            "ALTER TABLE products ADD COLUMN rogue int",
            "TRUNCATE TABLE alembic_version",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)
        assert conn.execute("SELECT count(*) FROM products").fetchone()[0] > 0


def test_app_role_is_read_only_on_shop_tables_and_writes_langgraph_tables(bootstrapped_db):
    with psycopg.connect(role_url(bootstrapped_db, ROLE_APP), autocommit=True) as conn:
        for table in ("products", "orders", "refunds"):
            conn.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 - tên bảng cố định
        for statement in (
            "UPDATE products SET stock = stock",
            "DELETE FROM orders",
            "INSERT INTO refunds (order_id, amount_vnd, reason) VALUES ('x', 1, 'x')",
            "SELECT count(*) FROM alembic_version",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)
        for table in sorted(LANGGRAPH_TABLES):
            privileges = {
                p: conn.execute("SELECT has_table_privilege(current_user, %s, %s)", (table, p)).fetchone()[0]
                for p in ("SELECT", "INSERT", "UPDATE", "DELETE")
            }
            assert all(privileges.values()), f"{table}: {privileges}"


def test_mcp_role_has_minimum_privileges(bootstrapped_db):
    with psycopg.connect(role_url(bootstrapped_db, ROLE_MCP), autocommit=True) as conn:
        assert conn.execute("SELECT count(*) FROM orders").fetchone()[0] > 0
        for statement in (
            "UPDATE products SET stock = 0",
            "DELETE FROM orders",
            "SELECT * FROM checkpoints",
            "CREATE TABLE rogue (id int)",
            "CREATE TEMP TABLE rogue_temp (id int)",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)
        # INSERT refunds được giữ có chủ đích cho tool issue_refund (xem MCP_GRANTS): tới được kiểm tra khoá ngoại
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute("INSERT INTO refunds (order_id, amount_vnd, reason) VALUES ('no-such-order', 1, 'x')")


async def _fake_chat_as_app_role(app_dsn: str) -> None:
    pool = AsyncConnectionPool(app_dsn, min_size=1, max_size=3, open=False, kwargs={"row_factory": dict_row, "autocommit": True})
    await pool.open()
    try:
        # Không gọi setup(): bảng đã do bootstrap tạo, role app không có DDL
        saver = AsyncPostgresSaver(pool)
        index = {"dims": EMBEDDING_DIMS, "embed": ConstantEmbeddings(), "fields": ["text"]}
        store = AsyncPostgresStore(pool, index=index)
        graph = build_graph(FakeLLM(messages=iter([AIMessage("Xin chào!")])), [], saver, store)
        thread = uuid.uuid4().hex
        cfg = {"configurable": {"thread_id": thread, "user_id": "u-1"}, "recursion_limit": 12}
        result = await graph.ainvoke({"messages": [("user", "chào shop")]}, cfg)
        assert result["messages"][-1].content == "Xin chào!"
        assert (await graph.aget_state(cfg)).values["messages"], "checkpoint phải đọc lại được"
        item = await store.aget(("u-1", "profile"), "last_request")
        assert item is not None and "chào shop" in item.value["text"]
    finally:
        await pool.close()


def test_chat_graph_runs_under_app_role(bootstrapped_db):
    run_async(_fake_chat_as_app_role(role_url(bootstrapped_db, ROLE_APP)))


def test_connection_budget_fits_postgres_limit(admin_url):
    api = ApiSettings(
        _env_file=None, llm_base_url="http://x/v1", llm_model="m", embedding_model="e",
        database_url="postgresql://u:p@h/d",
        payout_encryption_key=Fernet.generate_key().decode(),
    )
    mcp = McpSettings(_env_file=None, database_url="postgresql://u:p@h/d")
    migrate_connections = 2  # kết nối khoá + kết nối DDL của bước migrate
    with psycopg.connect(admin_url) as conn:
        max_conn = int(conn.execute("SHOW max_connections").fetchone()[0])
        reserved = int(conn.execute("SHOW superuser_reserved_connections").fetchone()[0])
    total = api.max_connections + mcp.max_connections + migrate_connections
    assert total < max_conn - reserved, f"{total} kết nối dự kiến >= giới hạn khả dụng {max_conn - reserved}"
