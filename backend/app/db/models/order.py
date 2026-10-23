"""Đơn hàng và dòng hàng. Địa chỉ giao nằm ở `shipping_address` (bản chụp lúc đặt, nguồn duy nhất)."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, Uuid, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Order(Base):
    """Trạng thái thanh toán không nằm ở đây: suy ra từ bảng `payments`."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_payment', 'processing', 'shipped', 'delivered', 'cancelled')", name="status_valid"
        ),
        CheckConstraint("total_vnd >= 0", name="total_non_negative"),
        CheckConstraint("subtotal_vnd >= 0", name="subtotal_non_negative"),
        CheckConstraint("shipping_fee_vnd >= 0", name="shipping_fee_non_negative"),
        CheckConstraint("total_vnd = subtotal_vnd + shipping_fee_vnd", name="total_is_subtotal_plus_shipping"),
        # Hạn hoàn tiền tính từ delivered_at nên đơn đã giao bắt buộc có mốc này
        CheckConstraint("status <> 'delivered' OR delivered_at IS NOT NULL", name="delivered_has_delivered_at"),
        # Một khoá idempotency chỉ tạo một đơn cho mỗi khách (NULL = đơn tạo ngoài luồng checkout)
        UniqueConstraint("user_id", "idempotency_key", name="uq_orders_user_id_idempotency_key"),
        # Đích của khoá ngoại ghép (order_id, user_id) từ refunds
        UniqueConstraint("id", "user_id", name="uq_orders_id_user_id"),
        Index("ix_orders_expires_at_pending", "expires_at", postgresql_where=text("status = 'pending_payment'")),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(Text)
    subtotal_vnd: Mapped[int] = mapped_column(BigInteger)
    shipping_fee_vnd: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    total_vnd: Mapped[int] = mapped_column(BigInteger)
    shipping_address: Mapped[dict[str, Any]] = mapped_column(JSONB)
    note: Mapped[str | None] = mapped_column(Text)
    carrier: Mapped[str | None] = mapped_column(Text)
    tracking_code: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Ghi một lần (trigger chặn sửa): mốc tính hạn hoàn tiền
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stock_released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    request_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("qty BETWEEN 1 AND 10", name="qty_in_range"),
        CheckConstraint("unit_price_vnd >= 0", name="unit_price_non_negative"),
    )

    order_id: Mapped[str] = mapped_column(Text, ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), primary_key=True, index=True)
    # Bản chụp tên/giá lúc đặt: đổi giá sản phẩm sau này không làm lệch đơn cũ
    product_name: Mapped[str] = mapped_column(Text)
    unit_price_vnd: Mapped[int] = mapped_column(BigInteger)
    qty: Mapped[int] = mapped_column(Integer)
