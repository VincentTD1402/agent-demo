"""Tính embedding cho chunk KB và sản phẩm: `python -m app.kb.reindex` (chạy riêng, không thuộc cổng migrate).

Idempotent nhờ content_hash = sha256(model + nội dung): chạy lại không gọi endpoint cho dòng không đổi, đổi model
hoặc nội dung thì chỉ dòng đó được embed lại. Lỗi giữa chừng giữ phần đã xong; chạy lại sẽ làm tiếp.
Cần quyền ghi kb_chunks/product_embeddings nên dùng role migrator.

Chỉ một lần chạy tại một thời điểm (khoá advisory không chờ: có lần khác đang chạy thì thoát mã 0 ngay).
`--max-seconds` giới hạn tổng thời gian: hết hạn thì dừng sau lô hiện tại (mã 3), phần đã xong được giữ.
Embedding của sản phẩm không còn hoạt động bị xoá.
"""
import argparse
import hashlib
import logging
import sys
import time
from dataclasses import dataclass

import psycopg

from app.db.locks import try_reindex_lock
from app.kb.chunking import chunk_text
from app.kb.embedding_client import EmbeddingClient, EmbeddingError, HttpEmbeddingClient
from app.settings.migrate import MigrateSettings

log = logging.getLogger("kb.reindex")
BATCH_SIZE = 16


class ReindexBudgetExceeded(Exception):
    """Hết ngân sách thời gian tổng (--max-seconds)."""


def _check_budget(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise ReindexBudgetExceeded


@dataclass
class ReindexStats:
    kb_chunks_embedded: int = 0
    products_embedded: int = 0
    stale_product_embeddings_removed: int = 0
    unchanged: int = 0


def content_hash(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def _product_text(row: tuple) -> str:
    name, brand, category, description, specs = row
    spec_lines = "\n".join(f"{k}: {v}" for k, v in sorted(specs.items()))
    return f"{name}\n{brand} - {category}\n{description}\n{spec_lines}".strip()


def _sync_kb_chunks(conn: psycopg.Connection) -> None:
    """Đưa bảng kb_chunks khớp với body hiện tại của tài liệu (chunk đổi nội dung bị xoá embedding)."""
    for doc_id, body in conn.execute("SELECT id, body FROM kb_documents ORDER BY id").fetchall():
        chunks = chunk_text(body)
        for idx, content in enumerate(chunks):
            conn.execute(
                """INSERT INTO kb_chunks (document_id, idx, content) VALUES (%s, %s, %s)
                   ON CONFLICT (document_id, idx) DO UPDATE
                   SET content = EXCLUDED.content, content_hash = NULL, embedding = NULL
                   WHERE kb_chunks.content IS DISTINCT FROM EXCLUDED.content""",
                (doc_id, idx, content),
            )
        conn.execute("DELETE FROM kb_chunks WHERE document_id = %s AND idx >= %s", (doc_id, len(chunks)))


def _batches(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _reindex_kb(
    conn: psycopg.Connection, client: EmbeddingClient, model: str, stats: ReindexStats, deadline: float | None
) -> None:
    _sync_kb_chunks(conn)
    rows = conn.execute("SELECT document_id, idx, content, content_hash, embedding IS NULL FROM kb_chunks").fetchall()
    pending = [r for r in rows if r[4] or r[3] != content_hash(model, r[2])]
    stats.unchanged += len(rows) - len(pending)
    for batch in _batches(pending, BATCH_SIZE):
        _check_budget(deadline)
        vectors = client.embed([r[2] for r in batch])
        for (doc_id, idx, content, _, _), vector in zip(batch, vectors, strict=True):
            conn.execute(
                "UPDATE kb_chunks SET embedding = %s::vector, content_hash = %s WHERE document_id = %s AND idx = %s",
                (_vector_literal(vector), content_hash(model, content), doc_id, idx),
            )
        stats.kb_chunks_embedded += len(batch)


def _reindex_products(
    conn: psycopg.Connection, client: EmbeddingClient, model: str, stats: ReindexStats, deadline: float | None
) -> None:
    removed = conn.execute(
        "DELETE FROM product_embeddings WHERE product_id IN (SELECT id FROM products WHERE NOT is_active)"
    )
    stats.stale_product_embeddings_removed = removed.rowcount
    products = conn.execute(
        "SELECT p.id, p.name, p.brand, p.category, p.description, p.specs, e.content_hash"
        " FROM products p LEFT JOIN product_embeddings e ON e.product_id = p.id WHERE p.is_active ORDER BY p.id"
    ).fetchall()
    texts = {r[0]: _product_text(r[1:6]) for r in products}
    pending = [r[0] for r in products if r[6] != content_hash(model, texts[r[0]])]
    stats.unchanged += len(products) - len(pending)
    for batch in _batches(pending, BATCH_SIZE):
        _check_budget(deadline)
        vectors = client.embed([texts[pid] for pid in batch])
        for pid, vector in zip(batch, vectors, strict=True):
            conn.execute(
                """INSERT INTO product_embeddings (product_id, model, embedding, content_hash)
                   VALUES (%s, %s, %s::vector, %s)
                   ON CONFLICT (product_id) DO UPDATE
                   SET model = EXCLUDED.model, embedding = EXCLUDED.embedding,
                       content_hash = EXCLUDED.content_hash, updated_at = now()""",
                (pid, model, _vector_literal(vector), content_hash(model, texts[pid])),
            )
        stats.products_embedded += len(batch)


def reindex(
    conn: psycopg.Connection, client: EmbeddingClient, model: str, deadline: float | None = None
) -> ReindexStats:
    """`conn` phải ở chế độ autocommit để phần đã embed được giữ lại khi một lô sau đó lỗi.
    `deadline` (time.monotonic) hết thì ném ReindexBudgetExceeded giữa hai lô."""
    stats = ReindexStats()
    _reindex_kb(conn, client, model, stats, deadline)
    _reindex_products(conn, client, model, stats, deadline)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tính embedding cho chunk KB và sản phẩm")
    parser.add_argument("--max-seconds", type=float, default=None, help="tổng thời gian tối đa (giây); mặc định không giới hạn")
    args = parser.parse_args(argv)
    if args.max_seconds is not None and args.max_seconds <= 0:
        parser.error("--max-seconds phải > 0")
    deadline = None if args.max_seconds is None else time.monotonic() + args.max_seconds
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = MigrateSettings()  # type: ignore[call-arg]
    if not s.embedding_base_url or not s.embedding_model:
        log.error("Cần đặt EMBEDDING_BASE_URL và EMBEDDING_MODEL để chạy reindex")
        return 2
    api_key = s.embedding_api_key.get_secret_value() if s.embedding_api_key else None
    client = HttpEmbeddingClient(s.embedding_base_url, s.embedding_model, s.embedding_dims, s.embedding_timeout_s, api_key)
    try:
        with psycopg.connect(s.migrator_database_url, autocommit=True) as conn:
            if not try_reindex_lock(conn):
                log.warning("Một lần reindex khác đang chạy: bỏ qua lần này")
                return 0
            stats = reindex(conn, client, s.embedding_model, deadline)
    except ReindexBudgetExceeded:
        log.error("Hết ngân sách %.0fs: dừng sau lô hiện tại, phần đã xong được giữ; chạy lại để làm tiếp", args.max_seconds)
        return 3
    except (EmbeddingError, psycopg.Error) as exc:
        log.error("Reindex thất bại: %s", exc)
        return 1
    finally:
        client.close()
    log.info("Reindex xong: %s", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
