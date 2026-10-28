"""giỏ hàng theo phiên, đơn hàng, yêu cầu hoàn tiền + 3 đơn mẫu

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-28
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # session_id là khoá truy cập giỏ hàng (UUID ngẫu nhiên do trình duyệt sinh), không phải tài khoản
    op.execute(
        """
        CREATE TABLE carts (
            session_id text NOT NULL,
            product_id bigint NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            qty        integer NOT NULL CHECK (qty BETWEEN 1 AND 10),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (session_id, product_id)
        )
        """
    )
    op.execute("CREATE SEQUENCE order_code_seq START 1000")
    # Khách tra đơn bằng (code, phone) nên phone luôn lưu dạng chuẩn hoá 0xxxxxxxxx
    op.execute(
        """
        CREATE TABLE orders (
            id               bigserial PRIMARY KEY,
            code             text NOT NULL UNIQUE DEFAULT ('SM' || lpad(nextval('order_code_seq')::text, 6, '0')),
            session_id       text,
            customer_name    text NOT NULL,
            phone            text NOT NULL,
            address          text NOT NULL,
            payment_method   text NOT NULL CHECK (payment_method IN ('cod', 'online')),
            payment_status   text NOT NULL DEFAULT 'unpaid' CHECK (payment_status IN ('unpaid', 'paid', 'refunded')),
            payment_ref      text,
            status           text NOT NULL DEFAULT 'processing'
                             CHECK (status IN ('processing', 'shipped', 'delivered', 'cancelled')),
            subtotal_vnd     bigint NOT NULL CHECK (subtotal_vnd >= 0),
            shipping_fee_vnd bigint NOT NULL CHECK (shipping_fee_vnd >= 0),
            total_vnd        bigint NOT NULL CHECK (total_vnd >= 0),
            created_at       timestamptz NOT NULL DEFAULT now(),
            delivered_at     timestamptz
        )
        """
    )
    op.execute("CREATE INDEX orders_phone_idx ON orders (phone)")
    op.execute("CREATE INDEX orders_session_idx ON orders (session_id)")
    # product_name/unit_price chụp tại thời điểm đặt: đổi giá sau này không làm lệch đơn cũ
    op.execute(
        """
        CREATE TABLE order_items (
            id             bigserial PRIMARY KEY,
            order_id       bigint NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            product_id     bigint NOT NULL REFERENCES products(id),
            product_slug   text NOT NULL,
            product_name   text NOT NULL,
            unit_price_vnd bigint NOT NULL CHECK (unit_price_vnd >= 0),
            qty            integer NOT NULL CHECK (qty > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE refund_requests (
            id          bigserial PRIMARY KEY,
            order_id    bigint NOT NULL REFERENCES orders(id),
            reason_code text NOT NULL CHECK (reason_code IN
                        ('not_as_described', 'defective', 'wrong_or_missing_item', 'damaged_in_shipping')),
            details     text NOT NULL DEFAULT '',
            item_slugs  text[],
            amount_vnd  bigint NOT NULL CHECK (amount_vnd > 0),
            status      text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
            staff_note  text,
            created_at  timestamptz NOT NULL DEFAULT now(),
            decided_at  timestamptz
        )
        """
    )
    # Mỗi đơn chỉ có một yêu cầu đang hiệu lực: chặn trùng ngay ở DB kể cả khi hai request chạy đồng thời
    op.execute(
        "CREATE UNIQUE INDEX refund_one_active_per_order ON refund_requests (order_id) "
        "WHERE status IN ('pending', 'approved')"
    )
    _seed_demo_orders()


def _seed_demo_orders() -> None:
    """3 đơn mẫu của khách SĐT 0900000001 để thử tra đơn/hoàn tiền (dữ liệu demo)."""
    demo = [
        # code, status, payment_method, payment_status, created, delivered, [(slug, qty)]
        ("SM000100", "delivered", "online", "paid", "5 days", "2 days", [("airpods-pro-2-usb-c", 1)]),
        ("SM000101", "shipped", "online", "paid", "1 day", None, [("anker-sac-20w", 2), ("pin-du-phong-anker-10000", 1)]),
        ("SM000102", "processing", "cod", "unpaid", "0 days", None, [("anker-sac-20w", 1)]),
    ]
    for code, status, method, paid, created, delivered, items in demo:
        values = ", ".join(f"('{slug}', {qty})" for slug, qty in items)
        delivered_sql = f"now() - interval '{delivered}'" if delivered else "NULL"
        op.execute(
            f"""
            WITH lines AS (
                SELECT p.id, p.slug, p.name, p.price_vnd, v.qty
                FROM (VALUES {values}) AS v(slug, qty)
                JOIN products p ON p.slug = v.slug
            ), totals AS (
                SELECT sum(price_vnd * qty) AS subtotal FROM lines
            ), new_order AS (
                INSERT INTO orders (code, customer_name, phone, address, payment_method, payment_status, status,
                                    subtotal_vnd, shipping_fee_vnd, total_vnd, created_at, delivered_at)
                SELECT '{code}', 'Khách Demo', '0900000001', '12 Nguyễn Huệ, Bến Nghé, Quận 1, TP. Hồ Chí Minh',
                       '{method}', '{paid}', '{status}', subtotal,
                       CASE WHEN subtotal >= 500000 THEN 0 ELSE 30000 END,
                       subtotal + CASE WHEN subtotal >= 500000 THEN 0 ELSE 30000 END,
                       now() - interval '{created}', {delivered_sql}
                FROM totals RETURNING id
            )
            INSERT INTO order_items (order_id, product_id, product_slug, product_name, unit_price_vnd, qty)
            SELECT new_order.id, lines.id, lines.slug, lines.name, lines.price_vnd, lines.qty FROM new_order, lines
            """
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS refund_requests")
    op.execute("DROP TABLE IF EXISTS order_items")
    op.execute("DROP TABLE IF EXISTS orders")
    op.execute("DROP SEQUENCE IF EXISTS order_code_seq")
    op.execute("DROP TABLE IF EXISTS carts")
