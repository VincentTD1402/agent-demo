"""Reindex: khoá không chờ (chỉ một lần chạy), ngân sách thời gian tổng, xoá embedding của sản phẩm đã ẩn."""
import time

import psycopg
import pytest

from app.db.locks import try_reindex_lock
from app.kb import reindex as reindex_module
from app.kb.reindex import ReindexBudgetExceeded, reindex
from tests.db.test_kb_reindex import FakeEmbedder, _connect


class ClosableEmbedder(FakeEmbedder):
    def close(self) -> None:
        pass


class SlowEmbedder(ClosableEmbedder):
    def embed(self, texts):
        time.sleep(0.3)
        return super().embed(texts)


@pytest.fixture
def run_main(bootstrapped_db, monkeypatch):
    """Gọi `main()` của reindex trên DB tạm với client giả; trả (exit_code, client)."""
    settings = bootstrapped_db.model_copy(update={"embedding_base_url": "http://embed.test/v1", "embedding_model": "m"})
    monkeypatch.setattr(reindex_module, "MigrateSettings", lambda: settings)

    def run(client, *argv: str) -> int:
        monkeypatch.setattr(reindex_module, "HttpEmbeddingClient", lambda *a, **k: client)
        return reindex_module.main(list(argv))

    return run


def test_inactive_products_lose_their_embedding(bootstrapped_db):
    client = FakeEmbedder()
    with _connect(bootstrapped_db) as conn:
        reindex(conn, client, "model-a")
        total = conn.execute("SELECT count(*) FROM product_embeddings").fetchone()[0]
        conn.execute("UPDATE products SET is_active = false WHERE slug = 'iphone-16-128gb'")
        stats = reindex(conn, client, "model-a")
        assert stats.stale_product_embeddings_removed == 1
        assert conn.execute("SELECT count(*) FROM product_embeddings").fetchone()[0] == total - 1


def test_expired_budget_stops_before_calling_the_endpoint(bootstrapped_db):
    client = FakeEmbedder()
    with _connect(bootstrapped_db) as conn:
        with pytest.raises(ReindexBudgetExceeded):
            reindex(conn, client, "model-a", deadline=time.monotonic() - 1)
    assert client.calls == []


def test_budget_expiring_mid_run_keeps_finished_batches_and_rerun_completes(bootstrapped_db):
    client = SlowEmbedder()
    with _connect(bootstrapped_db) as conn:
        with pytest.raises(ReindexBudgetExceeded):
            reindex(conn, client, "model-a", deadline=time.monotonic() + 0.1)
        assert len(client.calls) >= 1
        done = conn.execute("SELECT count(*) FROM kb_chunks WHERE embedding IS NOT NULL").fetchone()[0]
        assert done > 0
        reindex(conn, FakeEmbedder(), "model-a")
        assert conn.execute("SELECT count(*) FROM kb_chunks WHERE embedding IS NULL").fetchone()[0] == 0


def test_second_run_exits_cleanly_while_another_holds_the_lock(bootstrapped_db, run_main):
    client = ClosableEmbedder()
    with _connect(bootstrapped_db) as holder:
        assert try_reindex_lock(holder) is True
        assert run_main(client) == 0
        assert client.calls == [], "lần chạy thứ hai không được gọi endpoint khi lần đầu còn chạy"
    assert run_main(client) == 0
    assert client.calls, "khoá được nhả khi kết nối đóng nên lần sau chạy thật"


def test_cli_budget_flag_returns_dedicated_exit_code(run_main):
    assert run_main(SlowEmbedder(), "--max-seconds", "0.05") == 3


def test_cli_rejects_non_positive_budget(run_main):
    with pytest.raises(SystemExit):
        run_main(ClosableEmbedder(), "--max-seconds", "0")


def test_lock_is_per_connection_and_not_blocking(bootstrapped_db):
    with _connect(bootstrapped_db) as a, _connect(bootstrapped_db) as b:
        assert try_reindex_lock(a) is True
        assert try_reindex_lock(b) is False
    with psycopg.connect(bootstrapped_db.migrator_database_url) as c:
        assert try_reindex_lock(c) is True
