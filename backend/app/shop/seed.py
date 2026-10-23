"""Nạp dữ liệu mẫu (sản phẩm, đơn hàng) cho bảng còn trống. Chạy ở bước bootstrap bằng role migrator."""
import json

import psycopg

from app.shop.seed_data import IMAGES, ORDERS, PRODUCTS


def _count(conn: psycopg.Connection, table: str) -> int:
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608 - tên bảng cố định


def seed_demo_data(conn: psycopg.Connection) -> None:
    """Một transaction duy nhất: lỗi giữa chừng thì không để lại dữ liệu dở dang (lần chạy sau thấy bảng trống và nạp lại)."""
    with conn.transaction():
        _seed(conn)


def _seed(conn: psycopg.Connection) -> None:
    if _count(conn, "products") == 0:
        for p in PRODUCTS:
            conn.execute(
                """INSERT INTO products (slug, name, category, brand, price_vnd, old_price_vnd,
                                         rating, stock, specs, description, image_url)
                   VALUES (%(slug)s, %(name)s, %(category)s, %(brand)s, %(price_vnd)s,
                           %(old_price_vnd)s, %(rating)s, %(stock)s, %(specs)s, %(description)s, %(image_url)s)
                   ON CONFLICT (slug) DO NOTHING""",
                {**p, "specs": json.dumps(p["specs"])},
            )
    # DB đã seed từ trước khi có ảnh: bổ sung image_url cho sản phẩm mẫu còn trống
    for slug, url in IMAGES.items():
        conn.execute("UPDATE products SET image_url = %s WHERE slug = %s AND image_url IS NULL", (url, slug))
    if _count(conn, "orders") == 0:
        for o in ORDERS:
            conn.execute(
                "INSERT INTO orders (id, user_id, status, total_vnd, items) VALUES (%s, %s, %s, %s, %s)"
                " ON CONFLICT (id) DO NOTHING",
                (o["id"], o["user_id"], o["status"], o["total_vnd"], json.dumps(o["items"])),
            )
