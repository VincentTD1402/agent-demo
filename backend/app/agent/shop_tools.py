"""Nạp tool từ MCP server và gắn `session_id` tin cậy vào mỗi lời gọi.

`session_id` xác định giỏ hàng/đơn của khách. Nếu để model tự điền, một tin nhắn "độc hại" có thể khiến model gọi tool với
session_id của người khác. Vì vậy tham số này bị ẩn khỏi schema model nhìn thấy và luôn lấy từ cấu hình lượt chat do server
đặt (RunnableConfig.configurable.session_id).
"""

import copy
import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.settings import Settings

logger = logging.getLogger(__name__)

SESSION_ARG = "session_id"


def bind_session(tool: BaseTool) -> BaseTool:
    """Bọc tool MCP: ẩn `session_id` khỏi model và tự điền từ config. Tool không có tham số này giữ nguyên."""
    schema = tool.args_schema
    if not isinstance(schema, dict) or SESSION_ARG not in schema.get("properties", {}):
        return tool
    visible = copy.deepcopy(schema)
    visible["properties"].pop(SESSION_ARG)
    visible["required"] = [name for name in visible.get("required", []) if name != SESSION_ARG]

    async def run(config: RunnableConfig, **kwargs):
        session_id = (config.get("configurable") or {}).get(SESSION_ARG)
        if not session_id:
            raise ValueError("Thiếu session_id trong cấu hình lượt chat")
        # Ghi đè mọi giá trị model có thể đã gửi kèm: nguồn duy nhất là config
        return await tool.ainvoke({**kwargs, SESSION_ARG: session_id})

    return StructuredTool(name=tool.name, description=tool.description, args_schema=visible, coroutine=run)


async def load_shop_tools(settings: Settings) -> list[BaseTool]:
    """Danh sách tool của MCP server; ném lỗi nếu server chưa sẵn sàng (nơi gọi quyết định thử lại)."""
    client = MultiServerMCPClient(
        {
            "shop": {
                "transport": "streamable_http",
                "url": settings.mcp_server_url,
                "headers": {"Authorization": f"Bearer {settings.mcp_api_key}"},
            }
        }
    )
    tools = [bind_session(tool) for tool in await client.get_tools()]
    logger.info("Đã nạp %d tool từ MCP server: %s", len(tools), [t.name for t in tools])
    return tools
