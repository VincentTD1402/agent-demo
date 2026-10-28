"""documents + chunks (vector 1024 chiều, chỉ mục HNSW cosine)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # source: khoá tự nhiên của tài liệu (tên file khi upload, đường dẫn tương đối khi quét folder);
    # nạp lại cùng source thì thay toàn bộ chunk. content_hash (gồm cả language) để bỏ qua file không đổi.
    op.execute(
        """
        CREATE TABLE documents (
            id           bigserial PRIMARY KEY,
            source       text NOT NULL UNIQUE,
            language     text CHECK (language IN ('vi', 'ko')),
            content_hash char(64) NOT NULL,
            chunk_count  integer NOT NULL,
            created_at   timestamptz NOT NULL DEFAULT now(),
            updated_at   timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE chunks (
            id          bigserial PRIMARY KEY,
            document_id bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index integer NOT NULL,
            content     text NOT NULL,
            embedding   vector(1024) NOT NULL,
            UNIQUE (document_id, chunk_index)
        )
        """
    )
    op.execute("CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS documents")
