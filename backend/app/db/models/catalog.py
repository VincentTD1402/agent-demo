"""Danh mục sản phẩm và vector embedding để tìm kiếm ngữ nghĩa."""
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, Text, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

EMBEDDING_DIMS = 1024  # Qwen3-Embedding-0.6B


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price_vnd >= 0", name="price_non_negative"),
        CheckConstraint("stock >= 0", name="stock_non_negative"),
        # Tìm theo tên không phân biệt dấu: truy vấn phải dùng đúng biểu thức immutable_unaccent(name)
        Index(
            "ix_products_name_trgm", func.immutable_unaccent(text("name")), postgresql_using="gin",
            postgresql_ops={"immutable_unaccent(name)": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text, index=True)
    brand: Mapped[str] = mapped_column(Text)
    price_vnd: Mapped[int] = mapped_column(BigInteger)
    old_price_vnd: Mapped[int | None] = mapped_column(BigInteger)
    rating: Mapped[float] = mapped_column(Numeric(2, 1), server_default=text("0"))
    stock: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    specs: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    description: Mapped[str] = mapped_column(Text, server_default=text("''"))
    image_url: Mapped[str | None] = mapped_column(Text)
    # Ẩn sản phẩm khỏi cửa hàng/agent mà vẫn giữ lịch sử đơn
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class ProductEmbedding(Base):
    __tablename__ = "product_embeddings"
    __table_args__ = (
        Index(
            "ix_product_embeddings_embedding_hnsw", "embedding",
            postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    model: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMS))
    # sha256(model + nội dung): bằng nhau thì reindex bỏ qua, không gọi lại endpoint embedding
    content_hash: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
