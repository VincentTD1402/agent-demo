"""Hoàn tiền: kiểm tra điều kiện theo chính sách, tạo yêu cầu (chờ nhân viên duyệt), nhân viên duyệt/từ chối.

Agent không bao giờ tự hoàn tiền: `request` chỉ tạo yêu cầu ở trạng thái 'pending'; chỉ `decide` (API nhân viên) mới đổi trạng thái.
"""

from datetime import datetime, timedelta, timezone

from psycopg import Connection, errors
from psycopg_pool import ConnectionPool

from app.shop.common import OrderNotFoundError, ShopError, ShopPolicy, iso, normalize_phone
from app.shop.lookup_guard import LookupGuard

# Lý do được hoàn tiền (đều do lỗi phía cửa hàng/vận chuyển). 'changed_mind' không thuộc diện hoàn tiền.
ELIGIBLE_REASONS = {
    "not_as_described": "sản phẩm không đúng mô tả",
    "defective": "sản phẩm bị lỗi từ nhà sản xuất",
    "wrong_or_missing_item": "giao sai hoặc thiếu sản phẩm/phụ kiện",
    "damaged_in_shipping": "hư hỏng trong quá trình vận chuyển",
}
_NOT_FOUND = "Không tìm thấy đơn hàng khớp mã đơn và số điện thoại này"


