"""Lắp ráp agent: model, reranker, bộ tìm kiếm, checkpointer Postgres, tool MCP và đồ thị.

Đồ thị được dựng lười ở request chat đầu tiên: app (và /health) vẫn khởi động được khi DB hoặc MCP server chưa sẵn sàng.
Nếu MCP server chưa lên, agent chạy tạm không có nhánh shop (hỏi mua hàng sẽ đi nhánh RAG) và thử nạp tool lại sau
`_TOOLS_RETRY_SECONDS`; khi nạp được thì dựng lại đồ thị có nhánh shop.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

from langchain_core.tools import BaseTool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, ConnectionPool

from app.agent.graph import build_agent_graph
from app.agent.llm import build_answer_llm, build_fast_llm
from app.agent.nodes import AgentNodes, SummaryPolicy
from app.agent.reranker_client import HttpReranker
from app.agent.retrieval import PgChunkSearcher
from app.agent.shop_tools import load_shop_tools
from app.embedding_client import Embedder
from app.settings import Settings

logger = logging.getLogger(__name__)
_TOOLS_RETRY_SECONDS = 30.0


@dataclass
class AgentRuntime:
    settings: Settings
    reranker: HttpReranker
    searcher: PgChunkSearcher
    _checkpointer: AsyncPostgresSaver
    _pool: AsyncConnectionPool
    _ready: bool = False
    _graph: CompiledStateGraph | None = None
    _has_tools: bool = False
    _next_tools_attempt: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def ensure_ready(self) -> None:
        """Tạo bảng checkpoint (idempotent) ở lần dùng đầu; chạy lại được nếu lần trước DB chưa sẵn sàng."""
        if self._ready:
            return
        async with self._lock:
            if not self._ready:
                await self._checkpointer.setup()
                self._ready = True

    async def get_graph(self) -> CompiledStateGraph:
        await self.ensure_ready()
        async with self._lock:
            wants_tools = bool(self.settings.mcp_api_key) and not self._has_tools
            if self._graph is None or (wants_tools and time.monotonic() >= self._next_tools_attempt):
                tools = await self._try_load_tools() if wants_tools else []
                self._graph = self._build(tools)
                self._has_tools = bool(tools)
            return self._graph

    async def _try_load_tools(self) -> list[BaseTool]:
        try:
            return await load_shop_tools(self.settings)
        except Exception:
            logger.warning("Chưa nạp được tool từ MCP server; chạy không có nhánh shop, thử lại sau %.0fs", _TOOLS_RETRY_SECONDS)
            self._next_tools_attempt = time.monotonic() + _TOOLS_RETRY_SECONDS
            return []

    def _build(self, tools: list[BaseTool]) -> CompiledStateGraph:
        s = self.settings
        answer_llm = build_answer_llm(s)
        nodes = AgentNodes(
            build_fast_llm(s),
            answer_llm,
            self.searcher,
            SummaryPolicy(s.rag_summarize_after, s.rag_keep_messages),
            shop_llm=answer_llm.bind_tools(tools) if tools else None,
        )
        return build_agent_graph(nodes, self._checkpointer, tools)

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
    # Checkpointer của LangGraph yêu cầu autocommit, không prepared statement và hàng dạng dict
    pool = AsyncConnectionPool(
        settings.database_dsn,
        max_size=settings.postgres_pool_size,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=False,
    )
    await pool.open(wait=False)
    runtime = AgentRuntime(settings, reranker, searcher, AsyncPostgresSaver(pool), pool)
    try:
        await runtime.get_graph()
    except Exception:
        logger.warning("Chưa dựng được agent lúc khởi động (DB chưa sẵn sàng?); sẽ thử lại ở request chat đầu tiên")
    return runtime
