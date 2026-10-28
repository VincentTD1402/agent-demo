"""Tool MCP trên Postgres thật (cần TEST_DATABASE_URL) và xác thực Bearer của MCP server."""

import json

import pytest
from starlette.testclient import TestClient

from app.mcp_server.server import build_app, build_mcp
from app.shop.services import ShopServices

SESSION = "session-aaaaaaaaaaaa"
PHONE = "0900000001"


async def call(mcp, name: str, args: dict) -> dict:
    result = await mcp.call_tool(name, args)
    if isinstance(result, tuple):  # (nội dung, structured)
        result = result[0]
    return json.loads(result[0].text)


async def test_tool_catalog_lists_expected_tools(shop: ShopServices):
    names = {tool.name for tool in await build_mcp(shop).list_tools()}
    assert names == {
        "search_products", "get_product", "view_cart", "add_to_cart", "set_cart_quantity", "checkout", "pay_order",
        "lookup_order", "list_my_orders", "cancel_order", "check_refund_eligibility", "request_refund",
    }


async def test_search_products_uses_live_price_and_stock_filters(shop: ShopServices, db_pool):
    mcp = build_mcp(shop)
    with db_pool.connection() as conn:
        conn.execute("UPDATE products SET price_vnd = 8000000, stock = 0 WHERE slug = 'xiaomi-redmi-note-14-pro'")
    cheap = await call(mcp, "search_products", {"category": "dien-thoai", "max_price_vnd": 10000000})
    assert [p["slug"] for p in cheap["products"]] == ["xiaomi-redmi-note-14-pro"]
    assert cheap["products"][0]["price_vnd"] == 8000000 and cheap["products"][0]["stock"] == 0  # giá mới, không phải giá lúc seed
    in_stock = await call(mcp, "search_products", {"category": "dien-thoai", "max_price_vnd": 10000000, "in_stock_only": True})
    assert in_stock["products"] == []


async def test_cart_checkout_and_lookup_flow_through_tools(shop: ShopServices):
    mcp = build_mcp(shop)
    added = await call(mcp, "add_to_cart", {"session_id": SESSION, "slug": "anker-sac-20w", "quantity": 2})
    assert added["ok"] and added["cart"]["total_vnd"] == 580000
    order = (await call(mcp, "checkout", {
        "session_id": SESSION, "customer_name": "Nguyễn Văn A", "phone": PHONE,
        "address": "12 Nguyễn Huệ, Bến Nghé, Quận 1, TP. HCM", "payment_method": "online",
    }))["order"]
    paid = await call(mcp, "pay_order", {"order_code": order["code"], "phone": PHONE})
    assert paid["order"]["payment_status"] == "paid"
    looked = await call(mcp, "lookup_order", {"order_code": order["code"], "phone": PHONE})
    assert looked["order"]["items"][0]["qty"] == 2
    assert (await call(mcp, "list_my_orders", {"session_id": SESSION}))["orders"][0]["code"] == order["code"]


async def test_business_errors_become_structured_results_not_exceptions(shop: ShopServices):
    mcp = build_mcp(shop)
    result = await call(mcp, "checkout", {
        "session_id": SESSION, "customer_name": "A B", "phone": PHONE, "address": "địa chỉ đủ dài ở đây", "payment_method": "cod",
    })
    assert result == {"ok": False, "error": "Giỏ hàng đang trống"}
    wrong = await call(mcp, "lookup_order", {"order_code": "SM000100", "phone": "0911111111"})
    assert wrong["ok"] is False and "Không tìm thấy" in wrong["error"]


async def test_refund_tools_only_create_pending_request(shop: ShopServices):
    mcp = build_mcp(shop)
    check = await call(mcp, "check_refund_eligibility", {"order_code": "SM000100", "phone": PHONE, "reason_code": "defective"})
    assert check["result"]["eligible"]
    refund = await call(mcp, "request_refund", {"order_code": "SM000100", "phone": PHONE, "reason_code": "defective", "details": "lỗi loa"})
    assert refund["refund"]["status"] == "pending" and "nhân viên" in refund["refund"]["next_step"].lower()
    assert shop.orders.get("SM000100", PHONE)["payment_status"] == "paid"  # tiền chưa được hoàn


def test_bearer_auth_protects_mcp_but_not_health(shop: ShopServices):
    client = TestClient(build_app(shop, "secret-key"))
    assert client.get("/health").status_code == 200
    assert client.post("/mcp", json={}).status_code == 401
    assert client.post("/mcp", json={}, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/mcp", json={}, headers={"Authorization": "secret-key"}).status_code == 401


def test_server_refuses_empty_key(shop: ShopServices):
    with pytest.raises(ValueError, match="MCP_API_KEY"):
        build_app(shop, "")
