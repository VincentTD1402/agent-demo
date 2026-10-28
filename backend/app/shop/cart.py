"""Giỏ hàng theo phiên (session_id). Giá và tồn kho luôn đọc trực tiếp từ bảng products."""

from psycopg import Connection
from psycopg_pool import ConnectionPool

from app.shop.common import ShopError, ShopPolicy, check_session_id


class CartService:
    def __init__(self, pool: ConnectionPool, policy: ShopPolicy):
        self._pool = pool
        self._policy = policy

    def view(self, session_id: str) -> dict:
        check_session_id(session_id)
        with self._pool.connection() as conn:
            return self._view(conn, session_id)

    def add(self, session_id: str, slug: str, qty: int = 1) -> dict:
        check_session_id(session_id)
        if qty < 1:
            raise ShopError("Số lượng phải từ 1 trở lên")
        with self._pool.connection() as conn:
            product_id, name, stock = self._product(conn, slug)
            row = conn.execute(
                "SELECT qty FROM carts WHERE session_id = %s AND product_id = %s", (session_id, product_id)
            ).fetchone()
            self._upsert(conn, session_id, product_id, name, stock, (row[0] if row else 0) + qty)
            return self._view(conn, session_id)

    def set_quantity(self, session_id: str, slug: str, qty: int) -> dict:
        """Đặt số lượng tuyệt đối; qty = 0 thì bỏ dòng khỏi giỏ."""
        check_session_id(session_id)
        if qty < 0:
            raise ShopError("Số lượng không hợp lệ")
        with self._pool.connection() as conn:
            product_id, name, stock = self._product(conn, slug)
            if qty == 0:
                conn.execute("DELETE FROM carts WHERE session_id = %s AND product_id = %s", (session_id, product_id))
            else:
                self._upsert(conn, session_id, product_id, name, stock, qty)
            return self._view(conn, session_id)

    def remove(self, session_id: str, slug: str) -> dict:
        return self.set_quantity(session_id, slug, 0)

    def clear(self, session_id: str) -> dict:
        check_session_id(session_id)
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM carts WHERE session_id = %s", (session_id,))
            return self._view(conn, session_id)

    @staticmethod
    def _product(conn: Connection, slug: str) -> tuple[int, str, int]:
        row = conn.execute("SELECT id, name, stock FROM products WHERE slug = %s", (slug,)).fetchone()
        if row is None:
            raise ShopError("Không tìm thấy sản phẩm này")
        return row

    def _upsert(self, conn: Connection, session_id: str, product_id: int, name: str, stock: int, qty: int) -> None:
        if qty > self._policy.max_qty_per_line:
            raise ShopError(f"Mỗi sản phẩm chỉ mua tối đa {self._policy.max_qty_per_line} cái mỗi lần")
        if qty > stock:
            raise ShopError(f"{name} chỉ còn {stock} sản phẩm" if stock else f"{name} đã hết hàng")
        conn.execute(
            """
            INSERT INTO carts (session_id, product_id, qty) VALUES (%s, %s, %s)
            ON CONFLICT (session_id, product_id) DO UPDATE SET qty = EXCLUDED.qty, updated_at = now()
            """,
            (session_id, product_id, qty),
        )

    def _view(self, conn: Connection, session_id: str) -> dict:
        rows = conn.execute(
            """
            SELECT p.slug, p.name, p.category, p.price_vnd, p.image_url, c.qty, p.stock
            FROM carts c JOIN products p ON p.id = c.product_id
            WHERE c.session_id = %s ORDER BY c.updated_at, p.id
            """,
            (session_id,),
        ).fetchall()
        lines = [
            {"slug": slug, "name": name, "category": category, "price_vnd": price, "image_url": image,
             "qty": qty, "stock": stock, "line_total_vnd": price * qty}
            for slug, name, category, price, image, qty, stock in rows
        ]
        subtotal = sum(line["line_total_vnd"] for line in lines)
        shipping = self._policy.shipping_fee(subtotal) if lines else 0
        return {
            "lines": lines,
            "subtotal_vnd": subtotal,
            "shipping_fee_vnd": shipping,
            "total_vnd": subtotal + shipping,
            # Tồn kho có thể giảm sau khi thêm vào giỏ: báo để khách/agent xử lý trước khi chốt đơn
            "out_of_stock": [line["name"] for line in lines if line["qty"] > line["stock"]],
        }
