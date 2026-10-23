"""Ràng buộc ở DB là lớp bảo vệ cuối: chạy trên schema thật bằng role migrator (chủ bảng, không bị hạn chế quyền)."""
import pytest
from psycopg.errors import CheckViolation, ForeignKeyViolation, RestrictViolation, UniqueViolation

from app.settings.migrate import ROLE_MIGRATOR
from app.shop.seed_data import DEMO_CUSTOMER_ID, ORDER_REFUND_ELIGIBLE_ID, ORDER_SHIPPED_ID, OTHER_CUSTOMER_ID
from tests.db.conftest import expect_error
from tests.db.refund_rows import NEW_REFUND, insert_refund, refund_params

NEW_ORDER = (
    "INSERT INTO orders (id, user_id, status, subtotal_vnd, total_vnd, shipping_address, idempotency_key)"
    " VALUES (%s, %s, 'processing', 100, 100, '{}', %s)"
)


@pytest.fixture
def conn(connect_as):
    return connect_as(ROLE_MIGRATOR)


def _refund(conn, key: str, status: str = "pending_staff", order_id: str = ORDER_REFUND_ELIGIBLE_ID) -> None:
    insert_refund(conn, key, status, order_id=order_id)


def test_only_one_live_refund_per_order(conn):
    _refund(conn, "k1")
    expect_error(conn, UniqueViolation, NEW_REFUND, refund_params("k2", "pending_staff"))
    expect_error(conn, UniqueViolation, NEW_REFUND, refund_params("k3", "approved"))
    _refund(conn, "k4", order_id=ORDER_SHIPPED_ID)  # đơn khác không bị ảnh hưởng


def test_refund_can_be_resubmitted_after_rejection_or_cancel(conn):
    _refund(conn, "k1", "rejected")
    _refund(conn, "k2", "cancelled")
    _refund(conn, "k3")  # yêu cầu mới sau hai lần bị từ chối/huỷ
    expect_error(conn, UniqueViolation, NEW_REFUND, refund_params("k4", "pending_staff"))


def test_no_new_refund_after_paid_out(conn):
    _refund(conn, "k1", "paid_out")
    for key, status in (("k2", "pending_staff"), ("k3", "approved"), ("k4", "paid_out")):
        expect_error(conn, UniqueViolation, NEW_REFUND, refund_params(key, status))
    _refund(conn, "k5", "rejected")  # bản ghi không "sống" vẫn lưu được để giữ lịch sử


def test_refund_idempotency_key_is_unique_per_submission(conn):
    _refund(conn, "thread:call-1")
    expect_error(conn, UniqueViolation, NEW_REFUND, refund_params("thread:call-1", order_id=ORDER_SHIPPED_ID))


def test_refund_amount_rules(conn):
    _refund(conn, "k1")
    expect_error(conn, CheckViolation, "UPDATE refunds SET requested_amount_vnd = 0")
    expect_error(conn, CheckViolation, "UPDATE refunds SET approved_amount_vnd = 1001")  # vượt số tiền yêu cầu
    expect_error(conn, CheckViolation, "UPDATE refunds SET approved_amount_vnd = 0")
    conn.execute(
        "UPDATE refunds SET approved_amount_vnd = 600, status = 'approved', decided_by = %s, decided_at = now()",
        (DEMO_CUSTOMER_ID,),
    )


@pytest.mark.parametrize("qty", [0, 11, -1])
def test_order_item_qty_must_be_between_1_and_10(conn, qty):
    expect_error(
        conn, CheckViolation,
        "INSERT INTO order_items (order_id, product_id, product_name, unit_price_vnd, qty)"
        " SELECT %s, id, 'x', 1, %s FROM products LIMIT 1",
        (ORDER_SHIPPED_ID, qty),
    )


@pytest.mark.parametrize("qty", [1, 10])
def test_order_item_qty_bounds_are_inclusive(conn, qty):
    conn.execute(
        "INSERT INTO order_items (order_id, product_id, product_name, unit_price_vnd, qty)"
        " SELECT 'A102', id, 'x', 1, %s FROM products WHERE slug = 'iphone-16-128gb'",
        (qty,),
    )


def test_product_stock_cannot_go_negative(conn):
    expect_error(conn, CheckViolation, "UPDATE products SET stock = -1 WHERE slug = 'iphone-16-128gb'")
    conn.execute("UPDATE products SET stock = 0 WHERE slug = 'iphone-16-128gb'")


def test_order_idempotency_key_is_unique_per_user(conn):
    conn.execute(NEW_ORDER, ("N1", DEMO_CUSTOMER_ID, "key-1"))
    expect_error(conn, UniqueViolation, NEW_ORDER, ("N2", DEMO_CUSTOMER_ID, "key-1"))
    conn.execute(NEW_ORDER, ("N3", OTHER_CUSTOMER_ID, "key-1"))  # khách khác dùng cùng khoá được
    conn.execute(NEW_ORDER, ("N4", DEMO_CUSTOMER_ID, None))  # đơn không qua checkout: không có khoá
    conn.execute(NEW_ORDER, ("N5", DEMO_CUSTOMER_ID, None))


