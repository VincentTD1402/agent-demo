"""Lưu tài liệu và các chunk (kèm vector) vào Postgres/pgvector."""

from typing import Protocol

from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from app.settings import Settings


class DocumentStore(Protocol):
    def get_content_hash(self, source: str) -> str | None: ...

    def replace_document(
        self, source: str, language: str | None, content_hash: str, chunks: list[str], vectors: list[list[float]]
    ) -> None: ...

    def delete_document(self, source: str) -> bool: ...


def create_pool(settings: Settings) -> ConnectionPool:
    # open=False: app vẫn khởi động (và /health vẫn chạy) khi DB chưa sẵn sàng; lỗi lộ ra ở request nạp tài liệu
    return ConnectionPool(
        settings.database_dsn,
        min_size=1,
        max_size=settings.postgres_pool_size,
        configure=register_vector,
        open=False,
    )


class PgDocumentStore:
    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    def get_content_hash(self, source: str) -> str | None:
        with self._pool.connection() as conn:
            row = conn.execute("SELECT content_hash FROM documents WHERE source = %s", (source,)).fetchone()
        return row[0] if row else None

    def delete_document(self, source: str) -> bool:
        with self._pool.connection() as conn:  # chunks xoá theo ON DELETE CASCADE
            return conn.execute("DELETE FROM documents WHERE source = %s", (source,)).rowcount > 0

    def replace_document(
        self, source: str, language: str | None, content_hash: str, chunks: list[str], vectors: list[list[float]]
    ) -> None:
        """Ghi đè toàn bộ chunk của `source` trong một transaction (nạp lại file đã đổi không để chunk cũ)."""
        with self._pool.connection() as conn:  # commit khi thoát khối, rollback nếu có lỗi
            # ON CONFLICT DO UPDATE khoá dòng documents -> hai request cùng source được xếp hàng, không đè chunk nhau
            document_id = conn.execute(
                """
                INSERT INTO documents (source, language, content_hash, chunk_count)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (source) DO UPDATE
                    SET language = EXCLUDED.language,
                        content_hash = EXCLUDED.content_hash,
                        chunk_count = EXCLUDED.chunk_count,
                        updated_at = now()
                RETURNING id
                """,
                (source, language, content_hash, len(chunks)),
            ).fetchone()[0]
            conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO chunks (document_id, chunk_index, content, embedding) VALUES (%s, %s, %s, %s)",
                    [(document_id, i, text, vec) for i, (text, vec) in enumerate(zip(chunks, vectors))],
                )
