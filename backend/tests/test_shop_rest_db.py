"""REST giỏ hàng (storefront) và API nhân viên trên Postgres thật (cần TEST_DATABASE_URL)."""

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.settings import get_settings
from app.shop.common import ShopError
from app.shop.router import cart_router, staff_router
from settings_factory import make_settings

SID = {"X-Session-Id": "session-aaaaaaaaaaaa"}
STAFF = {"X-Staff-Key": "staff-secret"}
PHONE = "0900000001"


def make_client(shop, **settings):
    app = FastAPI()
    app.include_router(cart_router)
    app.include_router(staff_router)
    app.state.shop = shop
    cfg = make_settings(**settings)
    app.dependency_overrides[get_settings] = lambda: cfg

    @app.exception_handler(ShopError)
    async def handler(_: Request, exc: ShopError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    return TestClient(app)


@pytest.fixture
def client(shop):
    return make_client(shop, staff_api_key="staff-secret")


def test_cart_endpoints_round_trip(client):
    assert client.get("/cart", headers=SID).json()["lines"] == []
    added = client.post("/cart/items", json={"slug": "anker-sac-20w", "qty": 2}, headers=SID).json()
    assert added["lines"][0]["qty"] == 2 and added["subtotal_vnd"] == 580000 and added["shipping_fee_vnd"] == 0
    assert client.put("/cart/items/anker-sac-20w", json={"qty": 1}, headers=SID).json()["lines"][0]["qty"] == 1
    assert client.delete("/cart/items/anker-sac-20w", headers=SID).json()["lines"] == []


def test_cart_errors_are_400_with_message_and_validation_is_422(client):
    missing = client.post("/cart/items", json={"slug": "khong-co"}, headers=SID)
    assert missing.status_code == 400 and "Không tìm thấy" in missing.json()["detail"]
    assert client.get("/cart").status_code == 400  # thiếu X-Session-Id
    assert client.get("/cart", headers={"X-Session-Id": "short"}).status_code == 400
    assert client.post("/cart/items", json={"slug": "anker-sac-20w", "qty": 11}, headers=SID).status_code == 422


def test_cart_is_isolated_per_session_and_shared_with_agent_tools(client, shop):
    shop.cart.add("session-aaaaaaaaaaaa", "anker-sac-20w", 1)  # agent thêm qua domain/tool
    assert client.get("/cart", headers=SID).json()["lines"][0]["slug"] == "anker-sac-20w"  # UI thấy ngay
    assert client.get("/cart", headers={"X-Session-Id": "session-bbbbbbbbbbbb"}).json()["lines"] == []


def test_staff_endpoints_require_key(shop):
    assert make_client(shop).get("/staff/refunds").status_code == 503  # STAFF_API_KEY trống: tắt hẳn
    client = make_client(shop, staff_api_key="staff-secret")
    assert client.get("/staff/refunds").status_code == 401
    assert client.get("/staff/refunds", headers={"X-Staff-Key": "wrong"}).status_code == 401
    assert client.get("/staff/refunds", headers=STAFF).status_code == 200


def test_staff_decides_refund_request(client, shop):
    refund_id = shop.refunds.request("SM000100", PHONE, "defective", "lỗi loa")["refund_id"]
    pending = client.get("/staff/refunds", headers=STAFF).json()
    assert [p["id"] for p in pending] == [refund_id] and pending[0]["amount_vnd"] == 5490000
    done = client.post(f"/staff/refunds/{refund_id}/decision", json={"approve": True, "note": "ok"}, headers=STAFF)
    assert done.json()["status"] == "approved"
    assert client.get("/staff/refunds", headers=STAFF).json() == []
    again = client.post(f"/staff/refunds/{refund_id}/decision", json={"approve": False}, headers=STAFF)
    assert again.status_code == 400 and "đã được xử lý" in again.json()["detail"]


def test_staff_advances_order_status(client):
    ok = client.post("/staff/orders/SM000102/status", json={"status": "shipped"}, headers=STAFF)
    assert ok.json()["status"] == "shipped"
    assert client.post("/staff/orders/SM000102/status", json={"status": "processing"}, headers=STAFF).status_code == 422
    assert client.post("/staff/orders/SM000100/status", json={"status": "shipped"}, headers=STAFF).status_code == 400
