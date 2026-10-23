"""Truy vấn tìm kiếm dùng được index trigram / HNSW / GIN trên bảng có dữ liệu.

`enable_seqscan = off` có chủ đích: với vài trăm dòng planner luôn thích quét tuần tự hơn, nên test này chứng minh
index *dùng được* cho đúng biểu thức/toán tử truy vấn (và cho kết quả đúng), không đo hiệu năng ở quy mô thật.
"""
import random

import pytest

from app.settings.migrate import ROLE_MIGRATOR

DIMS = 1024
ROWS = 400


def _vector(rng: random.Random) -> str:
    return "[" + ",".join(f"{rng.uniform(-1, 1):.4f}" for _ in range(DIMS)) + "]"


def _plan(conn, query: str, params=()) -> str:
    conn.execute("SET LOCAL enable_seqscan = off")
    return "\n".join(row[0] for row in conn.execute("EXPLAIN " + query, params).fetchall())


@pytest.fixture
def populated(connect_as):
    conn = connect_as(ROLE_MIGRATOR)
    conn.execute(
        "INSERT INTO products (slug, name, category, brand, price_vnd)"
        " SELECT 'filler-' || g, 'Sản phẩm số ' || g, 'phu-kien', 'Hãng', 1000 + g FROM generate_series(1, %s) g",
        (ROWS,),
    )
    conn.execute(
        "INSERT INTO products (slug, name, category, brand, price_vnd) VALUES ('dt-test', 'Điện thoại thử nghiệm', 'dien-thoai', 'X', 1)"
    )
    rng = random.Random(7)
    ids = [r[0] for r in conn.execute("SELECT id FROM products").fetchall()]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO product_embeddings (product_id, model, embedding, content_hash) VALUES (%s, 'm', %s::vector, 'h')",
            [(pid, _vector(rng)) for pid in ids],
        )
    conn.execute(
        "INSERT INTO kb_documents (slug, lang, title, category, body) VALUES ('t', 'vi', 't', 'refund', 'b') RETURNING id"
    )
    doc_id = conn.execute("SELECT id FROM kb_documents WHERE slug = 't'").fetchone()[0]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO kb_chunks (document_id, idx, content, embedding) VALUES (%s, %s, %s, %s::vector)",
            [(doc_id, i, f"Chính sách hoàn tiền số {i}" if i % 2 else f"Bảo hành số {i}", _vector(rng)) for i in range(ROWS)],
        )
    conn.execute("ANALYZE products")
    conn.execute("ANALYZE product_embeddings")
    conn.execute("ANALYZE kb_chunks")
    return conn, rng


def test_name_search_uses_trigram_index_and_ignores_accents(populated):
    conn, _ = populated
    query = "SELECT id, name FROM products WHERE immutable_unaccent(name) ILIKE immutable_unaccent(%s)"
    plan = _plan(conn, query, ("%dien thoai%",))
    assert "ix_products_name_trgm" in plan, plan
    rows = conn.execute(query, ("%dien thoai%",)).fetchall()
    assert [r[1] for r in rows] == ["Điện thoại thử nghiệm"]


def test_product_vector_search_uses_hnsw_cosine_index(populated):
    conn, rng = populated
    query = "SELECT product_id FROM product_embeddings ORDER BY embedding <=> %s::vector LIMIT 5"
    probe = _vector(rng)
    assert "ix_product_embeddings_embedding_hnsw" in _plan(conn, query, (probe,))
    assert len(conn.execute(query, (probe,)).fetchall()) == 5


def test_kb_vector_search_uses_hnsw_and_text_search_uses_gin(populated):
    conn, rng = populated
    vector_query = "SELECT document_id, idx FROM kb_chunks ORDER BY embedding <=> %s::vector LIMIT 3"
    assert "ix_kb_chunks_embedding_hnsw" in _plan(conn, vector_query, (_vector(rng),))
    text_query = "SELECT idx FROM kb_chunks WHERE tsv @@ plainto_tsquery('simple', immutable_unaccent(%s))"
    assert "ix_kb_chunks_tsv" in _plan(conn, text_query, ("hoàn tiền",))
    # bỏ dấu cả hai phía: gõ không dấu vẫn tìm thấy đoạn có dấu
    found = {r[0] for r in conn.execute(text_query, ("hoan tien",)).fetchall()}
    assert found == {i for i in range(ROWS) if i % 2}
