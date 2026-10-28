"""MCP server (streamable HTTP, stateless) chạy như service riêng; chỉ agent nội bộ gọi tới bằng Bearer key."""

import hmac

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.mcp_server.tools import register_tools
from app.shop.services import ShopServices


class BearerAuthMiddleware:
    """Từ chối mọi request thiếu/sai `Authorization: Bearer <key>` (trừ /health). Viết dạng ASGI thuần để không làm hỏng SSE."""

    def __init__(self, app: ASGIApp, token: str):
        if not token:
            raise ValueError("MCP_API_KEY chưa được đặt")
        self._app = app
        self._token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] != "/health":
            header = dict(scope["headers"]).get(b"authorization", b"")
            if not hmac.compare_digest(header, b"Bearer " + self._token):
                await JSONResponse({"detail": "Unauthorized"}, status_code=401)(scope, receive, send)
                return
        await self._app(scope, receive, send)


def build_mcp(shop: ShopServices, port: int = 8001) -> FastMCP:
    mcp = FastMCP(
        "shopmobile",
        instructions="Tool của ShopMobile: tra cứu sản phẩm/tồn kho, giỏ hàng, chốt đơn, thanh toán, tra đơn, hoàn tiền.",
        host="0.0.0.0",
        port=port,
        stateless_http=True,  # mỗi lời gọi độc lập, không giữ session phía server
        # Chỉ lắng nghe trong mạng nội bộ phía sau Bearer key, tên host là tên service compose nên không bật chống DNS rebinding
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    register_tools(mcp, shop)
    return mcp


def build_app(shop: ShopServices, api_key: str, port: int = 8001) -> ASGIApp:
    if not api_key:  # kiểm tra ngay: Starlette chỉ dựng middleware ở request đầu tiên nên lỗi sẽ nổ quá muộn
        raise ValueError("MCP_API_KEY chưa được đặt")
    app = build_mcp(shop, port).streamable_http_app()
    app.add_middleware(BearerAuthMiddleware, token=api_key)
    return app
