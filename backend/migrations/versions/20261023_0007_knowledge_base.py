"""knowledge base: kb_documents, kb_chunks (vector + tsvector)

Embedding không nằm trong cổng migrate: cột `embedding` cho phép NULL và được điền bởi `python -m app.kb.reindex`.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "kb_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("lang", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("lang IN ('vi', 'en')", name=op.f("ck_kb_documents_lang_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kb_documents")),
        sa.UniqueConstraint("slug", "lang", name=op.f("uq_kb_documents_slug_lang")),
    )
    op.create_table(
        "kb_chunks",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column(
            "tsv", postgresql.TSVECTOR(), sa.Computed("to_tsvector('simple', immutable_unaccent(content))", persisted=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["kb_documents.id"], name=op.f("fk_kb_chunks_document_id_kb_documents"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("document_id", "idx", name=op.f("pk_kb_chunks")),
    )
    op.execute("CREATE INDEX ix_kb_chunks_embedding_hnsw ON kb_chunks USING hnsw (embedding vector_cosine_ops)")
    op.execute("CREATE INDEX ix_kb_chunks_tsv ON kb_chunks USING gin (tsv)")

    # app chỉ đọc KB (reindex chạy bằng migrator); mcp đọc để trích dẫn chính sách
    op.execute("GRANT SELECT ON kb_documents, kb_chunks TO shopbot_mcp")


def downgrade() -> None:
    op.drop_table("kb_chunks")
    op.drop_table("kb_documents")
