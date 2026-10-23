"""baseline: extensions, immutable_unaccent(), products/orders/refunds

Revision ID: 0001
Revises:
Create Date: 2026-10-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `vector` cần superuser nên bootstrap tạo trước; ở đây chỉ đảm bảo có mặt (no-op nếu đã có).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    # unaccent() không IMMUTABLE nên không dùng được trong index; hàm bọc này cố định từ điển.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.immutable_unaccent(text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$
        """
    )

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=False),
        sa.Column("price_vnd", sa.BigInteger(), nullable=False),
        sa.Column("old_price_vnd", sa.BigInteger(), nullable=True),
        sa.Column("rating", sa.Numeric(precision=2, scale=1), server_default=sa.text("0"), nullable=False),
        sa.Column("stock", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("specs", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("description", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.CheckConstraint("price_vnd >= 0", name=op.f("ck_products_price_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("slug", name=op.f("uq_products_slug")),
    )
    op.create_index(op.f("ix_products_category"), "products", ["category"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("total_vnd", sa.BigInteger(), nullable=False),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('processing', 'shipped', 'delivered', 'cancelled')", name=op.f("ck_orders_status_valid")
        ),
        sa.CheckConstraint("total_vnd >= 0", name=op.f("ck_orders_total_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
    )
    op.create_index(op.f("ix_orders_user_id"), "orders", ["user_id"])

    op.create_table(
        "refunds",
        sa.Column("order_id", sa.Text(), nullable=False),
        sa.Column("amount_vnd", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount_vnd > 0", name=op.f("ck_refunds_amount_positive")),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name=op.f("fk_refunds_order_id_orders")),
        sa.PrimaryKeyConstraint("order_id", name=op.f("pk_refunds")),
    )


def downgrade() -> None:
    op.drop_table("refunds")
    op.drop_index(op.f("ix_orders_user_id"), table_name="orders")
    op.drop_table("orders")
    op.drop_index(op.f("ix_products_category"), table_name="products")
    op.drop_table("products")
    op.execute("DROP FUNCTION IF EXISTS public.immutable_unaccent(text)")
    # Không DROP EXTENSION: bảng LangGraph (store_vectors) phụ thuộc `vector`; rollback production là roll-forward.
