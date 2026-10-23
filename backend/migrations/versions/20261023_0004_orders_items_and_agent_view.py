"""orders (user_id uuid, địa chỉ chụp, mốc giao/hết hạn, idempotency), order_items, view orders_for_agent

Biến đổi bảng `orders` của 0001 tại chỗ: cột `items` jsonb bị thay bằng `order_items`, `user_id` text thành uuid
có khoá ngoại tới `users`. Dữ liệu đơn/hoàn tiền cũ chỉ là dữ liệu mẫu nên bị xoá (không có cách ánh xạ
user_id text sang người dùng thật); chạy được trên DB đã seed lẫn DB trống. Có dòng thì revision từ chối
chạy trừ khi `alembic -x allow_destroy_legacy_orders=true` (xem app/db/legacy_order_guard.py); downgrade cũng vậy.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.legacy_order_guard import require_destroy_allowed

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES_NEW = "'pending_payment', 'processing', 'shipped', 'delivered', 'cancelled'"
STATUSES_OLD = "'processing', 'shipped', 'delivered', 'cancelled'"

# mcp không bao giờ đọc bảng orders: chỉ view này, không có địa chỉ giao, ghi chú tự do, khoá idempotency
ORDERS_FOR_AGENT_VIEW = """
CREATE VIEW orders_for_agent AS
SELECT id, user_id, status, subtotal_vnd, shipping_fee_vnd, total_vnd, carrier, tracking_code,
       expires_at, delivered_at, created_at
FROM orders
"""

# delivered_at là mốc tính hạn hoàn tiền: đã ghi thì không được sửa lại
DELIVERED_AT_GUARD = """
CREATE FUNCTION forbid_delivered_at_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.delivered_at IS NOT NULL AND NEW.delivered_at IS DISTINCT FROM OLD.delivered_at THEN
        RAISE EXCEPTION 'orders.delivered_at is write-once' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END $$
