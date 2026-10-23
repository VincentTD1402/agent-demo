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
from app.settings.migrate import ROLE_APP, ROLE_MCP
from app.shop.seed import seed_demo_data
from app.shop.seed_data import ORDERS, PRODUCTS
from tests.db.conftest import APP_PASSWORD, MCP_PASSWORD, MIGRATOR_PASSWORD, role_url

BACKEND_DIR = Path(__file__).resolve().parents[2]
SHOP_TABLES = {"products", "orders", "refunds"}


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
    # extension được giữ lại có chủ đích (bảng LangGraph phụ thuộc vector)
    assert _scalar(url, "SELECT count(*) FROM pg_extension WHERE extname IN ('vector', 'pg_trgm', 'unaccent')") == 3

    command.upgrade(cfg, "head")
    assert SHOP_TABLES <= _tables(url)


def test_tables_recreated_by_plain_upgrade_stay_readable_by_app(bootstrapped_db):
    """`alembic upgrade` chạy trực tiếp (không bootstrap lại) vẫn để app đọc được bảng mới nhờ default privileges."""
    cfg = bootstrap.alembic_config(bootstrapped_db.migrator_database_url)
    command.downgrade(cfg, "base")
    assert not SHOP_TABLES & _tables(bootstrapped_db.bootstrap_database_url)
    command.upgrade(cfg, "head")
    with psycopg.connect(role_url(bootstrapped_db, ROLE_APP), autocommit=True) as conn:
        for table in sorted(SHOP_TABLES):
            conn.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 - tên bảng cố định
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM products")
    # mcp chỉ có quyền khai báo rõ trong MCP_GRANTS (cấp bởi bootstrap), không nhận quyền tự động
    with psycopg.connect(role_url(bootstrapped_db, ROLE_MCP), autocommit=True) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT count(*) FROM products")


def test_seed_is_all_or_nothing(bootstrapped_db, monkeypatch):
    """Seed lỗi giữa chừng thì rollback hết, lần chạy sau vẫn nạp đủ."""
    url = bootstrapped_db.migrator_database_url
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("TRUNCATE refunds, orders, products RESTART IDENTITY")
    broken = [*PRODUCTS[:2], {**PRODUCTS[2], "price_vnd": -1}]  # vi phạm CHECK price_vnd >= 0
    monkeypatch.setattr("app.shop.seed.PRODUCTS", broken)
    with psycopg.connect(url, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            seed_demo_data(conn)
    assert _scalar(url, "SELECT count(*) FROM products") == 0
    monkeypatch.undo()
    with psycopg.connect(url, autocommit=True) as conn:
        seed_demo_data(conn)
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


def test_bootstrap_is_idempotent_and_seeds_once(bootstrapped_db):
    bootstrap.run(bootstrapped_db)
    url = bootstrapped_db.bootstrap_database_url
    assert _scalar(url, "SELECT count(*) FROM products") == len(PRODUCTS)
    assert _scalar(url, "SELECT count(*) FROM orders") == len(ORDERS)
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
