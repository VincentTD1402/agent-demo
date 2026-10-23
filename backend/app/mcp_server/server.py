"""MCP server của ShopBot: tra đơn, hoàn tiền, chính sách (Streamable HTTP)."""
import logging

from mcp.server.fastmcp import FastMCP

from app.mcp_server import db
from app.settings.mcp import get_mcp_settings

_settings = get_mcp_settings()
logging.basicConfig(level=_settings.log_level.upper())

mcp = FastMCP(
    "shopbot",
    host=_settings.mcp_host,
    port=_settings.mcp_port,
    stateless_http=True,
)

REFUND_POLICY = (
    "Chính sách hoàn tiền: chỉ hoàn cho đơn đã giao (delivered), tối đa bằng tổng giá trị đơn, "
    "mỗi đơn hoàn một lần. Đơn đang xử lý/đang giao hoặc đã huỷ không đủ điều kiện hoàn tiền."
)


@mcp.tool()
async def lookup_order(order_id: str, user_id: str) -> dict:
    """Tra cứu đơn hàng (chỉ đọc). Dùng khi khách hỏi về trạng thái/chi tiết đơn.
    Không dùng để hoàn tiền. Ví dụ: order_id="A100"."""
    order = await db.get_order(order_id.strip().upper(), user_id)
    if not order:
        return {"found": False, "message": f"Không tìm thấy đơn {order_id} của khách này."}
    order["created_at"] = order["created_at"].isoformat()
    return {"found": True, **order}


@mcp.tool()
async def search_products(
    query: str | None = None, category: str | None = None, max_price_vnd: int | None = None
) -> list[dict]:
    """Tìm sản phẩm trong cửa hàng (chỉ đọc) để tư vấn mua hàng. category là một trong:
    dien-thoai, laptop, may-tinh-bang, dong-ho, phu-kien. Trả tối đa 8 sản phẩm gồm tên, giá, tồn kho."""
    rows = await db.search_products(query, category, max_price_vnd)
    return [
        {k: r[k] for k in ("slug", "name", "category", "brand", "price_vnd", "old_price_vnd", "rating", "stock")}
        | {"rating": float(r["rating"])}
        for r in rows
    ]


@mcp.tool()
async def get_product_details(slug: str) -> dict:
    """Xem thông số và mô tả chi tiết một sản phẩm theo slug (lấy từ search_products)."""
    p = await db.get_product(slug)
    if not p:
        return {"found": False}
    return {"found": True, **p, "rating": float(p["rating"])}


@mcp.tool()
async def get_refund_policy() -> str:
    """Lấy chính sách hoàn tiền. Gọi trước khi quyết định đơn có đủ điều kiện hoàn tiền hay không."""
    return REFUND_POLICY


@mcp.tool()
async def issue_refund(order_id: str, user_id: str, amount_vnd: int, reason: str) -> dict:
    """Hoàn tiền cho đơn hàng (HÀNH ĐỘNG KHÓ ĐẢO NGƯỢC, cần người duyệt).
    Chỉ gọi sau khi đã lookup_order và xác nhận đơn đủ điều kiện theo chính sách.
    Idempotent: gọi lại cùng order_id trả kết quả cũ, không hoàn lần hai."""
    order = await db.get_order(order_id.strip().upper(), user_id)
    if not order:
        return {"ok": False, "message": "Không tìm thấy đơn của khách này."}
    if order["status"] != "delivered":
        return {"ok": False, "message": f"Đơn ở trạng thái {order['status']}, không đủ điều kiện hoàn."}
    if not 0 < amount_vnd <= order["total_vnd"]:
        return {"ok": False, "message": f"Số tiền phải trong khoảng 1..{order['total_vnd']} VND."}
    refund, is_new = await db.create_refund(order["id"], amount_vnd, reason)
    return {
        "ok": True,
        "already_refunded": not is_new,
        "order_id": refund["order_id"],
        "amount_vnd": refund["amount_vnd"],
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
