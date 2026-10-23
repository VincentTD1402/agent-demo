"""Reindex: embed chunk KB + sản phẩm, idempotent theo content_hash, không gọi host embedding thật (client giả đếm lời gọi).

Client giả chỉ thay endpoint HTTP bên ngoài; toàn bộ phần chunking, SQL, upsert, hash chạy trên Postgres thật.
"""
import hashlib
import json
import os

import httpx
import psycopg
import pytest

from app.kb.embedding_client import EmbeddingError, HttpEmbeddingClient
from app.kb.reindex import reindex
from app.settings.migrate import MigrateSettings

DIMS = 1024


class FakeEmbedder:
    """Vector tất định theo nội dung; ghi lại số lần gọi và các văn bản đã được gửi."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    @property
    def texts(self) -> list[str]:
        return [t for call in self.calls for t in call]

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._vector(t) for t in texts]

    @staticmethod
    def _vector(text: str) -> list[float]:
        seed = hashlib.sha256(text.encode()).digest()
        return [seed[i % len(seed)] / 255 - 0.5 for i in range(DIMS)]


def _connect(settings):
    return psycopg.connect(settings.migrator_database_url, autocommit=True)


def test_reindex_embeds_everything_then_is_idempotent(bootstrapped_db):
    client = FakeEmbedder()
    with _connect(bootstrapped_db) as conn:
        first = reindex(conn, client, "model-a")
        chunk_total = conn.execute("SELECT count(*) FROM kb_chunks").fetchone()[0]
        assert chunk_total >= 10, "mỗi tài liệu có ít nhất một chunk"
        assert conn.execute("SELECT count(*) FROM kb_chunks WHERE embedding IS NULL").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM product_embeddings").fetchone()[0] == first.products_embedded > 0
        assert first.kb_chunks_embedded == chunk_total
        calls_after_first = len(client.calls)

        second = reindex(conn, client, "model-a")
        assert len(client.calls) == calls_after_first, "chạy lại không được gọi endpoint embedding"
        assert second.kb_chunks_embedded == 0 and second.products_embedded == 0 and second.unchanged > 0
        assert conn.execute("SELECT count(*) FROM kb_chunks").fetchone()[0] == chunk_total


def test_reindex_only_reembeds_changed_content_and_model(bootstrapped_db):
    client = FakeEmbedder()
    with _connect(bootstrapped_db) as conn:
        reindex(conn, client, "model-a")
        client.calls.clear()

        conn.execute("UPDATE kb_documents SET body = body || E'\\n\\nĐoạn bổ sung mới.' WHERE slug = 'shipping' AND lang = 'vi'")
        conn.execute("UPDATE products SET description = description || ' Bản mới.' WHERE slug = 'iphone-16-128gb'")
        stats = reindex(conn, client, "model-a")
        assert stats.kb_chunks_embedded == 1 and stats.products_embedded == 1
        assert len(client.texts) == 2 and any("Đoạn bổ sung mới." in t for t in client.texts)

        client.calls.clear()
        stats = reindex(conn, client, "model-b")  # đổi model: mọi vector phải tính lại
        assert stats.kb_chunks_embedded > 1 and stats.products_embedded > 1
        assert conn.execute("SELECT DISTINCT model FROM product_embeddings").fetchall() == [("model-b",)]


def test_reindex_shrinks_chunks_and_skips_inactive_products(bootstrapped_db):
    client = FakeEmbedder()
    with _connect(bootstrapped_db) as conn:
        conn.execute("UPDATE products SET is_active = false WHERE slug = 'iphone-16-128gb'")
        stats = reindex(conn, client, "model-a")
        assert stats.products_embedded == conn.execute("SELECT count(*) FROM products WHERE is_active").fetchone()[0]
        long_body = "\n\n".join(f"Đoạn dài số {i}. " + "nội dung " * 100 for i in range(6))
        conn.execute("UPDATE kb_documents SET body = %s WHERE slug = 'warranty' AND lang = 'vi'", (long_body,))
        reindex(conn, client, "model-a")
        many = conn.execute(
            "SELECT count(*) FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id WHERE d.slug = 'warranty' AND d.lang = 'vi'"
        ).fetchone()[0]
        assert many > 1
        conn.execute("UPDATE kb_documents SET body = 'Ngắn.' WHERE slug = 'warranty' AND lang = 'vi'")
        reindex(conn, client, "model-a")
        left = conn.execute(
            "SELECT count(*) FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id WHERE d.slug = 'warranty' AND d.lang = 'vi'"
        ).fetchone()[0]
        assert left == 1, "chunk thừa phải bị xoá khi tài liệu ngắn lại"


def test_reindex_failure_keeps_progress_and_rerun_finishes(bootstrapped_db):
    class FlakyEmbedder(FakeEmbedder):
        failed = False

        def embed(self, texts):
            if len(self.calls) == 1 and not self.failed:  # lô thứ hai (sản phẩm) lỗi đúng một lần
                self.failed = True
                raise EmbeddingError("host treo")
            return super().embed(texts)

    client = FlakyEmbedder()
    with _connect(bootstrapped_db) as conn:
        with pytest.raises(EmbeddingError):
            reindex(conn, client, "model-a")
        done = conn.execute("SELECT count(*) FROM kb_chunks WHERE embedding IS NOT NULL").fetchone()[0]
        assert done > 0, "lô đầu đã xong được giữ lại"
        reindex(conn, client, "model-a")
        assert conn.execute("SELECT count(*) FROM kb_chunks WHERE embedding IS NULL").fetchone()[0] == 0


def _http_client(handler, **kwargs) -> HttpEmbeddingClient:
    return HttpEmbeddingClient(
        "http://embed.test/v1/", "m", kwargs.pop("dims", 3), 5.0, transport=httpx.MockTransport(handler), **kwargs
    )


def test_http_client_posts_openai_shape_and_orders_by_index():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers.get("authorization"), json.loads(request.content)
        data = [{"index": 1, "embedding": [0, 1, 0]}, {"index": 0, "embedding": [1, 0, 0]}]
        return httpx.Response(200, json={"data": data})

    vectors = _http_client(handler, api_key="secret-key").embed(["a", "b"])
    assert vectors == [[1, 0, 0], [0, 1, 0]]
    assert seen["url"] == "http://embed.test/v1/embeddings" and seen["body"] == {"model": "m", "input": ["a", "b"]}
    assert seen["auth"] == "Bearer secret-key"


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500, json={"error": "boom"}),
        lambda r: httpx.Response(200, text="not json"),
        lambda r: httpx.Response(200, json={"unexpected": []}),
        lambda r: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 2]}]}),  # sai số chiều
        lambda r: httpx.Response(200, json={"data": []}),  # thiếu vector
    ],
    ids=["http-500", "not-json", "missing-data", "wrong-dims", "missing-vectors"],
)
def test_http_client_raises_clear_error_on_bad_responses(handler):
    with pytest.raises(EmbeddingError):
        _http_client(handler).embed(["a"])


def test_http_client_timeout_becomes_embedding_error_without_leaking_key():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(EmbeddingError) as exc:
        _http_client(handler, api_key="secret-key").embed(["a"])
    assert "secret-key" not in str(exc.value) and "ReadTimeout" in str(exc.value)


@pytest.mark.skipif(
    os.environ.get("RUN_EMBEDDING_INTEGRATION") != "1", reason="đặt RUN_EMBEDDING_INTEGRATION=1 để gọi endpoint embedding thật"
)
def test_real_embedding_endpoint_returns_configured_dimensions():
    """Tích hợp tuỳ chọn, mặc định bỏ qua: cần EMBEDDING_BASE_URL/EMBEDDING_MODEL trong môi trường (không đọc file .env)."""
    s = MigrateSettings(_env_file=None, bootstrap_database_url="postgresql://x@localhost/x",
                        migrator_db_password="MigratorTestPass1", app_db_password="AppTestPass123456",
                        mcp_db_password="McpTestPass123456")
    assert s.embedding_base_url and s.embedding_model, "thiếu EMBEDDING_BASE_URL/EMBEDDING_MODEL"
    api_key = s.embedding_api_key.get_secret_value() if s.embedding_api_key else None
    client = HttpEmbeddingClient(s.embedding_base_url, s.embedding_model, s.embedding_dims, s.embedding_timeout_s, api_key)
    try:
        vectors = client.embed(["hoàn tiền trong bao lâu", "refund window"])
    finally:
        client.close()
    assert len(vectors) == 2 and all(len(v) == s.embedding_dims for v in vectors)
