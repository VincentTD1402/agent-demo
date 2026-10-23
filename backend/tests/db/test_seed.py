"""Seed: chỉ khi bảng trống, mặc định tắt, không tạo tài khoản khi tắt, staff demo chỉ ở ENV=dev, fixture e2e cố định."""
import psycopg
import pytest
from argon2 import PasswordHasher
from pydantic import SecretStr

from app.db import bootstrap
from app.kb.documents import PolicyNumbers, build_kb_documents
from app.shop.seed import seed_demo_data
from app.shop.seed_data import (
    CUSTOMERS, DEMO_CUSTOMER_ID, ORDER_COD_ID, ORDER_OTHER_CUSTOMER_ID, ORDER_REFUND_ELIGIBLE_ID, ORDER_SHIPPED_ID,
    ORDERS, PRODUCTS, STAFF_DEMO_EMAIL, STAFF_DEMO_ID,
)

SEEDED_TABLES = ("products", "users", "orders", "order_items", "kb_documents")
STAFF_PASSWORD = "StaffDemoPass1234"
STAFF_SECRET = SecretStr(STAFF_PASSWORD)


def _counts(url: str) -> dict[str, int]:
    with psycopg.connect(url) as conn:
        return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in SEEDED_TABLES}  # noqa: S608


def _seed(settings, **overrides) -> None:
    with psycopg.connect(settings.migrator_database_url, autocommit=True) as conn:
        seed_demo_data(conn, settings.model_copy(update=overrides))


def _empty(settings) -> None:
    with psycopg.connect(settings.migrator_database_url, autocommit=True) as conn:
        conn.execute("TRUNCATE users, products, kb_documents RESTART IDENTITY CASCADE")


def test_seed_twice_does_not_duplicate(bootstrapped_db):
    url = bootstrapped_db.migrator_database_url
    first = _counts(url)
    assert first["products"] == len(PRODUCTS) and first["orders"] == len(ORDERS) and first["users"] == len(CUSTOMERS)
    _seed(bootstrapped_db)
    _seed(bootstrapped_db)
    assert _counts(url) == first


def test_seed_does_not_touch_tables_that_already_have_rows(bootstrapped_db):
    """Có dữ liệu thật trong bảng thì seed không chèn thêm vào bảng đó."""
    url = bootstrapped_db.migrator_database_url
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("TRUNCATE users, orders, kb_documents RESTART IDENTITY CASCADE")
        conn.execute("INSERT INTO users (email, full_name) VALUES ('real@example.com', 'Real')")
    _seed(bootstrapped_db)
    counts = _counts(url)
    assert counts["users"] == 1, "users đã có dòng: không nạp khách mẫu"
    assert counts["orders"] == 0, "không có khách demo thì không nạp đơn mẫu"
    assert counts["kb_documents"] > 0, "bảng KB còn trống nên được nạp"


def test_seed_off_creates_no_account_and_no_data(fresh_db):
    settings = fresh_db.model_copy(update={"seed_demo_data": False, "env": "dev", "staff_demo_password": STAFF_SECRET})
    bootstrap.run(settings)
    assert _counts(settings.migrator_database_url) == dict.fromkeys(SEEDED_TABLES, 0)


def test_staff_demo_account_only_in_dev_with_password(bootstrapped_db):
    url = bootstrapped_db.migrator_database_url
    staff_query = "SELECT id, password_hash, role FROM users WHERE email = %s"
    for overrides in (
        {"env": "production", "staff_demo_password": STAFF_SECRET},
        {"env": "staging", "staff_demo_password": STAFF_SECRET},
        {"env": "dev", "staff_demo_password": None},
    ):
        _empty(bootstrapped_db)
        _seed(bootstrapped_db, **overrides)
        with psycopg.connect(url) as conn:
            assert conn.execute(staff_query, (STAFF_DEMO_EMAIL,)).fetchone() is None, overrides

    _empty(bootstrapped_db)
    _seed(bootstrapped_db, env="dev", staff_demo_password=STAFF_SECRET)
    with psycopg.connect(url) as conn:
        staff_id, password_hash, role = conn.execute(staff_query, (STAFF_DEMO_EMAIL,)).fetchone()
        customers_with_hash = conn.execute("SELECT count(*) FROM users WHERE password_hash IS NOT NULL AND role = 'customer'")
        assert customers_with_hash.fetchone()[0] == 0
    assert str(staff_id) == STAFF_DEMO_ID and role == "staff"
    assert STAFF_PASSWORD not in password_hash and password_hash.startswith("$argon2id$")
    assert PasswordHasher().verify(password_hash, STAFF_PASSWORD)


