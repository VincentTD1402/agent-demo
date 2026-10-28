"""Định nghĩa tool MCP cho agent: tra cứu hàng, giỏ hàng, chốt đơn, thanh toán, tra đơn, hoàn tiền.

Quy ước:
- Mọi tool trả về {"ok": true, ...} hoặc {"ok": false, "error": "<thông báo cho khách>"}; lỗi nghiệp vụ không ném ngoại lệ
  để model đọc được và diễn đạt lại.
- `session_id` do agent runtime gắn vào (model không thấy tham số này), xem app/agent/shop_tools.py.
- Giá, phí ship, số tiền hoàn luôn do server tính; tool không nhận số tiền từ model.
- Tool nào ghi dữ liệu chỉ nên được gọi sau khi khách xác nhận rõ ràng (nêu trong mô tả để model tuân thủ).
"""

import asyncio
import logging
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from app.shop.common import ShopError
from app.shop.services import ShopServices

logger = logging.getLogger(__name__)

_PRODUCT_FIELDS = ("slug", "name", "category", "brand", "price_vnd", "old_price_vnd", "rating", "stock", "specs", "description")


async def _run(fn: Callable[[], dict]) -> dict:
    """Chạy hàm đồng bộ (DB) ngoài event loop và đổi lỗi nghiệp vụ thành kết quả có cấu trúc."""
    try:
        return {"ok": True, **await asyncio.to_thread(fn)}
    except ShopError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        logger.exception("Tool gặp lỗi không lường trước")
        return {"ok": False, "error": "Hệ thống đang gặp sự cố, vui lòng thử lại sau"}


def register_tools(mcp: FastMCP, shop: ShopServices) -> None:
    @mcp.tool()
    async def search_products(
        query: str | None = None, category: str | None = None, min_price_vnd: int | None = None,
        max_price_vnd: int | None = None, in_stock_only: bool = False, limit: int = 8,
    ) -> dict:
        """Look up products with LIVE price and stock. category is one of: dien-thoai, laptop, may-tinh-bang, dong-ho, phu-kien.
        Use for any question about price, availability, comparison or recommendation. Prices are in VND."""
        def work() -> dict:
            rows = shop.products.search(
                query, category, max(1, min(limit, 20)),
                min_price_vnd=min_price_vnd, max_price_vnd=max_price_vnd, in_stock_only=in_stock_only,
            )
            return {"products": [{k: p[k] for k in _PRODUCT_FIELDS} for p in rows]}
        return await _run(work)

    @mcp.tool()
    async def get_product(slug: str) -> dict:
        """Get one product by slug with live price and stock."""
        def work() -> dict:
            product = shop.products.get(slug)
            if product is None:
                raise ShopError("Không tìm thấy sản phẩm này")
            return {"product": {k: product[k] for k in _PRODUCT_FIELDS}}
        return await _run(work)

    @mcp.tool()
    async def view_cart(session_id: str) -> dict:
        """Show the customer's current cart with live prices, shipping fee and total."""
        return await _run(lambda: {"cart": shop.cart.view(session_id)})

    @mcp.tool()
    async def add_to_cart(session_id: str, slug: str, quantity: int = 1) -> dict:
        """Add `quantity` of a product to the cart (adds to the existing quantity). Checks live stock. Max 10 per product."""
        return await _run(lambda: {"cart": shop.cart.add(session_id, slug, quantity)})

    @mcp.tool()
    async def set_cart_quantity(session_id: str, slug: str, quantity: int) -> dict:
        """Set the exact quantity of a product in the cart; quantity 0 removes it."""
        return await _run(lambda: {"cart": shop.cart.set_quantity(session_id, slug, quantity)})

    @mcp.tool()
    async def checkout(session_id: str, customer_name: str, phone: str, address: str, payment_method: str) -> dict:
        """Place an order from the current cart. payment_method: 'cod' (pay on delivery) or 'online' (then call pay_order).
        Creates a real order and reduces stock. ONLY call after the customer has explicitly confirmed the order summary
        (items, total, receiver name, phone, full address, payment method) in their latest message."""
        return await _run(lambda: {"order": shop.orders.checkout(session_id, customer_name, phone, address, payment_method)})

    @mcp.tool()
    async def pay_order(order_code: str, phone: str) -> dict:
        """Pay an unpaid 'online' order (simulated payment gateway). The amount is taken from the order, never from the caller.
        ONLY call after the customer has agreed to pay now."""
        return await _run(lambda: {"order": shop.orders.pay(order_code, phone)})

    @mcp.tool()
    async def lookup_order(order_code: str, phone: str) -> dict:
        """Look up an order's real status, payment status, items and refund status. Needs the order code AND the phone used to order."""
        return await _run(lambda: {"order": shop.orders.get(order_code, phone)})

    @mcp.tool()
    async def list_my_orders(session_id: str) -> dict:
        """List orders placed in this chat session (latest first)."""
        return await _run(lambda: {"orders": shop.orders.list_for_session(session_id)})

    @mcp.tool()
    async def cancel_order(order_code: str, phone: str) -> dict:
        """Cancel an order that is still 'processing' and unpaid; stock is restored. ONLY call after the customer confirmed."""
        return await _run(lambda: {"order": shop.orders.cancel(order_code, phone)})

    @mcp.tool()
    async def check_refund_eligibility(order_code: str, phone: str, reason_code: str, item_slugs: list[str] | None = None) -> dict:
        """Check (without changing anything) whether an order can be refunded under policy: delivered within the refund window,
        valid reason, no existing refund. reason_code: not_as_described | defective | wrong_or_missing_item |
        damaged_in_shipping | changed_mind (never refundable). item_slugs optional for a partial refund."""
        return await _run(lambda: {"result": shop.refunds.check(order_code, phone, reason_code, item_slugs)})

    @mcp.tool()
    async def request_refund(
        order_code: str, phone: str, reason_code: str, details: str = "", item_slugs: list[str] | None = None
    ) -> dict:
        """Create a refund REQUEST (status pending). It does NOT refund money: ShopMobile staff must review and approve it.
        Call check_refund_eligibility first and ONLY call this after the customer confirmed they want to submit it."""
        return await _run(lambda: {"refund": shop.refunds.request(order_code, phone, reason_code, details, item_slugs)})
