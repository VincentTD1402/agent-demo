"""Khởi tạo tài nguyên dài hạn: Postgres checkpointer + store (pool riêng), công cụ MCP, đồ thị.

Bảng LangGraph do bước bootstrap tạo; ở đây không có DDL nên role `app` đủ quyền.
"""
import asyncio
import logging

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore
from psycopg_pool import AsyncConnectionPool

from app.agent.graph import build_graph
from app.llm import build_chat_model, build_embeddings
from app.settings.api import ApiSettings

log = logging.getLogger(__name__)


async def _load_mcp_tools(url: str, attempts: int = 10):
    client = MultiServerMCPClient({"shopbot": {"transport": "streamable_http", "url": url}})
    for i in range(1, attempts + 1):
        try:
            return await client.get_tools()
        except Exception as exc:
            if i == attempts:
                raise
            log.warning("MCP server chưa sẵn sàng (%s), thử lại %s/%s", exc, i, attempts)
            await asyncio.sleep(2)


async def open_runtime(s: ApiSettings, pool: AsyncConnectionPool):
    """Trả về đồ thị đã compile. `pool` dành riêng cho LangGraph (autocommit, row_factory=dict_row)
    và do caller đóng."""
    index = {"dims": s.embedding_dims, "embed": build_embeddings(s), "fields": ["text"]}
    saver = AsyncPostgresSaver(pool)
    store = AsyncPostgresStore(pool, index=index)
    tools = await _load_mcp_tools(s.mcp_server_url)
    log.info("Đã nạp công cụ MCP: %s", [t.name for t in tools])
    return build_graph(build_chat_model(s), tools, saver, store)