@pytest.mark.parametrize("env", ["production", "staging", ""])
def test_demo_customers_and_orders_are_seeded_only_in_dev(bootstrapped_db, env):
    url = bootstrapped_db.migrator_database_url
    _empty(bootstrapped_db)
    _seed(bootstrapped_db, env=env, staff_demo_password=STAFF_SECRET)
    counts = _counts(url)
    assert counts["users"] == 0 and counts["orders"] == 0 and counts["order_items"] == 0
    assert counts["products"] == len(PRODUCTS) and counts["kb_documents"] > 0  # catalog và KB vẫn được nạp


def test_seed_fails_loudly_when_demo_products_are_missing(bootstrapped_db):
    url = bootstrapped_db.migrator_database_url
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("TRUNCATE orders RESTART IDENTITY CASCADE")
        conn.execute("DELETE FROM products WHERE slug = 'airpods-pro-2-usb-c'")
    with pytest.raises(RuntimeError, match="airpods-pro-2-usb-c"):
        _seed(bootstrapped_db)
    counts = _counts(url)
    assert counts["orders"] == 0 and counts["order_items"] == 0, "không để lại đơn không có dòng hàng"


def test_e2e_fixture_orders_are_consistent(bootstrapped_db):
    with psycopg.connect(bootstrapped_db.migrator_database_url) as conn:
        rows = {
            r[0]: r for r in conn.execute(
                "SELECT id, user_id::text, status, subtotal_vnd, shipping_fee_vnd, total_vnd, delivered_at,"
                " (SELECT sum(unit_price_vnd * qty) FROM order_items WHERE order_id = orders.id),"
                " now() - delivered_at FROM orders"
            )
        }
        assert set(rows) == {ORDER_REFUND_ELIGIBLE_ID, ORDER_SHIPPED_ID, ORDER_COD_ID, ORDER_OTHER_CUSTOMER_ID}
        for order_id, (_, _, _, subtotal, fee, total, _, items_total, _) in rows.items():
            assert subtotal == items_total and total == subtotal + fee, order_id
        eligible = rows[ORDER_REFUND_ELIGIBLE_ID]
        assert eligible[1] == DEMO_CUSTOMER_ID and eligible[2] == "delivered"
        assert eligible[8].days < bootstrapped_db.refund_window_days  # còn trong hạn hoàn tiền
        assert rows[ORDER_SHIPPED_ID][2] == "shipped" and rows[ORDER_SHIPPED_ID][6] is None
        cod = rows[ORDER_COD_ID]
        assert cod[2] == "processing" and cod[4] == bootstrapped_db.shipping_fee_vnd  # dưới ngưỡng miễn phí
        assert rows[ORDER_REFUND_ELIGIBLE_ID][4] == 0  # trên ngưỡng miễn phí
        assert rows[ORDER_OTHER_CUSTOMER_ID][1] != DEMO_CUSTOMER_ID


def test_seeded_kb_numbers_come_from_settings(fresh_db):
    settings = fresh_db.model_copy(update={"refund_window_days": 9, "shipping_fee_vnd": 45000, "free_shipping_from_vnd": 750000})
    bootstrap.run(settings)
    with psycopg.connect(settings.migrator_database_url) as conn:
        bodies = dict(conn.execute("SELECT slug || ':' || lang, body FROM kb_documents").fetchall())
    assert "9 ngày" in bodies["refund-policy:vi"] and "9 days" in bodies["refund-policy:en"]
    assert "45.000₫" in bodies["shipping:vi"] and "750.000₫" in bodies["shipping:vi"]
    assert "45,000 VND" in bodies["shipping:en"] and "750,000 VND" in bodies["shipping:en"]
    assert "7 ngày" not in bodies["refund-policy:vi"]


def test_kb_has_five_topics_in_both_languages():
    docs = build_kb_documents(PolicyNumbers(7, 30000, 500000))
    pairs = {(d["slug"], d["lang"]) for d in docs}
    topics = {"refund-policy", "warranty", "shipping", "installment", "exchange"}
    assert pairs == {(t, lang) for t in topics for lang in ("vi", "en")}
    assert all(d["body"].strip() and d["title"].strip() for d in docs)

