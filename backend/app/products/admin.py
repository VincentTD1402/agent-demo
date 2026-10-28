"""Quản trị danh mục sản phẩm cho chủ shop: thêm, sửa, xoá, đặt ảnh. Giá/tồn kho đổi ở đây có hiệu lực ngay với website và trợ lý."""

import json

from psycopg import errors
from psycopg_pool import ConnectionPool

from app.products.repository import PgProductRepository
from app.shop.common import ShopError

CATEGORIES = ("dien-thoai", "laptop", "may-tinh-bang", "dong-ho", "phu-kien")
_EDITABLE = ("name", "category", "brand", "price_vnd", "old_price_vnd", "rating", "stock", "specs", "description", "image_url")


class ProductAdminService:
    def __init__(self, pool: ConnectionPool):
        self._pool = pool
        self._repo = PgProductRepository(pool)

    def create(self, slug: str, data: dict) -> dict:
        try:
            with self._pool.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO products (slug, name, category, brand, price_vnd, old_price_vnd, rating, stock, specs,
                                          description, image_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CAST(%s AS jsonb), %s, %s)
                    """,
                    (slug, data["name"], data["category"], data["brand"], data["price_vnd"], data["old_price_vnd"],
                     data["rating"], data["stock"], json.dumps(data["specs"], ensure_ascii=False), data["description"],
                     data["image_url"]),
                )
        except errors.UniqueViolation:
            raise ShopError("Mã sản phẩm (slug) này đã tồn tại") from None
        return self._repo.get(slug)

    def update(self, slug: str, data: dict) -> dict:
        """Ghi đè toàn bộ trường chỉnh sửa được; slug không đổi vì đã nằm trong đường dẫn, giỏ hàng và đơn cũ."""
        with self._pool.connection() as conn:
            updated = conn.execute(
                """
                UPDATE products SET name = %s, category = %s, brand = %s, price_vnd = %s, old_price_vnd = %s, rating = %s,
                                    stock = %s, specs = CAST(%s AS jsonb), description = %s, image_url = %s
                WHERE slug = %s
                """,
                (*(json.dumps(data[k], ensure_ascii=False) if k == "specs" else data[k] for k in _EDITABLE), slug),
            ).rowcount
        if not updated:
            raise ShopError("Không tìm thấy sản phẩm này")
        return self._repo.get(slug)

    def delete(self, slug: str) -> str | None:
        """Xoá sản phẩm chưa từng được đặt; trả về image_url cũ để nơi gọi dọn file ảnh."""
        with self._pool.connection() as conn:
            row = conn.execute("SELECT id, image_url FROM products WHERE slug = %s FOR UPDATE", (slug,)).fetchone()
            if row is None:
                raise ShopError("Không tìm thấy sản phẩm này")
            if conn.execute("SELECT 1 FROM order_items WHERE product_id = %s LIMIT 1", (row[0],)).fetchone():
                raise ShopError("Sản phẩm đã có trong đơn hàng nên không xoá được; hãy đặt tồn kho về 0 để ngừng bán")
            conn.execute("DELETE FROM products WHERE id = %s", (row[0],))  # giỏ hàng chứa sản phẩm này tự bị xoá theo
            return row[1]

    def set_image(self, slug: str, url: str) -> tuple[dict, str | None]:
        """Đặt ảnh mới; trả về (sản phẩm, URL ảnh cũ)."""
        with self._pool.connection() as conn:
            row = conn.execute("SELECT image_url FROM products WHERE slug = %s FOR UPDATE", (slug,)).fetchone()
            if row is None:
                raise ShopError("Không tìm thấy sản phẩm này")
            conn.execute("UPDATE products SET image_url = %s WHERE slug = %s", (url, slug))
        return self._repo.get(slug), row[0]
