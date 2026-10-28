"""Truy xuất đoạn tài liệu: embedding câu hỏi -> pgvector (cosine) -> rerank -> lọc theo điểm."""

from typing import Protocol

from psycopg_pool import ConnectionPool

from app.agent.reranker_client import Reranker
from app.agent.state import RetrievedChunk
from app.embedding_client import Embedder

# Qwen3-Embedding: câu truy vấn cần tiền tố Instruct (tài liệu thì embed nguyên văn lúc nạp)
_QUERY_TEMPLATE = (
    "Instruct: Given a customer question about an electronics store, retrieve relevant policy and product passages\n"
    "Query: {query}"
)


class ChunkSearcher(Protocol):
    def search(self, question: str) -> list[RetrievedChunk]: ...


class PgChunkSearcher:
    def __init__(
        self, pool: ConnectionPool, embedder: Embedder, reranker: Reranker, top_k: int, top_n: int, min_score: float
    ):
        self._pool = pool
        self._embedder = embedder
        self._reranker = reranker
        self._top_k = top_k
        self._top_n = top_n
        self._min_score = min_score

    def search(self, question: str) -> list[RetrievedChunk]:
        """Đồng bộ (gọi mạng + DB); node async chạy hàm này qua asyncio.to_thread."""
        vector = self._embedder.embed([_QUERY_TEMPLATE.format(query=question)])[0]
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT d.source, c.content
                FROM chunks c JOIN documents d ON d.id = c.document_id
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (vector, self._top_k),
            ).fetchall()
        if not rows:
            return []
        scores = self._reranker.score(question, [content for _, content in rows])
        ranked = sorted(
            (RetrievedChunk(source=source, content=content, score=score) for (source, content), score in zip(rows, scores)),
            key=lambda chunk: chunk["score"],
            reverse=True,
        )
        return [chunk for chunk in ranked[: self._top_n] if chunk["score"] >= self._min_score]
