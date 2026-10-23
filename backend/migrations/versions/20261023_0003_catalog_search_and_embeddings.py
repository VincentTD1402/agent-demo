"""catalog: is_active, stock >= 0, trigram + embeddings, grants

Biến đổi bảng `products` của 0001 tại chỗ (dữ liệu hiện có được giữ nguyên).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    op.execute("ALTER TABLE products ADD CONSTRAINT ck_products_stock_non_negative CHECK (stock >= 0)")
    # Index trigram trên tên đã bỏ dấu; truy vấn phải dùng đúng biểu thức immutable_unaccent(name)
    op.execute("CREATE INDEX ix_products_name_trgm ON products USING gin (immutable_unaccent(name) gin_trgm_ops)")

    op.create_table(
        "product_embeddings",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_product_embeddings_product_id_products"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("product_id", name=op.f("pk_product_embeddings")),
    )
    op.execute(
        "CREATE INDEX ix_product_embeddings_embedding_hnsw ON product_embeddings"
        " USING hnsw (embedding vector_cosine_ops)"
    )

    op.execute("GRANT UPDATE ON products TO shopbot_app")  # checkout trừ/hoàn tồn kho
    op.execute("GRANT SELECT ON products, product_embeddings TO shopbot_mcp")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON products FROM shopbot_mcp")
    op.execute("REVOKE UPDATE ON products FROM shopbot_app")
    op.drop_table("product_embeddings")
    op.execute("DROP INDEX ix_products_name_trgm")
    op.execute("ALTER TABLE products DROP CONSTRAINT ck_products_stock_non_negative")
    op.drop_column("products", "is_active")
