"""Schema cửa hàng (products, orders, refunds) và dữ liệu mẫu khi bảng còn trống."""
import json

import psycopg

from app.shop.seed_data import IMAGES, ORDERS, PRODUCTS

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


async def ensure_schema(database_url: str, seed: bool) -> None:
    """Tạo bảng (idempotent); nếu seed=True thì nạp dữ liệu mẫu cho bảng còn trống."""
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as conn:
        await conn.execute(_DDL)
        if not seed:
            return
        if (await (await conn.execute("SELECT count(*) FROM products")).fetchone())[0] == 0:
            for p in PRODUCTS:
                await conn.execute(
                    """INSERT INTO products (slug, name, category, brand, price_vnd, old_price_vnd,
                                             rating, stock, specs, description, image_url)
                       VALUES (%(slug)s, %(name)s, %(category)s, %(brand)s, %(price_vnd)s,
                               %(old_price_vnd)s, %(rating)s, %(stock)s, %(specs)s, %(description)s, %(image_url)s)
                       ON CONFLICT (slug) DO NOTHING""",
                    {**p, "specs": json.dumps(p["specs"])},
                )
        # DB đã seed từ trước khi có ảnh: bổ sung image_url cho sản phẩm mẫu còn trống
        for slug, url in IMAGES.items():
            await conn.execute(
                "UPDATE products SET image_url = %s WHERE slug = %s AND image_url IS NULL", (url, slug)
            )
        if (await (await conn.execute("SELECT count(*) FROM orders")).fetchone())[0] == 0:
            for o in ORDERS:
                await conn.execute(
                    "INSERT INTO orders (id, user_id, status, total_vnd, items) VALUES (%s, %s, %s, %s, %s)"
                    " ON CONFLICT (id) DO NOTHING",
                    (o["id"], o["user_id"], o["status"], o["total_vnd"], json.dumps(o["items"])),
                )
