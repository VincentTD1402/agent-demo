"""Lắp ráp agent lúc khởi động: model, reranker, bộ tìm kiếm, checkpointer Postgres và đồ thị."""

import asyncio
import logging
from dataclasses import dataclass, field

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, ConnectionPool

from app.agent.graph import build_agent_graph
from app.agent.llm import build_answer_llm, build_fast_llm
from app.agent.nodes import AgentNodes, SummaryPolicy
from app.agent.reranker_client import HttpReranker
from app.agent.retrieval import PgChunkSearcher
from app.embedding_client import Embedder
from app.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class AgentRuntime:
    graph: CompiledStateGraph
    reranker: HttpReranker
    _checkpointer: AsyncPostgresSaver
    _pool: AsyncConnectionPool
    _ready: bool = False
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def ensure_ready(self) -> None:
        """Tạo bảng checkpoint (idempotent) ở lần dùng đầu; app vẫn khởi động được khi DB chưa sẵn sàng."""
        if self._ready:
            return
        async with self._lock:
            if not self._ready:
                await self._checkpointer.setup()
                self._ready = True

    async def delete_thread(self, thread_id: str) -> None:
        await self.ensure_ready()
        await self._checkpointer.adelete_thread(thread_id)

    async def close(self) -> None:
        self.reranker.close()
        await self._pool.close()


async def create_agent(settings: Settings, sync_pool: ConnectionPool, embedder: Embedder) -> AgentRuntime:
    reranker = HttpReranker(settings.reranker_api_url, settings.reranker_model_name, settings.reranker_timeout_s)
    searcher = PgChunkSearcher(
        sync_pool, embedder, reranker, settings.rag_top_k, settings.rag_top_n, settings.rag_min_score
    )
    nodes = AgentNodes(
        build_fast_llm(settings),
        build_answer_llm(settings),
        searcher,
        SummaryPolicy(settings.rag_summarize_after, settings.rag_keep_messages),
    )
    # Checkpointer của LangGraph yêu cầu autocommit, không prepared statement và hàng dạng dict
    pool = AsyncConnectionPool(
        settings.database_dsn,
        max_size=settings.postgres_pool_size,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=False,
    )
    await pool.open(wait=False)
    checkpointer = AsyncPostgresSaver(pool)
    runtime = AgentRuntime(build_agent_graph(nodes, checkpointer), reranker, checkpointer, pool)
    try:
        await runtime.ensure_ready()
    except Exception:
        logger.warning("Chưa tạo được bảng checkpoint (DB chưa sẵn sàng?); sẽ thử lại ở request chat đầu tiên")
    return runtime
