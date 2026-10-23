"""Khởi tạo tài nguyên dài hạn: Postgres checkpointer + store, công cụ MCP, đồ thị."""
import asyncio
import logging
from contextlib import AsyncExitStack

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore

from app.agent.graph import build_graph
from app.config import Settings
from app.llm import build_chat_model, build_embeddings

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


async def open_runtime(s: Settings, stack: AsyncExitStack):
    """Mở kết nối, tạo bảng lần đầu, trả về đồ thị đã compile. Đóng qua `stack`."""
    index = {"dims": s.embedding_dims, "embed": build_embeddings(s), "fields": ["text"]}
    saver = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(s.database_url))
    store = await stack.enter_async_context(
        AsyncPostgresStore.from_conn_string(s.database_url, index=index)
    )
    await saver.setup()
    await store.setup()
    tools = await _load_mcp_tools(s.mcp_server_url)
    log.info("Đã nạp công cụ MCP: %s", [t.name for t in tools])
    return build_graph(build_chat_model(s), tools, saver, store)
