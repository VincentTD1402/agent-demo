"""Đơn hàng: chốt đơn từ giỏ, tra cứu, huỷ, thanh toán. Khách chứng minh quyền xem đơn bằng (mã đơn + SĐT đặt hàng)."""

from psycopg import Connection
from psycopg_pool import ConnectionPool

from app.shop.common import OrderNotFoundError, ShopError, ShopPolicy, check_session_id, iso, normalize_phone
from app.shop.lookup_guard import LookupGuard
from app.shop.payments import PaymentGateway

_COLUMNS = (
    "id, code, customer_name, address, payment_method, payment_status, status, "
    "subtotal_vnd, shipping_fee_vnd, total_vnd, created_at, delivered_at"
)
# Một thông điệp chung cho "sai mã" và "sai SĐT": không để kẻ đoán mã đơn biết mã nào tồn tại
_NOT_FOUND = "Không tìm thấy đơn hàng khớp mã đơn và số điện thoại này"
_STATUS_FLOW = {"processing": "shipped", "shipped": "delivered"}


class OrderService:
    def __init__(self, pool: ConnectionPool, policy: ShopPolicy, gateway: PaymentGateway, guard: LookupGuard):
        self._pool = pool
        self._guard = guard
        self._policy = policy
        self._gateway = gateway

    def checkout(self, session_id: str, customer_name: str, phone: str, address: str, payment_method: str) -> dict:
        check_session_id(session_id)
        name, address = (customer_name or "").strip(), (address or "").strip()
        if not 2 <= len(name) <= 100:
            raise ShopError("Cần họ tên người nhận (2-100 ký tự)")
        if not 10 <= len(address) <= 300:
            raise ShopError("Cần địa chỉ giao hàng đầy đủ (số nhà, đường, phường/xã, quận/huyện, tỉnh/thành)")
        if payment_method not in ("cod", "online"):
            raise ShopError("Phương thức thanh toán phải là 'cod' (khi nhận hàng) hoặc 'online'")
        phone = normalize_phone(phone)
        with self._pool.connection() as conn:  # một transaction: lỗi ở bất kỳ bước nào thì rollback toàn bộ
            recent = conn.execute(
                "SELECT count(*) FROM orders WHERE session_id = %s AND created_at > now() - interval '1 hour'", (session_id,)
            ).fetchone()[0]
            if recent >= self._policy.max_orders_per_session_per_hour:  # chặn spam đơn giữ chỗ tồn kho
                raise ShopError("Bạn đã đặt khá nhiều đơn trong một giờ qua. Vui lòng thử lại sau hoặc liên hệ nhân viên ShopMobile.")
            # Khoá các dòng sản phẩm (thứ tự id cố định để tránh deadlock): hai đơn cùng mua món cuối cùng sẽ xếp hàng
            rows = conn.execute(
                """
                SELECT p.id, p.slug, p.name, p.price_vnd, p.stock, c.qty
                FROM carts c JOIN products p ON p.id = c.product_id
                WHERE c.session_id = %s ORDER BY p.id FOR UPDATE OF p
                """,
                (session_id,),
            ).fetchall()
            if not rows:
                raise ShopError("Giỏ hàng đang trống")
            for _, _, product_name, _, stock, qty in rows:
                if qty > stock:
                    raise ShopError(f"{product_name} chỉ còn {stock} sản phẩm, không đủ {qty}" if stock else f"{product_name} đã hết hàng")
            subtotal = sum(price * qty for _, _, _, price, _, qty in rows)
            shipping = self._policy.shipping_fee(subtotal)
            order_id, code = conn.execute(
                """
                INSERT INTO orders (session_id, customer_name, phone, address, payment_method,
                                    subtotal_vnd, shipping_fee_vnd, total_vnd)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, code
                """,
                (session_id, name, phone, address, payment_method, subtotal, shipping, subtotal + shipping),
            ).fetchone()
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO order_items (order_id, product_id, product_slug, product_name, unit_price_vnd, qty) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    [(order_id, pid, slug, pname, price, qty) for pid, slug, pname, price, _, qty in rows],
                )
                cur.executemany("UPDATE products SET stock = stock - %s WHERE id = %s", [(qty, pid) for pid, *_, qty in rows])
            conn.execute("DELETE FROM carts WHERE session_id = %s", (session_id,))
            return self._view(conn, self._row(conn, "WHERE id = %s", (order_id,)))

    def get(self, code: str, phone: str) -> dict:
        return self._guard.verified(code, phone, lambda: self._get(code, phone))

    def _get(self, code: str, phone: str) -> dict:
        with self._pool.connection() as conn:
            return self._view(conn, self._find(conn, code, phone))

    def list_for_session(self, session_id: str) -> list[dict]:
        check_session_id(session_id)
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM orders WHERE session_id = %s ORDER BY id DESC LIMIT 10", (session_id,)  # noqa: S608
            ).fetchall()
            return [self._view(conn, row) for row in rows]

    def cancel(self, code: str, phone: str) -> dict:
        return self._guard.verified(code, phone, lambda: self._cancel(code, phone))

    def _cancel(self, code: str, phone: str) -> dict:
        """Chỉ huỷ được đơn đang xử lý và chưa thanh toán; đơn đã trả tiền cần nhân viên xử lý để hoàn tiền đúng."""
        with self._pool.connection() as conn:
            row = self._find(conn, code, phone, lock=True)
            _, order_code, *_ = row
            status, payment_status = row[6], row[5]
            if status != "processing":
                raise ShopError("Chỉ huỷ được đơn đang ở trạng thái 'đang xử lý' (chưa giao cho đơn vị vận chuyển)")
            if payment_status != "unpaid":
                raise ShopError("Đơn đã thanh toán trực tuyến nên cần nhân viên hỗ trợ huỷ và hoàn tiền")
            conn.execute(
                "UPDATE products p SET stock = p.stock + i.qty FROM order_items i WHERE i.product_id = p.id AND i.order_id = %s",
                (row[0],),
            )
            conn.execute("UPDATE orders SET status = 'cancelled' WHERE id = %s", (row[0],))
            return self._view(conn, self._row(conn, "WHERE id = %s", (row[0],)))

    def pay(self, code: str, phone: str) -> dict:
        return self._guard.verified(code, phone, lambda: self._pay(code, phone))

    def _pay(self, code: str, phone: str) -> dict:
        """Thanh toán trực tuyến cho đơn 'online' chưa trả. Số tiền luôn lấy từ DB, không nhận từ người gọi."""
        with self._pool.connection() as conn:
            row = self._find(conn, code, phone, lock=True)
            order_id, order_code, payment_method, payment_status, status, total = row[0], row[1], row[4], row[5], row[6], row[9]
            if status == "cancelled":
                raise ShopError("Đơn này đã huỷ")
            if payment_method != "online":
                raise ShopError("Đơn này thanh toán khi nhận hàng (COD), không cần thanh toán trước")
            if payment_status != "unpaid":
                raise ShopError("Đơn này đã được thanh toán")
            result = self._gateway.charge(order_code, total)
            if not result.ok:
                raise ShopError(result.message or "Thanh toán không thành công, vui lòng thử lại")
            conn.execute(
                "UPDATE orders SET payment_status = 'paid', payment_ref = %s WHERE id = %s", (result.reference, order_id)
            )
            return self._view(conn, self._row(conn, "WHERE id = %s", (order_id,)))

    def set_status(self, code: str, new_status: str) -> dict:
        """Nhân viên đẩy trạng thái: processing -> shipped -> delivered (giao xong thì đơn COD được ghi là đã thu tiền)."""
        with self._pool.connection() as conn:
            row = self._row(conn, "WHERE code = %s FOR UPDATE", (code.strip().upper(),))
            if row is None:
                raise ShopError("Không tìm thấy đơn hàng")
            if _STATUS_FLOW.get(row[6]) != new_status:
                raise ShopError(f"Không thể chuyển đơn từ '{row[6]}' sang '{new_status}'")
            conn.execute(
                """
                UPDATE orders SET status = %s,
                    delivered_at = CASE WHEN %s = 'delivered' THEN now() ELSE delivered_at END,
                    payment_status = CASE WHEN %s = 'delivered' AND payment_method = 'cod' THEN 'paid' ELSE payment_status END
                WHERE id = %s
                """,
                (new_status, new_status, new_status, row[0]),
            )
            return self._view(conn, self._row(conn, "WHERE id = %s", (row[0],)))

    @staticmethod
    def _row(conn: Connection, where: str, params: tuple) -> tuple | None:
        return conn.execute(f"SELECT {_COLUMNS} FROM orders {where}", params).fetchone()  # noqa: S608

    def _find(self, conn: Connection, code: str, phone: str, lock: bool = False) -> tuple:
        try:
            phone = normalize_phone(phone)
        except ShopError:
            raise OrderNotFoundError(_NOT_FOUND) from None
        row = self._row(
            conn, "WHERE code = %s AND phone = %s" + (" FOR UPDATE" if lock else ""), ((code or "").strip().upper(), phone)
        )
        if row is None:
            raise OrderNotFoundError(_NOT_FOUND)
        return row

    @staticmethod
    def _view(conn: Connection, row: tuple) -> dict:
        order_id, code, name, address, method, pay_status, status, subtotal, shipping, total, created, delivered = row
        items = conn.execute(
            "SELECT product_slug, product_name, unit_price_vnd, qty FROM order_items WHERE order_id = %s ORDER BY id",
            (order_id,),
        ).fetchall()
        refund = conn.execute(
            "SELECT id, status, amount_vnd, reason_code, staff_note FROM refund_requests WHERE order_id = %s ORDER BY id DESC LIMIT 1",
            (order_id,),
        ).fetchone()
        return {
            "code": code, "status": status, "payment_method": method, "payment_status": pay_status,
            "customer_name": name, "address": address,
            "items": [{"slug": s, "name": n, "unit_price_vnd": p, "qty": q} for s, n, p, q in items],
            "subtotal_vnd": subtotal, "shipping_fee_vnd": shipping, "total_vnd": total,
            "created_at": iso(created), "delivered_at": iso(delivered),
            "refund": None if refund is None else {
                "id": refund[0], "status": refund[1], "amount_vnd": refund[2], "reason_code": refund[3], "staff_note": refund[4],
            },
        }
