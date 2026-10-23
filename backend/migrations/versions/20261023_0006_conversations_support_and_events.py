"""conversations, tool_audit_log, support_tickets, notifications, status_events (+ trigger chỉ-thêm)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY_TABLES = ("status_events", "tool_audit_log")

# Chặn mọi UPDATE/DELETE, kể cả chủ bảng: bảng sự kiện/audit là chứng cứ nên chỉ được thêm.
# Dọn theo hạn lưu trữ phải làm có chủ đích (partition/TRUNCATE do migrator), không bằng DELETE thường.
APPEND_ONLY_GUARD = """
CREATE FUNCTION forbid_row_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
END $$
"""


def _ts(name: str, nullable: bool = True, default_now: bool = False) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()") if default_now else None, nullable=nullable
    )


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("thread_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'open'"), nullable=False),
        _ts("running_since"),
        _ts("last_message_at", nullable=False, default_now=True),
        _ts("deleted_at"),
        _ts("created_at", nullable=False, default_now=True),
        sa.CheckConstraint("status IN ('open', 'handoff', 'closed')", name=op.f("ck_conversations_status_valid")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_conversations_user_id_users")),
        sa.PrimaryKeyConstraint("thread_id", name=op.f("pk_conversations")),
    )
    op.create_index(
        "ix_conversations_user_id_last_message_at", "conversations", ["user_id", "last_message_at"]
    )

    op.create_table(
        "tool_audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("args", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        _ts("at", nullable=False, default_now=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_tool_audit_log_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_audit_log")),
    )
    op.create_index("ix_tool_audit_log_thread_id", "tool_audit_log", ["thread_id"])

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=True),
        sa.Column("order_id", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("priority", sa.Text(), server_default=sa.text("'normal'"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'open'"), nullable=False),
        sa.Column("assigned_to", sa.Uuid(), nullable=True),
        _ts("due_at"),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        _ts("created_at", nullable=False, default_now=True),
        _ts("resolved_at"),
        sa.CheckConstraint(
            "category IN ('human_requested', 'complaint_legal', 'exchange_or_address', 'defective',"
            " 'refund_dispute', 'other')",
            name=op.f("ck_support_tickets_category_valid"),
        ),
        sa.CheckConstraint("priority IN ('normal', 'high')", name=op.f("ck_support_tickets_priority_valid")),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved', 'closed')", name=op.f("ck_support_tickets_status_valid")
        ),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], name=op.f("fk_support_tickets_assigned_to_users")),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name=op.f("fk_support_tickets_order_id_orders")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_support_tickets_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_tickets")),
    )
    op.create_index(op.f("ix_support_tickets_user_id"), "support_tickets", ["user_id"])
    op.create_index("ix_support_tickets_status_due_at", "support_tickets", ["status", "due_at"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        _ts("read_at"),
        _ts("created_at", nullable=False, default_now=True),
        sa.CheckConstraint(
            "type IN ('refund_decided', 'refund_paid_out', 'payment_confirmed', 'payment_rejected', 'ticket_updated')",
            name=op.f("ck_notifications_type_valid"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_notifications_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index("ix_notifications_user_id_read_at", "notifications", ["user_id", "read_at"])

    op.create_table(
        "status_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("at", nullable=False, default_now=True),
        sa.CheckConstraint(
            "entity_type IN ('order', 'payment', 'refund', 'ticket')", name=op.f("ck_status_events_entity_type_valid")
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name=op.f("fk_status_events_actor_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_status_events")),
    )
    op.create_index("ix_status_events_entity", "status_events", ["entity_type", "entity_id", "at"])

    op.execute(APPEND_ONLY_GUARD)
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table}"
            " FOR EACH ROW EXECUTE FUNCTION forbid_row_change()"
        )

    # app: SELECT đã có từ default privileges. Bảng sự kiện/audit chỉ INSERT (không UPDATE/DELETE)
    op.execute("GRANT INSERT, UPDATE, DELETE ON conversations TO shopbot_app")
    op.execute("GRANT INSERT, UPDATE ON support_tickets, notifications TO shopbot_app")
    op.execute("GRANT INSERT ON status_events, tool_audit_log TO shopbot_app")
    # Sequence của bảng identity: default privileges đã cấp USAGE cho app; mcp cần để INSERT
    # mcp chỉ ghi cột nội dung của audit/phiếu (không đặt thời điểm, trạng thái, người xử lý); không INSERT
    # status_events/notifications (API ghi); khớp MCP_INSERT_COLUMNS ở app/db/roles.py
    op.execute(
        "GRANT INSERT (thread_id, user_id, tool_name, args, status, latency_ms) ON tool_audit_log TO shopbot_mcp"
    )
    op.execute(
        "GRANT INSERT (user_id, thread_id, order_id, category, summary, priority) ON support_tickets TO shopbot_mcp"
    )
    op.execute("GRANT USAGE ON SEQUENCE tool_audit_log_id_seq TO shopbot_mcp")


def downgrade() -> None:
    op.drop_table("status_events")
    op.drop_table("notifications")
    op.drop_table("support_tickets")
    op.drop_table("tool_audit_log")
    op.drop_table("conversations")
    op.execute("DROP FUNCTION forbid_row_change()")