class RefundService:
    def __init__(self, pool: ConnectionPool, policy: ShopPolicy, guard: LookupGuard):
        self._pool = pool
        self._guard = guard
        self._policy = policy

    def check(self, code: str, phone: str, reason_code: str, item_slugs: list[str] | None = None) -> dict:
        return self._guard.verified(code, phone, lambda: self._check(code, phone, reason_code, item_slugs))

    def _check(self, code: str, phone: str, reason_code: str, item_slugs: list[str] | None) -> dict:
        """Chỉ đánh giá điều kiện, không ghi gì."""
        with self._pool.connection() as conn:
            _, decision = self._evaluate(conn, code, phone, reason_code, item_slugs)
            return decision

    def request(self, code: str, phone: str, reason_code: str, details: str = "", item_slugs: list[str] | None = None) -> dict:
        return self._guard.verified(code, phone, lambda: self._request(code, phone, reason_code, details, item_slugs))

    def _request(self, code: str, phone: str, reason_code: str, details: str, item_slugs: list[str] | None) -> dict:
        with self._pool.connection() as conn:
            order_id, decision = self._evaluate(conn, code, phone, reason_code, item_slugs, lock=True)
            if not decision["eligible"]:
                raise ShopError(decision["reason"])
            try:
                refund_id = conn.execute(
                    "INSERT INTO refund_requests (order_id, reason_code, details, item_slugs, amount_vnd) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (order_id, reason_code, (details or "").strip()[:1000], item_slugs or None, decision["amount_vnd"]),
                ).fetchone()[0]
            except errors.UniqueViolation:  # hai yêu cầu cùng lúc: chỉ một cái được ghi
                raise ShopError("Đơn này đã có yêu cầu hoàn tiền đang được xử lý") from None
            return {
                "refund_id": refund_id, "status": "pending", "amount_vnd": decision["amount_vnd"],
                "next_step": "Nhân viên ShopMobile sẽ xem xét và liên hệ qua số điện thoại đặt hàng để xác nhận phương thức nhận tiền.",
            }

    def list_pending(self) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT r.id, o.code, o.customer_name, o.phone, o.payment_method, o.payment_status, o.total_vnd,
                       r.reason_code, r.details, r.item_slugs, r.amount_vnd, r.created_at
                FROM refund_requests r JOIN orders o ON o.id = r.order_id
                WHERE r.status = 'pending' ORDER BY r.id
                """
            ).fetchall()
        keys = ("id", "order_code", "customer_name", "phone", "payment_method", "payment_status", "order_total_vnd",
                "reason_code", "details", "item_slugs", "amount_vnd", "created_at")
        return [{**dict(zip(keys, row)), "created_at": iso(row[-1])} for row in rows]

    def decide(self, refund_id: int, approve: bool, note: str = "") -> dict:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT r.order_id, r.amount_vnd, r.status, o.total_vnd FROM refund_requests r
                JOIN orders o ON o.id = r.order_id WHERE r.id = %s FOR UPDATE OF r
                """,
                (refund_id,),
            ).fetchone()
            if row is None:
                raise ShopError("Không tìm thấy yêu cầu hoàn tiền")
            order_id, amount, status, order_total = row
            if status != "pending":
                raise ShopError("Yêu cầu này đã được xử lý")
            new_status = "approved" if approve else "rejected"
            conn.execute(
                "UPDATE refund_requests SET status = %s, staff_note = %s, decided_at = now() WHERE id = %s",
                (new_status, (note or "").strip()[:500] or None, refund_id),
            )
            if approve and amount == order_total:  # hoàn toàn bộ đơn: ghi nhận đã hoàn
                conn.execute("UPDATE orders SET payment_status = 'refunded' WHERE id = %s", (order_id,))
            return {"refund_id": refund_id, "status": new_status, "amount_vnd": amount}

    def _evaluate(
        self, conn: Connection, code: str, phone: str, reason_code: str, item_slugs: list[str] | None, lock: bool = False
    ) -> tuple[int, dict]:
        if reason_code != "changed_mind" and reason_code not in ELIGIBLE_REASONS:
            raise ShopError("Lý do không hợp lệ")
        try:
            phone = normalize_phone(phone)
        except ShopError:
            raise OrderNotFoundError(_NOT_FOUND) from None
        order = conn.execute(
            "SELECT id, status, delivered_at, total_vnd FROM orders WHERE code = %s AND phone = %s"
            + (" FOR UPDATE" if lock else ""),
            ((code or "").strip().upper(), phone),
        ).fetchone()
        if order is None:
            raise OrderNotFoundError(_NOT_FOUND)
        order_id, status, delivered_at, total = order

        def no(reason: str, deadline: datetime | None = None) -> tuple[int, dict]:
            return order_id, {"eligible": False, "reason": reason, "amount_vnd": 0, "deadline": iso(deadline)}

        if reason_code == "changed_mind":
            return no("Đổi ý, không còn nhu cầu không thuộc diện hoàn tiền nếu sản phẩm không lỗi và đúng mô tả")
        if status != "delivered" or delivered_at is None:
            return no("Chỉ hoàn tiền cho đơn đã giao" + (" (đơn đã huỷ)" if status == "cancelled" else ""))
        deadline = delivered_at + timedelta(days=self._policy.refund_window_days)
        if datetime.now(timezone.utc) > deadline:
            return no(f"Đã quá hạn hoàn tiền {self._policy.refund_window_days} ngày kể từ ngày nhận hàng", deadline)
        if conn.execute(
            "SELECT 1 FROM refund_requests WHERE order_id = %s AND status IN ('pending', 'approved')", (order_id,)
        ).fetchone():
            return no("Đơn này đã có yêu cầu hoàn tiền đang xử lý hoặc đã được hoàn", deadline)
        amount = self._amount(conn, order_id, total, item_slugs)
        return order_id, {"eligible": True, "reason": ELIGIBLE_REASONS[reason_code], "amount_vnd": amount, "deadline": iso(deadline)}

    @staticmethod
    def _amount(conn: Connection, order_id: int, total: int, item_slugs: list[str] | None) -> int:
        """Hoàn cả đơn (kèm phí vận chuyển) nếu không chọn món hoặc chọn đủ mọi món; chọn một phần thì chỉ hoàn tiền hàng."""
        if not item_slugs:
            return total
        items = conn.execute(
            "SELECT product_slug, unit_price_vnd * qty FROM order_items WHERE order_id = %s", (order_id,)
        ).fetchall()
        by_slug = dict(items)
        unknown = [slug for slug in item_slugs if slug not in by_slug]
        if unknown:
            raise ShopError(f"Sản phẩm không thuộc đơn hàng này: {', '.join(unknown)}")
        chosen = set(item_slugs)
        return total if chosen == set(by_slug) else sum(by_slug[slug] for slug in chosen)
