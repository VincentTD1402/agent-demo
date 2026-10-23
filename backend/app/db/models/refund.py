"""Yêu cầu hoàn tiền. Mỗi đơn có tối đa một yêu cầu "sống" của khách (đang chờ, đã duyệt hoặc đã chi trả) và tối đa
một khoản hoàn "sống" do hệ thống tạo khi đơn đã thanh toán bị huỷ."""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, LargeBinary, Text, Uuid, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

LIVE_REFUND_STATUSES = "('pending_staff', 'approved', 'paid_out')"


class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("source IN ('customer_request', 'system_cancel_paid')", name="source_valid"),
        CheckConstraint(
            "status IN ('pending_staff', 'approved', 'rejected', 'paid_out', 'cancelled')", name="status_valid"
        ),
        CheckConstraint("requested_amount_vnd > 0", name="requested_amount_positive"),
        CheckConstraint(
            "approved_amount_vnd IS NULL OR (approved_amount_vnd > 0 AND approved_amount_vnd <= requested_amount_vnd)",
            name="approved_amount_within_request",
        ),
        CheckConstraint(
            "status <> 'paid_out' OR (payout_reference IS NOT NULL AND approved_amount_vnd IS NOT NULL)",
            name="paid_out_has_payout_fields",
        ),
        CheckConstraint(
            "status NOT IN ('approved', 'rejected') OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name="decided_has_decider",
        ),
        # Khoá ngoại ghép: người yêu cầu hoàn tiền phải là chủ đơn
        ForeignKeyConstraint(["order_id", "user_id"], ["orders.id", "orders.user_id"], name="fk_refunds_order_id_orders"),
        # Bị từ chối/huỷ thì gửi lại được; sau paid_out không tạo thêm. Hai nguồn có chỉ mục riêng để hoàn tiền
        # hệ thống không bị chặn bởi yêu cầu đang chờ của khách.
        Index(
            "uq_refunds_live_customer_request_per_order", "order_id", unique=True,
            postgresql_where=text(f"source = 'customer_request' AND status IN {LIVE_REFUND_STATUSES}"),
        ),
        Index(
            "uq_refunds_live_system_cancel_per_order", "order_id", unique=True,
            postgresql_where=text(f"source = 'system_cancel_paid' AND status IN {LIVE_REFUND_STATUSES}"),
        ),
        Index("ix_refunds_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    order_id: Mapped[str] = mapped_column(Text, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(Text)
    requested_amount_vnd: Mapped[int] = mapped_column(BigInteger)
    approved_amount_vnd: Mapped[int | None] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending_staff'"))
    # Theo từng lần gửi (`thread_id:tool_call_id`), không theo đơn
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)
    # Không có khoá ngoại: yêu cầu hoàn tiền phải sống lâu hơn hội thoại (chu kỳ lưu trữ ngắn hơn)
    thread_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # Tài khoản nhận tiền, mã hoá cấp ứng dụng (app.security.payout_encryption); log/trace không chứa giá trị
    payout_info_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    decision_note: Mapped[str | None] = mapped_column(Text)
    payout_reference: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
