"""Truy vấn thật trên schema mới: 5 tool MCP (role mcp) và /v1/products (role app), hợp đồng trả về không đổi."""
import httpx
import psycopg
import pytest
from fastapi import FastAPI

from app.api import routes_products
from app.db.event_loop import run_async
from app.api.deps import require_api_key
from app.settings.migrate import ROLE_APP
from app.shop.seed_data import (
    DEMO_CUSTOMER_ID, ORDER_OTHER_CUSTOMER_ID, ORDER_REFUND_ELIGIBLE_ID, ORDER_SHIPPED_ID, PRODUCTS,
)
from tests.db.conftest import open_pool, role_url

PRODUCT_FIELDS = {
    "slug", "name", "category", "brand", "price_vnd", "old_price_vnd", "rating", "stock", "specs", "description",
    "image_url",
}


@pytest.fixture
def run_with_products_api(bootstrapped_db):
    """Chạy `scenario(client)` với router /v1/products thật, kết nối DB bằng role app."""

    def run(scenario):
        async def main():
            pool = await open_pool(role_url(bootstrapped_db, ROLE_APP))
            app = FastAPI()
            app.include_router(routes_products.router)
            app.dependency_overrides[require_api_key] = lambda: None
            app.state.pool = pool
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    await scenario(client)
            finally:
                await pool.close()

        run_async(main())

    return run


def test_lookup_order_returns_same_shape_for_owner(run_with_mcp):
    async def scenario(mcp_tools):
        result = await mcp_tools.lookup_order("a100", DEMO_CUSTOMER_ID)  # id chuẩn hoá chữ hoa như trước
        assert result["found"] is True
        assert {"id", "status", "total_vnd", "items", "created_at", "refunded_vnd", "pending_refund_vnd"} <= result.keys()
        assert result["id"] == ORDER_REFUND_ELIGIBLE_ID and result["status"] == "delivered"
        assert result["items"] == [{"name": "Tai nghe AirPods Pro 2 USB-C", "qty": 1}]
        assert result["total_vnd"] == 5490000 and result["refunded_vnd"] is None and result["pending_refund_vnd"] is None
        assert "shipping_address" not in result
        shipped = await mcp_tools.lookup_order(ORDER_SHIPPED_ID, DEMO_CUSTOMER_ID)
        assert sorted(i["qty"] for i in shipped["items"]) == [1, 2] and shipped["status"] == "shipped"

    run_with_mcp(scenario)


def test_lookup_order_hides_other_customers_and_bad_ids(run_with_mcp):
    async def scenario(mcp_tools):
        for user_id in ("22222222-2222-4222-8222-222222222222", "demo-user", "", "' OR 1=1 --"):
            result = await mcp_tools.lookup_order(ORDER_REFUND_ELIGIBLE_ID, user_id)
            assert result["found"] is False, user_id
        assert (await mcp_tools.lookup_order("NOPE", DEMO_CUSTOMER_ID))["found"] is False
        other = await mcp_tools.lookup_order(ORDER_OTHER_CUSTOMER_ID, DEMO_CUSTOMER_ID)
        assert other["found"] is False

    run_with_mcp(scenario)


def test_search_and_product_detail_tools(run_with_mcp):
    async def scenario(mcp_tools):
        phones = await mcp_tools.search_products(category="dien-thoai")
        assert {p["slug"] for p in phones} == {p["slug"] for p in PRODUCTS if p["category"] == "dien-thoai"}
        assert set(phones[0]) == {"slug", "name", "category", "brand", "price_vnd", "old_price_vnd", "rating", "stock"}
        assert isinstance(phones[0]["rating"], float)
        cheap = await mcp_tools.search_products(max_price_vnd=1_000_000)
        assert cheap and all(p["price_vnd"] <= 1_000_000 for p in cheap)
        # Tên sản phẩm có dấu ("Củ sạc nhanh Anker 20W"): mọi cách gõ (có dấu, không dấu, hoa/thường, dấu sai)
        # phải ra đúng sản phẩm đó và không ra sản phẩm khác, kể cả khi chữ không nằm trong brand/mô tả
        name_matches = {
            query: [p["slug"] for p in await mcp_tools.search_products(query=query)]
            for query in ("củ sạc", "cu sac", "CỦ SẠC", "cú sạc", "Củ Sạc Nhanh", "cu sac nhanh")
        }
        assert all(slugs == ["anker-sac-20w"] for slugs in name_matches.values()), name_matches
        assert await mcp_tools.search_products(query="cu sac khong ton tai") == []
        detail = await mcp_tools.get_product_details("iphone-16-128gb")
        assert detail["found"] is True and detail["specs"]["Chip"] == "A18" and detail["slug"] == "iphone-16-128gb"
        assert (await mcp_tools.get_product_details("khong-co"))["found"] is False
        assert "hoàn tiền" in (await mcp_tools.get_refund_policy()).lower()

    run_with_mcp(scenario)


def test_products_endpoint_contract_is_unchanged(run_with_products_api):
    async def scenario(client):
        response = await client.get("/v1/products")
        assert response.status_code == 200
        items = response.json()
        assert len(items) == len(PRODUCTS) and all(set(i) == PRODUCT_FIELDS for i in items)
        first = items[0]
        assert (first["slug"], first["price_vnd"], first["stock"]) == ("iphone-16-128gb", 22990000, 25)
        assert isinstance(first["rating"], (int, float)) and isinstance(first["specs"], dict)
        assert first["image_url"] == "/products/iphone-16-128gb.jpg"
        detail = (await client.get("/v1/products/iphone-16-128gb")).json()
        assert set(detail) == PRODUCT_FIELDS and detail == first
        assert (await client.get("/v1/products/khong-co")).status_code == 404

    run_with_products_api(scenario)


def test_products_filters_and_inactive_products(run_with_products_api, bootstrapped_db):
    async def scenario(client):
        assert len((await client.get("/v1/products", params={"category": "laptop"})).json()) == 4
        assert [p["slug"] for p in (await client.get("/v1/products", params={"q": "MACBOOK"})).json()] == ["macbook-air-m3-13"]
        assert [p["slug"] for p in (await client.get("/v1/products", params={"q": "cu sac"})).json()] == ["anker-sac-20w"]
        assert len((await client.get("/v1/products", params={"limit": 3})).json()) == 3
        with psycopg.connect(bootstrapped_db.migrator_database_url, autocommit=True) as conn:
            conn.execute("UPDATE products SET is_active = false WHERE slug = 'macbook-air-m3-13'")
        assert len((await client.get("/v1/products")).json()) == len(PRODUCTS) - 1
        assert (await client.get("/v1/products/macbook-air-m3-13")).status_code == 404

    run_with_products_api(scenario)
