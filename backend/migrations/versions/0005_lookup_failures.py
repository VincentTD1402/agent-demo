"""lookup_failures: đếm lần tra cứu đơn sai (mã đơn hoặc SĐT) để chặn dò tìm

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-28
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # key dạng 'code:SM000100' hoặc 'phone:0900000001'; mỗi lần sai ghi một dòng, đếm theo cửa sổ thời gian
    op.execute(
        """
        CREATE TABLE lookup_failures (
            id         bigserial PRIMARY KEY,
            key        text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX lookup_failures_key_idx ON lookup_failures (key, created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lookup_failures")
