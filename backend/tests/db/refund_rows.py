"""Dựng dòng refunds hợp lệ theo từng trạng thái (các CHECK bắt trạng thái đã duyệt/chi trả có đủ trường đi kèm)."""
from datetime import UTC, datetime

from app.shop.seed_data import DEMO_CUSTOMER_ID, ORDER_REFUND_ELIGIBLE_ID

NEW_REFUND = (
    "INSERT INTO refunds (order_id, user_id, source, requested_amount_vnd, reason, idempotency_key, status,"
    " decided_by, decided_at, approved_amount_vnd, payout_reference)"
    " VALUES (%s, %s, %s, 1000, 'lỗi', %s, %s, %s, %s, %s, %s)"
)
# Thứ tự tham số của NEW_REFUND (để test bỏ từng trường)
PARAM_FIELDS = (
    "order_id", "user_id", "source", "key", "status", "decided_by", "decided_at", "approved_amount_vnd",
    "payout_reference",
)
_DECIDED = {"approved", "rejected", "paid_out"}


def refund_params(
    key: str, status: str = "pending_staff", order_id: str = ORDER_REFUND_ELIGIBLE_ID,
    source: str = "customer_request", user_id: str = DEMO_CUSTOMER_ID,
) -> tuple:
    """Tham số cho NEW_REFUND. Người duyệt dùng một user bất kỳ (khoá ngoại tới users là đủ cho test)."""
    decided = status in _DECIDED
    return (
        order_id, user_id, source, key, status,
        DEMO_CUSTOMER_ID if decided else None,
        datetime.now(UTC) if decided else None,
        1000 if status in ("approved", "paid_out") else None,
        "REF-1" if status == "paid_out" else None,
    )


def insert_refund(conn, key: str, status: str = "pending_staff", **kwargs) -> None:
    conn.execute(NEW_REFUND, refund_params(key, status, **kwargs))
