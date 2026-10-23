"""Revision 0004/0005 xoá đơn/hoàn tiền dạng cũ: chỉ chạy khi bảng trống hoặc có cờ allow_destroy_legacy_orders."""
import psycopg
import pytest
from alembic import command

from app.db import bootstrap
from app.db.roles import prepare_cluster
from app.settings.migrate import MigrateSettings
from app.shop.seed_data import DEMO_CUSTOMER_ID

FLAG = "allow_destroy_legacy_orders"


def _scalar(url: str, query: str):
    with psycopg.connect(url) as conn:
        return conn.execute(query).fetchone()[0]


def _cfg(settings, allow: bool = False):
    return bootstrap.alembic_config(settings.migrator_database_url, allow_destroy_legacy_orders=allow)


@pytest.fixture
def legacy_db(fresh_db):
    """DB ở revision 0001 với một đơn và một khoản hoàn tiền dạng cũ."""
    with psycopg.connect(fresh_db.bootstrap_database_url, autocommit=True) as su:
        prepare_cluster(su, fresh_db)
    command.upgrade(_cfg(fresh_db), "0001")
    with psycopg.connect(fresh_db.bootstrap_database_url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO orders (id, user_id, status, total_vnd, items) VALUES ('A1', 'demo-user', 'delivered', 5, '[]')"
        )
        conn.execute("INSERT INTO refunds (order_id, amount_vnd, reason) VALUES ('A1', 5, 'x')")
    return fresh_db


def test_upgrade_refuses_when_legacy_orders_exist_and_changes_nothing(legacy_db):
    url = legacy_db.bootstrap_database_url
    with pytest.raises(RuntimeError, match=FLAG) as exc:
        command.upgrade(_cfg(legacy_db), "head")
    assert "1 dòng ở orders" in str(exc.value) and "1 dòng ở refunds" in str(exc.value)
    assert _scalar(url, "SELECT count(*) FROM orders") == 1
    assert _scalar(url, "SELECT count(*) FROM refunds") == 1
    assert _scalar(url, "SELECT version_num FROM alembic_version") == "0001"


def test_upgrade_passes_with_the_flag_and_drops_legacy_rows(legacy_db):
    command.upgrade(_cfg(legacy_db, allow=True), "head")
    url = legacy_db.bootstrap_database_url
    assert _scalar(url, "SELECT count(*) FROM orders") == 0
    assert _scalar(url, "SELECT count(*) FROM refunds") == 0


def test_upgrade_passes_without_the_flag_when_tables_are_empty(fresh_db):
    with psycopg.connect(fresh_db.bootstrap_database_url, autocommit=True) as su:
        prepare_cluster(su, fresh_db)
    command.upgrade(_cfg(fresh_db), "head")
    assert _scalar(fresh_db.bootstrap_database_url, "SELECT count(*) FROM alembic_version") == 1


def test_refunds_revision_has_its_own_guard(legacy_db):
    """0005 tự kiểm tra bảng refunds (khi 0004 đã chạy mà refunds còn dòng, ví dụ 0004 chạy riêng rồi bị chặn)."""
    command.upgrade(_cfg(legacy_db, allow=True), "0004")
    with psycopg.connect(legacy_db.bootstrap_database_url, autocommit=True) as conn:
        conn.execute("INSERT INTO users (id, email, full_name) VALUES (%s, 'g@x.y', 'g')", (DEMO_CUSTOMER_ID,))
        conn.execute(
            "INSERT INTO orders (id, user_id, status, subtotal_vnd, total_vnd, shipping_address)"
            " VALUES ('G1', %s, 'processing', 1, 1, '{}')",
            (DEMO_CUSTOMER_ID,),
        )
        conn.execute("INSERT INTO refunds (order_id, amount_vnd, reason) VALUES ('G1', 1, 'x')")
    with pytest.raises(RuntimeError, match="1 dòng ở refunds"):
        command.upgrade(_cfg(legacy_db), "0005")
    assert _scalar(legacy_db.bootstrap_database_url, "SELECT count(*) FROM refunds") == 1
    command.upgrade(_cfg(legacy_db, allow=True), "0005")
    assert _scalar(legacy_db.bootstrap_database_url, "SELECT count(*) FROM refunds") == 0


def test_downgrade_refuses_when_orders_exist_and_passes_with_flag(bootstrapped_db):
    url = bootstrapped_db.bootstrap_database_url
    orders = _scalar(url, "SELECT count(*) FROM orders")
    assert orders > 0
    with pytest.raises(RuntimeError, match=FLAG):
        command.downgrade(_cfg(bootstrapped_db), "0003")
    assert _scalar(url, "SELECT count(*) FROM orders") == orders
    command.downgrade(_cfg(bootstrapped_db, allow=True), "0003")
    assert _scalar(url, "SELECT version_num FROM alembic_version") == "0003"


def test_downgrade_of_refunds_revision_refuses_when_refunds_exist(bootstrapped_db):
    url = bootstrapped_db.bootstrap_database_url
    with psycopg.connect(bootstrapped_db.migrator_database_url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO refunds (order_id, user_id, source, requested_amount_vnd, reason, idempotency_key)"
            " SELECT id, user_id, 'customer_request', 1, 'x', 'k' FROM orders WHERE id = 'A100'"
        )
    with pytest.raises(RuntimeError, match="1 dòng ở refunds"):
        command.downgrade(_cfg(bootstrapped_db), "0004")
    assert _scalar(url, "SELECT count(*) FROM refunds") == 1


def test_bootstrap_refuses_legacy_rows_unless_setting_enabled(legacy_db):
    assert legacy_db.allow_destroy_legacy_orders is False
    with pytest.raises(RuntimeError, match=FLAG):
        bootstrap.run(legacy_db)
    allowed: MigrateSettings = legacy_db.model_copy(update={"allow_destroy_legacy_orders": True})
    bootstrap.run(allowed)
    assert _scalar(legacy_db.bootstrap_database_url, "SELECT count(*) FROM refunds") == 0
    assert _scalar(legacy_db.bootstrap_database_url, "SELECT count(*) FROM orders") > 0  # seed nạp lại đơn mẫu
