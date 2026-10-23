"""Nạp dữ liệu mẫu (sản phẩm, khách, đơn, KB) cho bảng còn trống. Chạy ở bước bootstrap bằng role migrator.

Chỉ chạy khi SEED_DEMO_DATA=true (mặc định tắt). Mỗi nhóm dữ liệu chỉ nạp nếu bảng tương ứng còn trống nên chạy
nhiều lần không nhân đôi và không đè dữ liệu thật. Khách demo (id UUID cố định, công khai trong bundle frontend),
đơn mẫu và tài khoản staff demo chỉ tạo khi ENV=dev (staff còn cần mật khẩu); ENV khác chỉ nạp sản phẩm và KB.
"""
import json

import psycopg
from argon2 import PasswordHasher

from app.kb.documents import PolicyNumbers, build_kb_documents
from app.settings.migrate import MigrateSettings
from app.shop.seed_data import (
    CUSTOMERS, DEMO_CUSTOMER_ID, IMAGES, ORDERS, PRODUCTS, SHIPPING_ADDRESS, STAFF_DEMO_EMAIL, STAFF_DEMO_ID,
)

_PRICES = {p["slug"]: p for p in PRODUCTS}


def _count(conn: psycopg.Connection, table: str) -> int:
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608 - tên bảng cố định


def seed_demo_data(conn: psycopg.Connection, s: MigrateSettings) -> None:
    """Một transaction duy nhất: lỗi giữa chừng thì không để lại dữ liệu dở dang (lần chạy sau thấy bảng trống và nạp lại)."""
    with conn.transaction():
        _seed(conn, s)


def _seed(conn: psycopg.Connection, s: MigrateSettings) -> None:
    if _count(conn, "products") == 0:
        _seed_products(conn)
    # DB đã seed từ trước khi có ảnh: bổ sung image_url cho sản phẩm mẫu còn trống
    for slug, url in IMAGES.items():
        conn.execute("UPDATE products SET image_url = %s WHERE slug = %s AND image_url IS NULL", (url, slug))
    if _count(conn, "users") == 0:
        _seed_users(conn, s)
    if _count(conn, "orders") == 0 and conn.execute("SELECT 1 FROM users WHERE id = %s", (DEMO_CUSTOMER_ID,)).fetchone():
        _seed_orders(conn, s)
    if _count(conn, "kb_documents") == 0:
        _seed_kb(conn, s)


def _seed_products(conn: psycopg.Connection) -> None:
    for p in PRODUCTS:
        conn.execute(
            """INSERT INTO products (slug, name, category, brand, price_vnd, old_price_vnd,
                                     rating, stock, specs, description, image_url)
               VALUES (%(slug)s, %(name)s, %(category)s, %(brand)s, %(price_vnd)s,
                       %(old_price_vnd)s, %(rating)s, %(stock)s, %(specs)s, %(description)s, %(image_url)s)
               ON CONFLICT (slug) DO NOTHING""",
            {**p, "specs": json.dumps(p["specs"])},
        )


def _seed_users(conn: psycopg.Connection, s: MigrateSettings) -> None:
    if s.env != "dev":
        return
    for c in CUSTOMERS:
        conn.execute(
            "INSERT INTO users (id, email, full_name, phone, role) VALUES (%s, %s, %s, %s, 'customer')",
            (c["id"], c["email"], c["full_name"], c["phone"]),
        )
    if s.staff_demo_password is not None:
        # Băm trực tiếp bằng argon2-cffi: lớp xác thực đầy đủ (tham số, rehash) do phần đăng nhập đảm nhiệm
        password_hash = PasswordHasher().hash(s.staff_demo_password.get_secret_value())
        conn.execute(
            "INSERT INTO users (id, email, password_hash, full_name, role) VALUES (%s, %s, %s, 'Nhân viên Demo', 'staff')",
            (STAFF_DEMO_ID, STAFF_DEMO_EMAIL, password_hash),
        )


def _seed_orders(conn: psycopg.Connection, s: MigrateSettings) -> None:
    for o in ORDERS:
        lines = [(_PRICES[slug], qty) for slug, qty in o["items"]]
        subtotal = sum(p["price_vnd"] * qty for p, qty in lines)
        shipping_fee = 0 if subtotal >= s.free_shipping_from_vnd else s.shipping_fee_vnd
        delivered_days = o["delivered_days_ago"]
        conn.execute(
            """INSERT INTO orders (id, user_id, status, subtotal_vnd, shipping_fee_vnd, total_vnd, shipping_address,
                                   carrier, tracking_code, created_at, delivered_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now() - %s * interval '1 day',
                       CASE WHEN %s::int IS NULL THEN NULL ELSE now() - %s::int * interval '1 day' END)""",
            (o["id"], o["user_id"], o["status"], subtotal, shipping_fee, subtotal + shipping_fee,
             json.dumps(SHIPPING_ADDRESS), o["carrier"], o["tracking_code"], o["created_days_ago"],
             delivered_days, delivered_days),
        )
        for product, qty in lines:
            cur = conn.execute(
                """INSERT INTO order_items (order_id, product_id, product_name, unit_price_vnd, qty)
                   SELECT %s, id, %s, %s, %s FROM products WHERE slug = %s""",
                (o["id"], product["name"], product["price_vnd"], qty, product["slug"]),
            )
            if cur.rowcount != 1:  # catalog thiếu sản phẩm mẫu: dừng thay vì tạo đơn không có dòng hàng
                raise RuntimeError(f"Seed đơn {o['id']}: thiếu sản phẩm mẫu '{product['slug']}' trong bảng products")


def _seed_kb(conn: psycopg.Connection, s: MigrateSettings) -> None:
    policy = PolicyNumbers(s.refund_window_days, s.shipping_fee_vnd, s.free_shipping_from_vnd)
    for d in build_kb_documents(policy):
        conn.execute(
            "INSERT INTO kb_documents (slug, lang, title, category, body) VALUES (%(slug)s, %(lang)s, %(title)s, %(category)s, %(body)s)",
            d,
        )
