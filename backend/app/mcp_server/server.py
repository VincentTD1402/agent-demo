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

def _refund_policy() -> str:
    days = get_mcp_settings().refund_window_days
    return (
        f"Chính sách hoàn tiền: chỉ đơn đã giao (delivered) và đã thanh toán, trong {days} ngày kể từ ngày giao. "
        "Số tiền tối đa bằng tiền hàng đã thanh toán, không gồm phí vận chuyển, trừ các khoản đã hoàn trước đó. "
        "Mỗi đơn có tối đa một yêu cầu hoàn tiền đang xử lý. Yêu cầu được GỬI CHO NHÂN VIÊN duyệt: khi gửi xong "
        "tiền CHƯA được hoàn, chỉ khi nhân viên duyệt và chi trả khách mới nhận tiền (không nói là đã hoàn). "
        "Đơn đang xử lý/đang giao hoặc đã huỷ không đủ điều kiện hoàn tiền."
    )


# Nội dung báo khách theo trạng thái thật của yêu cầu hoàn tiền (không bao giờ nói "đã hoàn" khi chưa chi trả)
_REQUEST_MESSAGES = {
    "pending_staff": "Yêu cầu hoàn tiền đã gửi tới nhân viên để xem xét. Tiền CHƯA được hoàn; khách sẽ được báo khi có quyết định.",
    "approved": "Yêu cầu hoàn tiền đã được nhân viên duyệt và đang chờ chi trả. Tiền CHƯA được hoàn.",
    "paid_out": "Đơn này đã được chi trả hoàn tiền trước đó; không tạo thêm yêu cầu.",
}


def _refund_refused(key: str, message: str) -> dict:
    return {"ok": False, "message_key": key, "message": message}


@mcp.tool()
async def lookup_order(order_id: str, user_id: str) -> dict:
    """Tra cứu đơn hàng (chỉ đọc). Dùng khi khách hỏi về trạng thái/chi tiết đơn.
    Không dùng để hoàn tiền. Ví dụ: order_id="A100". `refunded_vnd` chỉ có giá trị khi tiền ĐÃ chi trả cho khách;
    `pending_refund_vnd` là số tiền đang chờ nhân viên duyệt/chi trả (chưa hoàn); `refund_status` là trạng thái yêu cầu."""
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
    return _refund_policy()


@mcp.tool()
async def issue_refund(order_id: str, user_id: str, amount_vnd: int, reason: str) -> dict:
    """GỬI YÊU CẦU hoàn tiền cho nhân viên duyệt (cần khách xác nhận). KHÔNG hoàn tiền ngay: kết quả `ok=true` với
    `status="pending_staff"` nghĩa là yêu cầu đang chờ nhân viên, tiền CHƯA được hoàn; không được nói "đã hoàn".
    Chỉ gọi sau khi đã lookup_order và xác nhận đơn đủ điều kiện theo chính sách (đã giao, trong hạn, số tiền <= tiền hàng).
    Idempotent: gọi lại cho cùng đơn trả yêu cầu hiện có (`already_requested=true`), không tạo thêm."""
    order = await db.get_order(order_id.strip().upper(), user_id)
    basis = await db.get_refund_basis(order["id"], user_id) if order else None
    if not order or not basis:
        return _refund_refused("order_not_found", "Không tìm thấy đơn của khách này.")
    live = basis["live_request"]
    if live:
        return _refund_result(order["id"], live, already_requested=True)
    if order["status"] != "delivered":
        return _refund_refused(
            "order_not_delivered", f"Đơn ở trạng thái {order['status']}, không đủ điều kiện hoàn."
        )
    # Kiểm tra "đơn đã thanh toán" bổ sung khi bảng payments (thanh toán) có mặt; tới lúc đó đơn đã giao được coi là
    # đã thu tiền, nên đơn COD chưa thu tiền chưa bị chặn ở đây.
    window = get_mcp_settings().refund_window_days
    days = basis["days_since_delivered"]
    if days is None or days > window:
        return _refund_refused("refund_window_expired", f"Đã quá hạn hoàn tiền {window} ngày kể từ ngày giao.")
    cap = basis["goods_vnd"] - basis["committed_vnd"]
    if not 0 < amount_vnd <= cap:
        return _refund_refused(
            "amount_out_of_range", f"Số tiền phải trong khoảng 1..{max(cap, 0)} VND (tiền hàng, không gồm phí ship)."
        )
    refund, is_new = await db.create_refund(order["id"], user_id, amount_vnd, reason)
    return _refund_result(order["id"], refund, already_requested=not is_new)


def _refund_result(order_id: str, request: dict, already_requested: bool) -> dict:
    status = request["status"]
    key = f"refund_request_already_{status}" if already_requested else "refund_request_submitted"
    return {
        "ok": True,
        "status": status,
        "already_requested": already_requested,
        "request_id": str(request["id"]),
        "order_id": order_id,
        "amount_vnd": request["amount_vnd"],
        "message_key": key,
        "message": _REQUEST_MESSAGES[status],
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
