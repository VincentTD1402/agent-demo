"""Migration: đảo ngược được, model khớp migration (kể cả khi bảng LangGraph đã có), chạy song song an toàn."""
import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.util.exc import CommandError

from app.db import bootstrap
from app.db.langgraph_setup import LANGGRAPH_TABLES
from app.db.roles import prepare_cluster
from app.kb.documents import PolicyNumbers, build_kb_documents
from app.settings.migrate import ROLE_APP, ROLE_MCP
from app.shop.seed import seed_demo_data
from app.shop.seed_data import ORDERS, PRODUCTS
from tests.db.conftest import APP_PASSWORD, MCP_PASSWORD, MIGRATOR_PASSWORD, role_url

BACKEND_DIR = Path(__file__).resolve().parents[2]
SHOP_TABLES = {
    "users", "refresh_tokens", "products", "product_embeddings", "orders", "order_items", "refunds", "conversations",
    "tool_audit_log", "support_tickets", "notifications", "status_events", "kb_documents", "kb_chunks",
}
LEGACY_TABLES = {"products", "orders", "refunds"}


def _tables(url: str) -> set[str]:
    with psycopg.connect(url) as conn:
        rows = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()
    return {r[0] for r in rows}


def _scalar(url: str, query: str):
    with psycopg.connect(url) as conn:
        return conn.execute(query).fetchone()[0]


def test_upgrade_downgrade_upgrade(fresh_db):
    with psycopg.connect(fresh_db.bootstrap_database_url, autocommit=True) as su:
        prepare_cluster(su, fresh_db)
    cfg = bootstrap.alembic_config(fresh_db.migrator_database_url)
    url = fresh_db.bootstrap_database_url

    command.upgrade(cfg, "head")
    assert SHOP_TABLES <= _tables(url)
    assert _scalar(url, "SELECT immutable_unaccent('Điện thoại')") == "Dien thoai"

    command.downgrade(cfg, "base")
    assert not SHOP_TABLES & _tables(url)
    # extension được giữ lại có chủ đích (bảng LangGraph phụ thuộc vector): downgrade extension là no-op
    assert _scalar(url, "SELECT count(*) FROM pg_extension WHERE extname IN ('vector', 'pg_trgm', 'unaccent')") == 3

    command.upgrade(cfg, "head")
    assert SHOP_TABLES <= _tables(url)


def test_each_revision_downgrades_one_step_at_a_time(fresh_db):
    with psycopg.connect(fresh_db.bootstrap_database_url, autocommit=True) as su:
        prepare_cluster(su, fresh_db)
    cfg = bootstrap.alembic_config(fresh_db.migrator_database_url)
    command.upgrade(cfg, "head")
    for target in ("0006", "0005", "0004", "0003", "0002", "0001", "base"):
        command.downgrade(cfg, target)
    command.upgrade(cfg, "head")
    command.check(cfg)


def test_upgrade_from_seeded_baseline_and_downgrade_back(fresh_db):
    """Revision 0001 đã có dữ liệu mẫu dạng cũ (orders.items, user_id text, refunds theo order_id): upgrade lên head
    thành công (đơn/hoàn tiền cũ bị bỏ vì chỉ là dữ liệu mẫu, và chỉ khi có cờ allow_destroy_legacy_orders), downgrade về 0001 rồi base cũng thành công."""
    with psycopg.connect(fresh_db.bootstrap_database_url, autocommit=True) as su:
        prepare_cluster(su, fresh_db)
    cfg = bootstrap.alembic_config(fresh_db.migrator_database_url, allow_destroy_legacy_orders=True)
    url = fresh_db.bootstrap_database_url
    command.upgrade(cfg, "0001")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("INSERT INTO products (slug, name, category, brand, price_vnd) VALUES ('p', 'P', 'c', 'b', 1)")
        conn.execute(
            "INSERT INTO orders (id, user_id, status, total_vnd, items) VALUES ('A1', 'demo-user', 'delivered', 5, '[]')"
        )
        conn.execute("INSERT INTO refunds (order_id, amount_vnd, reason) VALUES ('A1', 5, 'x')")

    command.upgrade(cfg, "head")
    assert _scalar(url, "SELECT count(*) FROM orders") == 0
    assert _scalar(url, "SELECT count(*) FROM refunds") == 0
    assert _scalar(url, "SELECT count(*) FROM products") == 1  # catalog được giữ

    command.downgrade(cfg, "0001")
    assert not (SHOP_TABLES - LEGACY_TABLES) & _tables(url)
    legacy_items = (
        "SELECT count(*) FROM information_schema.columns WHERE table_name = 'orders' AND column_name = 'items'"
    )
    assert _scalar(url, legacy_items) == 1
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


