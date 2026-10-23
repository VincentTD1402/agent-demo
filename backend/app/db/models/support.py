"""Phiếu hỗ trợ, thông báo và bảng sự kiện đổi trạng thái chung (chỉ-thêm)."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        CheckConstraint(
            "category IN ('human_requested', 'complaint_legal', 'exchange_or_address', 'defective',"
            " 'refund_dispute', 'other')",
            name="category_valid",
        ),
        CheckConstraint("priority IN ('normal', 'high')", name="priority_valid"),
        CheckConstraint("status IN ('open', 'in_progress', 'resolved', 'closed')", name="status_valid"),
        Index("ix_support_tickets_status_due_at", "status", "due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    thread_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # không khoá ngoại: phiếu sống lâu hơn hội thoại
    order_id: Mapped[str | None] = mapped_column(Text, ForeignKey("orders.id"))
    category: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(Text, server_default=text("'normal'"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'open'"))
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "type IN ('refund_decided', 'refund_paid_out', 'payment_confirmed', 'payment_rejected', 'ticket_updated')",
            name="type_valid",
        ),
        Index("ix_notifications_user_id_read_at", "user_id", "read_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StatusEvent(Base):
    """Một bảng sự kiện cho đơn/thanh toán/hoàn tiền/phiếu. Chỉ INSERT: trigger chặn UPDATE/DELETE."""

    __tablename__ = "status_events"
    __table_args__ = (
        CheckConstraint("entity_type IN ('order', 'payment', 'refund', 'ticket')", name="entity_type_valid"),
        Index("ix_status_events_entity", "entity_type", "entity_id", "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str] = mapped_column(Text)  # id đơn là text, các thực thể khác là uuid dạng chuỗi
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))  # NULL = hệ thống
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
