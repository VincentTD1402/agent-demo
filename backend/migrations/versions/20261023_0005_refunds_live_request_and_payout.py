"""refunds: khoá chính uuid, nguồn, trạng thái duyệt, thông tin nhận tiền mã hoá, một yêu cầu "sống" mỗi đơn

Biến đổi bảng `refunds` của 0001 tại chỗ (khoá chính từ order_id sang id uuid). Dữ liệu hoàn tiền cũ chỉ là
dữ liệu mẫu và thiếu user_id/idempotency_key nên bị xoá; chạy được trên DB đã seed lẫn DB trống. Có dòng thì
revision từ chối chạy trừ khi `alembic -x allow_destroy_legacy_orders=true`; downgrade cũng vậy.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.legacy_order_guard import require_destroy_allowed

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LIVE_STATUSES = "('pending_staff', 'approved', 'paid_out')"
# mcp chỉ ghi các cột công cụ issue_refund đặt: status luôn lấy DEFAULT 'pending_staff' (không có quyền chọn
# 'paid_out'), không tự đặt số tiền duyệt, người duyệt hay thông tin chi trả; khớp MCP_REFUND_INSERT_COLUMNS ở roles.py
MCP_REFUND_INSERT_COLUMNS = "order_id, user_id, source, requested_amount_vnd, reason, idempotency_key, thread_id"

# mcp đọc được mọi cột trừ payout_info_enc (cấp theo cột); phải khớp MCP_REFUND_COLUMNS trong app/db/roles.py
MCP_REFUND_COLUMNS = (
    "id, order_id, user_id, source, requested_amount_vnd, approved_amount_vnd, reason, status, idempotency_key,"
    " thread_id, decided_by, decision_note, payout_reference, created_at, decided_at, paid_out_at"
)


def upgrade() -> None:
    require_destroy_allowed(op.get_bind(), ("refunds",), "upgrade 0005")
    op.execute("DELETE FROM refunds")
    op.drop_constraint(op.f("pk_refunds"), "refunds", type_="primary")
    op.alter_column("refunds", "amount_vnd", new_column_name="requested_amount_vnd")
    op.execute("ALTER TABLE refunds RENAME CONSTRAINT ck_refunds_amount_positive TO ck_refunds_requested_amount_positive")
    op.add_column(
        "refunds", sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)
    )
    op.create_primary_key(op.f("pk_refunds"), "refunds", ["id"])
    op.add_column("refunds", sa.Column("user_id", sa.Uuid(), nullable=False))
    op.add_column("refunds", sa.Column("source", sa.Text(), nullable=False))
    op.add_column("refunds", sa.Column("approved_amount_vnd", sa.BigInteger(), nullable=True))
    op.add_column(
        "refunds", sa.Column("status", sa.Text(), server_default=sa.text("'pending_staff'"), nullable=False)
    )
    op.add_column("refunds", sa.Column("idempotency_key", sa.Text(), nullable=False))
    op.add_column("refunds", sa.Column("thread_id", sa.Uuid(), nullable=True))
    op.add_column("refunds", sa.Column("payout_info_enc", sa.LargeBinary(), nullable=True))
    op.add_column("refunds", sa.Column("decided_by", sa.Uuid(), nullable=True))
    op.add_column("refunds", sa.Column("decision_note", sa.Text(), nullable=True))
    op.add_column("refunds", sa.Column("payout_reference", sa.Text(), nullable=True))
    op.add_column("refunds", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("refunds", sa.Column("paid_out_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(op.f("fk_refunds_user_id_users"), "refunds", "users", ["user_id"], ["id"])
    # Khoá ngoại ghép thay khoá (order_id) đơn của 0001: người yêu cầu hoàn tiền phải là chủ đơn
    op.drop_constraint(op.f("fk_refunds_order_id_orders"), "refunds", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_refunds_order_id_orders"), "refunds", "orders", ["order_id", "user_id"], ["id", "user_id"]
    )
    op.create_foreign_key(op.f("fk_refunds_decided_by_users"), "refunds", "users", ["decided_by"], ["id"])
    op.create_unique_constraint(op.f("uq_refunds_idempotency_key"), "refunds", ["idempotency_key"])
    op.execute(
        "ALTER TABLE refunds ADD CONSTRAINT ck_refunds_source_valid"
        " CHECK (source IN ('customer_request', 'system_cancel_paid'))"
    )
    op.execute(
        "ALTER TABLE refunds ADD CONSTRAINT ck_refunds_status_valid"
        " CHECK (status IN ('pending_staff', 'approved', 'rejected', 'paid_out', 'cancelled'))"
    )
    op.execute(
        "ALTER TABLE refunds ADD CONSTRAINT ck_refunds_approved_amount_within_request CHECK"
        " (approved_amount_vnd IS NULL OR (approved_amount_vnd > 0 AND approved_amount_vnd <= requested_amount_vnd))"
    )
    # Mỗi đơn tối đa một yêu cầu sống; bị từ chối/huỷ thì gửi lại được, sau paid_out không tạo thêm
    op.execute(
        "ALTER TABLE refunds ADD CONSTRAINT ck_refunds_paid_out_has_payout_fields CHECK"
        " (status <> 'paid_out' OR (payout_reference IS NOT NULL AND approved_amount_vnd IS NOT NULL))"
    )
    op.execute(
        "ALTER TABLE refunds ADD CONSTRAINT ck_refunds_decided_has_decider CHECK"
        " (status NOT IN ('approved', 'rejected') OR (decided_by IS NOT NULL AND decided_at IS NOT NULL))"
    )
    # Mỗi đơn tối đa một yêu cầu "sống" của khách; bị từ chối/huỷ thì gửi lại được, sau paid_out không tạo thêm.
    # Hoàn tiền do hệ thống (đơn đã trả tiền bị huỷ) có chỉ mục riêng nên không đụng yêu cầu của khách.
    for name, source in (("customer_request", "customer_request"), ("system_cancel", "system_cancel_paid")):
        op.execute(
            f"CREATE UNIQUE INDEX uq_refunds_live_{name}_per_order ON refunds (order_id)"
            f" WHERE source = '{source}' AND status IN {LIVE_STATUSES}"
        )
    op.create_index(op.f("ix_refunds_order_id"), "refunds", ["order_id"])
    op.create_index(op.f("ix_refunds_user_id"), "refunds", ["user_id"])
    op.create_index("ix_refunds_status_created_at", "refunds", ["status", "created_at"])

    op.execute("GRANT INSERT, UPDATE ON refunds TO shopbot_app")
    op.execute(f"GRANT SELECT ({MCP_REFUND_COLUMNS}) ON refunds TO shopbot_mcp")
    op.execute(f"GRANT INSERT ({MCP_REFUND_INSERT_COLUMNS}) ON refunds TO shopbot_mcp")


def downgrade() -> None:
    require_destroy_allowed(op.get_bind(), ("refunds",), "downgrade 0005")
    op.execute("REVOKE ALL ON refunds FROM shopbot_mcp")
    op.execute("REVOKE INSERT, UPDATE ON refunds FROM shopbot_app")
    op.execute("DELETE FROM refunds")
    op.drop_index("ix_refunds_status_created_at", table_name="refunds")
    op.drop_index(op.f("ix_refunds_user_id"), table_name="refunds")
    op.drop_index(op.f("ix_refunds_order_id"), table_name="refunds")
    op.execute("DROP INDEX uq_refunds_live_system_cancel_per_order")
    op.execute("DROP INDEX uq_refunds_live_customer_request_per_order")
    for name in (
        "decided_has_decider", "paid_out_has_payout_fields", "approved_amount_within_request", "status_valid",
        "source_valid",
    ):
        op.execute(f"ALTER TABLE refunds DROP CONSTRAINT ck_refunds_{name}")
    op.drop_constraint(op.f("uq_refunds_idempotency_key"), "refunds", type_="unique")
    op.drop_constraint(op.f("fk_refunds_decided_by_users"), "refunds", type_="foreignkey")
    op.drop_constraint(op.f("fk_refunds_order_id_orders"), "refunds", type_="foreignkey")
    op.drop_constraint(op.f("fk_refunds_user_id_users"), "refunds", type_="foreignkey")
    for name in (
        "paid_out_at", "decided_at", "payout_reference", "decision_note", "decided_by", "payout_info_enc",
        "thread_id", "idempotency_key", "status", "approved_amount_vnd", "source", "user_id",
    ):
        op.drop_column("refunds", name)
    op.drop_constraint(op.f("pk_refunds"), "refunds", type_="primary")
    op.drop_column("refunds", "id")
    op.execute("ALTER TABLE refunds RENAME CONSTRAINT ck_refunds_requested_amount_positive TO ck_refunds_amount_positive")
    op.alter_column("refunds", "requested_amount_vnd", new_column_name="amount_vnd")
    op.create_primary_key(op.f("pk_refunds"), "refunds", ["order_id"])
    op.create_foreign_key(op.f("fk_refunds_order_id_orders"), "refunds", "orders", ["order_id"], ["id"])
