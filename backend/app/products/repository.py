"""Truy vấn danh mục sản phẩm từ Postgres."""

from typing import Protocol

from psycopg_pool import ConnectionPool

_COLUMNS = "slug, name, category, brand, price_vnd, old_price_vnd, rating, stock, specs, description, image_url"


class ProductRepository(Protocol):
    def search(self, q: str | None, category: str | None, limit: int) -> list[dict]: ...

    def get(self, slug: str) -> dict | None: ...


def _row_to_dict(row: tuple) -> dict:
    product = dict(zip(_COLUMNS.split(", "), row))
    product["rating"] = float(product["rating"])  # numeric -> Decimal
    return product


def _escape_like(text: str) -> str:
    # Ký tự đặc biệt của LIKE phải được thoát để người dùng gõ "%" hay "_" không khớp mọi thứ
    return text.replace("\\", "\\\\").replace("%", "\%").replace("_", "\_")


class PgProductRepository:
    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    def search(self, q: str | None, category: str | None, limit: int) -> list[dict]:
        conditions, params = [], []
        if category:
            conditions.append("category = %s")
            params.append(category)
        if q:
            conditions.append("(name ILIKE %s OR brand ILIKE %s OR description ILIKE %s)")
            params.extend([f"%{_escape_like(q.strip())}%"] * 3)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        # Chỉ ghép điều kiện cố định vào SQL; giá trị người dùng luôn đi qua tham số
        sql = f"SELECT {_COLUMNS} FROM products {where} ORDER BY id LIMIT %s"  # noqa: S608
        with self._pool.connection() as conn:
            return [_row_to_dict(row) for row in conn.execute(sql, (*params, limit)).fetchall()]

    def get(self, slug: str) -> dict | None:
        with self._pool.connection() as conn:
            row = conn.execute(f"SELECT {_COLUMNS} FROM products WHERE slug = %s", (slug,)).fetchone()  # noqa: S608
        return _row_to_dict(row) if row else None
