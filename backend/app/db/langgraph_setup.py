"""Tạo bảng của LangGraph (checkpoint + store). Chạy ở bước bootstrap bằng role migrator, không phải lúc API chạy."""
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore

from app.db.event_loop import run_async

# Alembic không quản lý các bảng này (xem include_object trong migrations/env.py)
LANGGRAPH_TABLES = frozenset(
    {
        "checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations",
        "store", "store_vectors", "store_migrations", "vector_migrations",
    }
)


async def _no_embed(texts: list[str]) -> list[list[float]]:
    raise RuntimeError("setup() chỉ tạo bảng, không được tính embedding")


async def _setup(dsn: str, embedding_dims: int) -> None:
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        await saver.setup()
    index = {"dims": embedding_dims, "embed": _no_embed, "fields": ["text"]}
    async with AsyncPostgresStore.from_conn_string(dsn, index=index) as store:
        await store.setup()


def setup_langgraph_tables(dsn: str, embedding_dims: int) -> None:
    run_async(_setup(dsn, embedding_dims))
