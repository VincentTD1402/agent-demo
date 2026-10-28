"""Chạy MCP server: `python -m app.mcp_server` (service `mcp-server` trong docker-compose)."""

import logging
import sys

import uvicorn

from app.mcp_server.server import build_app
from app.documents.store import create_pool
from app.settings import get_settings
from app.shop.services import build_shop_services


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.mcp_api_key:
        sys.exit("MCP_API_KEY chưa được đặt: MCP server từ chối khởi động không có khoá")
    pool = create_pool(settings)
    pool.open(wait=False)  # vẫn khởi động khi DB chưa sẵn sàng; tool sẽ báo lỗi tạm thời cho tới khi DB lên
    app = build_app(build_shop_services(settings, pool), settings.mcp_api_key, settings.mcp_port)
    try:
        uvicorn.run(app, host="0.0.0.0", port=settings.mcp_port)
    finally:
        pool.close()


if __name__ == "__main__":
    main()