def test_tables_recreated_by_plain_upgrade_keep_role_grants(bootstrapped_db):
    """`alembic upgrade` chạy trực tiếp (không bootstrap lại) vẫn cấp đủ quyền: grants nằm trong từng revision."""
    cfg = bootstrap.alembic_config(bootstrapped_db.migrator_database_url, allow_destroy_legacy_orders=True)
    command.downgrade(cfg, "base")
    assert not SHOP_TABLES & _tables(bootstrapped_db.bootstrap_database_url)
    command.upgrade(cfg, "head")
    with psycopg.connect(role_url(bootstrapped_db, ROLE_APP), autocommit=True) as conn:
        for table in sorted(SHOP_TABLES):
            conn.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 - tên bảng cố định
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM products")
    with psycopg.connect(role_url(bootstrapped_db, ROLE_MCP), autocommit=True) as conn:
        conn.execute("SELECT count(*) FROM products")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT count(*) FROM users")


def test_seed_is_all_or_nothing(bootstrapped_db, monkeypatch):
    """Seed lỗi giữa chừng thì rollback hết, lần chạy sau vẫn nạp đủ."""
    url = bootstrapped_db.migrator_database_url
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("TRUNCATE users, products, kb_documents RESTART IDENTITY CASCADE")
    broken = [*PRODUCTS[:2], {**PRODUCTS[2], "price_vnd": -1}]  # vi phạm CHECK price_vnd >= 0
    monkeypatch.setattr("app.shop.seed.PRODUCTS", broken)
    with psycopg.connect(url, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            seed_demo_data(conn, bootstrapped_db)
    assert _scalar(url, "SELECT count(*) FROM products") == 0
    monkeypatch.undo()
    with psycopg.connect(url, autocommit=True) as conn:
        seed_demo_data(conn, bootstrapped_db)
    assert _scalar(url, "SELECT count(*) FROM products") == len(PRODUCTS)


def test_alembic_check_clean_after_langgraph_setup(bootstrapped_db):
    url = bootstrapped_db.bootstrap_database_url
    assert LANGGRAPH_TABLES <= _tables(url), "bootstrap phải đã tạo bảng LangGraph"
    cfg = bootstrap.alembic_config(bootstrapped_db.migrator_database_url)
    command.check(cfg)  # ném CommandError nếu có thay đổi chưa có migration (kể cả đề xuất DROP bảng LangGraph)


def test_alembic_check_detects_model_drift(bootstrapped_db):
    with psycopg.connect(bootstrapped_db.migrator_database_url, autocommit=True) as conn:
        conn.execute("ALTER TABLE products ADD COLUMN drift_probe integer")
    with pytest.raises(CommandError):
        command.check(bootstrap.alembic_config(bootstrapped_db.migrator_database_url))


@pytest.mark.parametrize(
    "index",
    [
        "ix_products_name_trgm", "ix_product_embeddings_embedding_hnsw", "ix_kb_chunks_embedding_hnsw",
        "ix_kb_chunks_tsv", "uq_refunds_live_customer_request_per_order", "uq_refunds_live_system_cancel_per_order",
        "uq_users_email_lower", "ix_orders_expires_at_pending",
    ],
)
def test_alembic_check_notices_a_missing_hand_written_index(bootstrapped_db, index):
    """Index biểu thức/một phần/HNSW do tay viết trong revision: model phải khai báo khớp để `alembic check` bắt lệch."""
    with psycopg.connect(bootstrapped_db.migrator_database_url, autocommit=True) as conn:
        conn.execute(f"DROP INDEX {index}")  # noqa: S608 - tên index cố định
    with pytest.raises(CommandError):
        command.check(bootstrap.alembic_config(bootstrapped_db.migrator_database_url))


def test_bootstrap_is_idempotent_and_seeds_once(bootstrapped_db):
    bootstrap.run(bootstrapped_db)
    url = bootstrapped_db.bootstrap_database_url
    assert _scalar(url, "SELECT count(*) FROM products") == len(PRODUCTS)
    assert _scalar(url, "SELECT count(*) FROM orders") == len(ORDERS)
    policy = PolicyNumbers(
        bootstrapped_db.refund_window_days, bootstrapped_db.shipping_fee_vnd, bootstrapped_db.free_shipping_from_vnd
    )
    assert _scalar(url, "SELECT count(*) FROM kb_documents") == len(build_kb_documents(policy))
    assert _scalar(url, "SELECT count(*) FROM alembic_version") == 1


def test_two_concurrent_bootstrap_processes(fresh_db):
    env = {
        **os.environ,
        "BOOTSTRAP_DATABASE_URL": fresh_db.bootstrap_database_url,
        "MIGRATOR_DB_PASSWORD": MIGRATOR_PASSWORD,
        "APP_DB_PASSWORD": APP_PASSWORD,
        "MCP_DB_PASSWORD": MCP_PASSWORD,
        "SEED_DEMO_DATA": "true",
        "PYTHONIOENCODING": "utf-8",
    }
    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "app.db.bootstrap"], cwd=BACKEND_DIR, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        )
        for _ in range(2)
    ]
    outputs = [p.communicate(timeout=180)[0] for p in procs]
    for proc, out in zip(procs, outputs):
        assert proc.returncode == 0, out
    url = fresh_db.bootstrap_database_url
    assert SHOP_TABLES | LANGGRAPH_TABLES <= _tables(url)
    assert _scalar(url, "SELECT count(*) FROM alembic_version") == 1
    assert _scalar(url, "SELECT count(*) FROM products") == len(PRODUCTS)
