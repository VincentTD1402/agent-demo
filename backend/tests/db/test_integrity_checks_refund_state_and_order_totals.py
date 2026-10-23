"""CHECK/FK trạng thái hoàn tiền, tổng đơn, mốc giao, chủ đơn của khoản hoàn và chỉ mục "sống" theo nguồn."""
import pytest
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation

from app.settings.migrate import ROLE_MIGRATOR
from app.shop.seed_data import DEMO_CUSTOMER_ID, OTHER_CUSTOMER_ID
from tests.db.conftest import expect_error
from tests.db.refund_rows import NEW_REFUND, PARAM_FIELDS, insert_refund, refund_params

INSERT_ORDER = (
    "INSERT INTO orders (id, user_id, status, subtotal_vnd, shipping_fee_vnd, total_vnd, shipping_address, delivered_at)"
    " VALUES (%s, %s, %s, %s, %s, %s, '{}', %s)"
)


@pytest.fixture
def conn(connect_as):
    return connect_as(ROLE_MIGRATOR)


@pytest.mark.parametrize("missing", ["payout_reference", "approved_amount_vnd"])
def test_paid_out_requires_payout_reference_and_approved_amount(conn, missing):
    params = list(refund_params("k1", "paid_out"))
    params[PARAM_FIELDS.index(missing)] = None
    expect_error(conn, CheckViolation, NEW_REFUND, tuple(params))
    insert_refund(conn, "k2", "paid_out")  # đủ trường thì hợp lệ


@pytest.mark.parametrize("status", ["approved", "rejected"])
@pytest.mark.parametrize("missing", ["decided_by", "decided_at"])
def test_approved_and_rejected_require_decider_and_time(conn, status, missing):
    params = list(refund_params("k1", status))
    params[PARAM_FIELDS.index(missing)] = None
    expect_error(conn, CheckViolation, NEW_REFUND, tuple(params))
    insert_refund(conn, "k2", status)


def test_refund_must_belong_to_the_order_owner(conn):
    expect_error(
        conn, ForeignKeyViolation, NEW_REFUND, refund_params("k1", user_id=OTHER_CUSTOMER_ID),
    )
    insert_refund(conn, "k2")  # đúng chủ đơn


def test_system_refund_is_not_blocked_by_a_live_customer_request(conn):
    insert_refund(conn, "k1", "pending_staff")
    insert_refund(conn, "k2", "pending_staff", source="system_cancel_paid")
    expect_error(conn, UniqueViolation, NEW_REFUND, refund_params("k3", "approved", source="system_cancel_paid"))
    expect_error(conn, UniqueViolation, NEW_REFUND, refund_params("k4", "pending_staff"))  # khách vẫn một yêu cầu


def test_system_refund_can_be_created_after_customer_request_was_paid_out(conn):
    insert_refund(conn, "k1", "paid_out")
    insert_refund(conn, "k2", "pending_staff", source="system_cancel_paid")


def test_order_total_must_equal_subtotal_plus_shipping(conn):
    expect_error(conn, CheckViolation, INSERT_ORDER, ("T1", DEMO_CUSTOMER_ID, "processing", 100, 30, 100, None))
    expect_error(conn, CheckViolation, INSERT_ORDER, ("T2", DEMO_CUSTOMER_ID, "processing", 100, 0, 130, None))
    conn.execute(INSERT_ORDER, ("T3", DEMO_CUSTOMER_ID, "processing", 100, 30, 130, None))


def test_delivered_order_requires_delivered_at(conn):
    expect_error(conn, CheckViolation, INSERT_ORDER, ("D1", DEMO_CUSTOMER_ID, "delivered", 1, 0, 1, None))
    conn.execute(INSERT_ORDER, ("D2", DEMO_CUSTOMER_ID, "delivered", 1, 0, 1, "2026-01-01T00:00:00Z"))
    conn.execute(INSERT_ORDER, ("D3", DEMO_CUSTOMER_ID, "processing", 1, 0, 1, None))
    expect_error(conn, CheckViolation, "UPDATE orders SET status = 'delivered' WHERE id = 'D3'")
    conn.execute("UPDATE orders SET status = 'delivered', delivered_at = now() WHERE id = 'D3'")