"""


def upgrade() -> None:
    require_destroy_allowed(op.get_bind(), ("orders", "refunds"), "upgrade 0004")
    op.execute("DELETE FROM refunds")
    op.execute("DELETE FROM orders")

    op.execute("ALTER TABLE orders DROP CONSTRAINT ck_orders_status_valid")
    op.execute(f"ALTER TABLE orders ADD CONSTRAINT ck_orders_status_valid CHECK (status IN ({STATUSES_NEW}))")
    op.drop_index(op.f("ix_orders_user_id"), table_name="orders")
    op.drop_column("orders", "user_id")
    op.drop_column("orders", "items")
    op.add_column("orders", sa.Column("user_id", sa.Uuid(), nullable=False))
    op.add_column("orders", sa.Column("subtotal_vnd", sa.BigInteger(), nullable=False))
    op.add_column("orders", sa.Column("shipping_fee_vnd", sa.BigInteger(), server_default=sa.text("0"), nullable=False))
    op.add_column("orders", sa.Column("shipping_address", postgresql.JSONB(astext_type=sa.Text()), nullable=False))
    for name in ("note", "carrier", "tracking_code", "idempotency_key", "request_hash"):
        op.add_column("orders", sa.Column(name, sa.Text(), nullable=True))
    for name in ("expires_at", "delivered_at", "stock_released_at"):
        op.add_column("orders", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(op.f("fk_orders_user_id_users"), "orders", "users", ["user_id"], ["id"])
    op.create_index(op.f("ix_orders_user_id"), "orders", ["user_id"])
    op.execute("ALTER TABLE orders ADD CONSTRAINT ck_orders_subtotal_non_negative CHECK (subtotal_vnd >= 0)")
    op.execute("ALTER TABLE orders ADD CONSTRAINT ck_orders_shipping_fee_non_negative CHECK (shipping_fee_vnd >= 0)")
    op.execute("ALTER TABLE orders ADD CONSTRAINT ck_orders_total_is_subtotal_plus_shipping CHECK (total_vnd = subtotal_vnd + shipping_fee_vnd)")
    # Đơn đã giao phải có mốc giao: hạn hoàn tiền tính từ delivered_at
    op.execute("ALTER TABLE orders ADD CONSTRAINT ck_orders_delivered_has_delivered_at CHECK (status <> 'delivered' OR delivered_at IS NOT NULL)")
    op.create_unique_constraint(
        op.f("uq_orders_user_id_idempotency_key"), "orders", ["user_id", "idempotency_key"]
    )
    # Đích của khoá ngoại ghép (order_id, user_id) từ refunds: hoàn tiền luôn thuộc đúng chủ đơn
    op.create_unique_constraint(op.f("uq_orders_id_user_id"), "orders", ["id", "user_id"])
    op.execute(
        "CREATE INDEX ix_orders_expires_at_pending ON orders (expires_at) WHERE status = 'pending_payment'"
    )
    op.execute(DELIVERED_AT_GUARD)
    op.execute(
        "CREATE TRIGGER orders_delivered_at_write_once BEFORE UPDATE OF delivered_at ON orders"
        " FOR EACH ROW EXECUTE FUNCTION forbid_delivered_at_rewrite()"
    )

    op.create_table(
        "order_items",
        sa.Column("order_id", sa.Text(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=False),
        sa.Column("unit_price_vnd", sa.BigInteger(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.CheckConstraint("qty BETWEEN 1 AND 10", name=op.f("ck_order_items_qty_in_range")),
        sa.CheckConstraint("unit_price_vnd >= 0", name=op.f("ck_order_items_unit_price_non_negative")),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name=op.f("fk_order_items_order_id_orders"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_order_items_product_id_products")),
        sa.PrimaryKeyConstraint("order_id", "product_id", name=op.f("pk_order_items")),
    )
    op.create_index(op.f("ix_order_items_product_id"), "order_items", ["product_id"])
    op.execute(ORDERS_FOR_AGENT_VIEW)

    op.execute("GRANT INSERT, UPDATE ON orders, order_items TO shopbot_app")
    op.execute("GRANT SELECT ON order_items, orders_for_agent TO shopbot_mcp")


def downgrade() -> None:
    require_destroy_allowed(op.get_bind(), ("orders", "refunds"), "downgrade 0004")
    op.execute("DROP VIEW orders_for_agent")
    op.drop_table("order_items")
    op.execute("DROP TRIGGER orders_delivered_at_write_once ON orders")
    op.execute("DROP FUNCTION forbid_delivered_at_rewrite()")
    # Đơn mới không ánh xạ ngược được về user_id text/items jsonb: bỏ dữ liệu như lúc upgrade
    op.execute("DELETE FROM refunds")
    op.execute("DELETE FROM orders")
    op.execute("DROP INDEX ix_orders_expires_at_pending")
    op.drop_constraint(op.f("uq_orders_id_user_id"), "orders", type_="unique")
    op.drop_constraint(op.f("uq_orders_user_id_idempotency_key"), "orders", type_="unique")
    op.execute("ALTER TABLE orders DROP CONSTRAINT ck_orders_delivered_has_delivered_at")
    op.execute("ALTER TABLE orders DROP CONSTRAINT ck_orders_total_is_subtotal_plus_shipping")
    op.execute("ALTER TABLE orders DROP CONSTRAINT ck_orders_shipping_fee_non_negative")
    op.execute("ALTER TABLE orders DROP CONSTRAINT ck_orders_subtotal_non_negative")
    op.drop_index(op.f("ix_orders_user_id"), table_name="orders")
    op.drop_constraint(op.f("fk_orders_user_id_users"), "orders", type_="foreignkey")
    for name in (
        "stock_released_at", "delivered_at", "expires_at", "request_hash", "idempotency_key", "tracking_code",
        "carrier", "note", "shipping_address", "shipping_fee_vnd", "subtotal_vnd", "user_id",
    ):
        op.drop_column("orders", name)
    op.add_column("orders", sa.Column("user_id", sa.Text(), nullable=False))
    op.add_column(
        "orders",
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.create_index(op.f("ix_orders_user_id"), "orders", ["user_id"])
    op.execute("ALTER TABLE orders DROP CONSTRAINT ck_orders_status_valid")
    op.execute(f"ALTER TABLE orders ADD CONSTRAINT ck_orders_status_valid CHECK (status IN ({STATUSES_OLD}))")
    op.execute("REVOKE INSERT, UPDATE ON orders FROM shopbot_app")
