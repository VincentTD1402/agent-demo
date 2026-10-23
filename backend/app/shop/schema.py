"""DDL cũ của cửa hàng (products, orders, refunds), không còn được API gọi.

Nguồn sự thật hiện là migration Alembic + app/shop/models.py; file này chỉ còn để đối chiếu và sẽ bị xoá
khi schema mới thay thế.
"""
import psycopg

_DDL = """
CREATE TABLE IF NOT EXISTS products (
    id            SERIAL PRIMARY KEY,
    slug          TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL,
    category      TEXT NOT NULL,
    brand         TEXT NOT NULL,
    price_vnd     BIGINT NOT NULL CHECK (price_vnd >= 0),
    old_price_vnd BIGINT,
    rating        NUMERIC(2, 1) NOT NULL DEFAULT 0,
    stock         INT NOT NULL DEFAULT 0,
    specs         JSONB NOT NULL DEFAULT '{}',
    description   TEXT NOT NULL DEFAULT '',
    image_url     TEXT
);
ALTER TABLE products ADD COLUMN IF NOT EXISTS image_url TEXT;
CREATE INDEX IF NOT EXISTS products_category_idx ON products (category);

CREATE TABLE IF NOT EXISTS orders (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('processing', 'shipped', 'delivered', 'cancelled')),
    total_vnd  BIGINT NOT NULL CHECK (total_vnd >= 0),
    items      JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS orders_user_idx ON orders (user_id);

-- order_id là khoá chính => mỗi đơn chỉ hoàn tiền một lần (idempotency)
CREATE TABLE IF NOT EXISTS refunds (
    order_id   TEXT PRIMARY KEY REFERENCES orders (id),
    amount_vnd BIGINT NOT NULL CHECK (amount_vnd > 0),
    reason     TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


async def ensure_schema(database_url: str) -> None:
    """Tạo bảng (idempotent). Chỉ dùng cho môi trường không chạy Alembic."""
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as conn:
        await conn.execute(_DDL)