def test_order_delivered_at_is_write_once(conn):
    conn.execute(NEW_ORDER, ("N1", DEMO_CUSTOMER_ID, None))
    conn.execute("UPDATE orders SET status = 'delivered', delivered_at = now() WHERE id = 'N1'")
    expect_error(conn, RestrictViolation, "UPDATE orders SET delivered_at = now() - interval '9 day' WHERE id = 'N1'")
    expect_error(conn, RestrictViolation, "UPDATE orders SET delivered_at = NULL WHERE id = 'N1'")
    conn.execute("UPDATE orders SET carrier = 'GHN' WHERE id = 'N1'")  # cột khác vẫn sửa được


def test_foreign_keys_reject_unknown_references(conn):
    expect_error(conn, ForeignKeyViolation, NEW_ORDER, ("N1", "99999999-9999-4999-8999-999999999999", None))
    expect_error(conn, ForeignKeyViolation, NEW_REFUND, refund_params("k", order_id="NOPE"))


def test_user_email_is_unique_case_insensitively(conn):
    expect_error(conn, UniqueViolation, "INSERT INTO users (email, full_name) VALUES ('DEMO@Shopbot.Local', 'x')")


ENUM_CASES = [
    ("users", "INSERT INTO users (email, full_name, role) VALUES ('a@b.c', 'x', 'owner')"),
    ("orders", "INSERT INTO orders (id, user_id, status, subtotal_vnd, total_vnd, shipping_address)"
               f" VALUES ('E1', '{DEMO_CUSTOMER_ID}', 'paid', 1, 1, '{{}}')"),
    ("refunds source", "INSERT INTO refunds (order_id, user_id, source, requested_amount_vnd, reason, idempotency_key)"
                       f" VALUES ('A100', '{DEMO_CUSTOMER_ID}', 'phone', 1, 'x', 'e1')"),
    ("refunds status", "INSERT INTO refunds (order_id, user_id, source, requested_amount_vnd, reason, idempotency_key,"
                       f" status) VALUES ('A100', '{DEMO_CUSTOMER_ID}', 'customer_request', 1, 'x', 'e2', 'done')"),
    ("conversations", f"INSERT INTO conversations (user_id, status) VALUES ('{DEMO_CUSTOMER_ID}', 'paused')"),
    ("support_tickets category", "INSERT INTO support_tickets (user_id, category, summary)"
                                 f" VALUES ('{DEMO_CUSTOMER_ID}', 'spam', 'x')"),
    ("support_tickets priority", "INSERT INTO support_tickets (user_id, category, summary, priority)"
                                 f" VALUES ('{DEMO_CUSTOMER_ID}', 'other', 'x', 'urgent')"),
    ("support_tickets status", "INSERT INTO support_tickets (user_id, category, summary, status)"
                               f" VALUES ('{DEMO_CUSTOMER_ID}', 'other', 'x', 'done')"),
    ("notifications", f"INSERT INTO notifications (user_id, type) VALUES ('{DEMO_CUSTOMER_ID}', 'promo')"),
    ("status_events", "INSERT INTO status_events (entity_type, entity_id, to_status) VALUES ('cart', '1', 'x')"),
    ("kb_documents", "INSERT INTO kb_documents (slug, lang, title, category, body) VALUES ('s', 'fr', 't', 'c', 'b')"),
]


@pytest.mark.parametrize(("name", "statement"), ENUM_CASES, ids=[c[0] for c in ENUM_CASES])
def test_enum_checks_reject_unknown_values(conn, name, statement):
    expect_error(conn, CheckViolation, statement)


def test_valid_enum_values_are_accepted(conn):
    """Bảo đảm các CHECK ở trên không chặn nhầm giá trị hợp lệ (cả `pending_payment` mới của đơn)."""
    conn.execute(
        "INSERT INTO orders (id, user_id, status, subtotal_vnd, total_vnd, shipping_address)"
        f" VALUES ('E1', '{DEMO_CUSTOMER_ID}', 'pending_payment', 1, 1, '{{}}')"
    )
    conn.execute(f"INSERT INTO notifications (user_id, type) VALUES ('{DEMO_CUSTOMER_ID}', 'refund_decided')")
    conn.execute("INSERT INTO status_events (entity_type, entity_id, to_status) VALUES ('payment', 'p1', 'pending')")
    conn.execute(f"INSERT INTO conversations (user_id) VALUES ('{DEMO_CUSTOMER_ID}')")  # thread_id do server sinh
    assert conn.execute("SELECT count(*) FROM conversations WHERE thread_id IS NOT NULL").fetchone()[0] == 1

