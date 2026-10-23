"""Model SQLAlchemy của miền cửa hàng; Alembic so sánh các model này với database."""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("price_vnd >= 0", name="price_non_negative"),)

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


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("status IN ('processing', 'shipped', 'delivered', 'cancelled')", name="status_valid"),
        CheckConstraint("total_vnd >= 0", name="total_non_negative"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, index=True)
    status: Mapped[str] = mapped_column(Text)
    total_vnd: Mapped[int] = mapped_column(BigInteger)
    items: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Refund(Base):
    """order_id là khoá chính nên mỗi đơn chỉ hoàn tiền một lần (idempotency)."""

    __tablename__ = "refunds"
    __table_args__ = (CheckConstraint("amount_vnd > 0", name="amount_positive"),)

    order_id: Mapped[str] = mapped_column(Text, ForeignKey("orders.id"), primary_key=True)
    amount_vnd: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
