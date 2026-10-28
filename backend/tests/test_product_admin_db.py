"""API quản trị sản phẩm của nhân viên trên Postgres thật (cần TEST_DATABASE_URL)."""

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.mcp_server.server import build_mcp
from app.products.admin import ProductAdminService
from app.products.admin_router import router
from app.settings import get_settings
from app.shop.common import ShopError
from settings_factory import make_settings
from test_product_images import JPG, PNG

STAFF = {"X-Staff-Key": "staff-secret"}
NEW = {
    "slug": "tai-nghe-moi", "name": "Tai nghe mới", "category": "phu-kien", "brand": "Sony", "price_vnd": 1500000,
    "old_price_vnd": 1800000, "stock": 12, "rating": 4.5, "specs": {"Pin": "20 giờ"}, "description": "Mô tả", "image_url": None,
}


def make_client(shop, db_pool, tmp_path, **settings):
    app = FastAPI()
    app.include_router(router)
    app.state.product_admin = ProductAdminService(db_pool)
    app.state.product_repo = shop.products
    cfg = make_settings(**({"staff_api_key": "staff-secret", "product_images_dir": str(tmp_path / "uploads")} | settings))
    app.dependency_overrides[get_settings] = lambda: cfg

    @app.exception_handler(ShopError)
    async def handler(_: Request, exc: ShopError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    return TestClient(app)


@pytest.fixture
def client(shop, db_pool, tmp_path):
    return make_client(shop, db_pool, tmp_path)


def test_endpoints_require_staff_key(shop, db_pool, tmp_path):
    assert make_client(shop, db_pool, tmp_path, staff_api_key="").get("/staff/products").status_code == 503
    c = make_client(shop, db_pool, tmp_path)
    assert c.get("/staff/products").status_code == 401
    assert c.post("/staff/products", json=NEW).status_code == 401
    assert c.get("/staff/products", headers={"X-Staff-Key": "wrong"}).status_code == 401


def test_list_includes_out_of_stock_products_and_filters(client, db_pool):
    with db_pool.connection() as conn:
        conn.execute("UPDATE products SET stock = 0 WHERE slug = 'anker-sac-20w'")
    everything = client.get("/staff/products", headers=STAFF).json()
    assert len(everything) == 16 and next(p for p in everything if p["slug"] == "anker-sac-20w")["stock"] == 0
    assert [p["slug"] for p in client.get("/staff/products", params={"category": "laptop"}, headers=STAFF).json()][0] == "macbook-air-m3-13"


def test_create_update_delete_round_trip(client, shop):
    created = client.post("/staff/products", json=NEW, headers=STAFF)
    assert created.status_code == 201 and created.json()["price_vnd"] == 1500000 and created.json()["specs"] == {"Pin": "20 giờ"}
    assert shop.products.get("tai-nghe-moi")["stock"] == 12  # website thấy ngay
    update = {k: v for k, v in NEW.items() if k != "slug"} | {"price_vnd": 1400000, "old_price_vnd": None, "stock": 5}
    assert client.put("/staff/products/tai-nghe-moi", json=update, headers=STAFF).json()["price_vnd"] == 1400000
    assert shop.products.get("tai-nghe-moi")["old_price_vnd"] is None
    assert client.delete("/staff/products/tai-nghe-moi", headers=STAFF).json() == {"deleted": "tai-nghe-moi"}
    assert shop.products.get("tai-nghe-moi") is None


def test_duplicate_slug_and_missing_product_are_400(client):
    assert client.post("/staff/products", json=NEW, headers=STAFF).status_code == 201
    dup = client.post("/staff/products", json=NEW, headers=STAFF)
    assert dup.status_code == 400 and "đã tồn tại" in dup.json()["detail"]
    body = {k: v for k, v in NEW.items() if k != "slug"}
    assert client.put("/staff/products/khong-co", json=body, headers=STAFF).status_code == 400
    assert client.delete("/staff/products/khong-co", headers=STAFF).status_code == 400


@pytest.mark.parametrize("patch", [
    {"slug": "Sai Slug"}, {"slug": "-bad"}, {"price_vnd": -1}, {"stock": -5}, {"category": "xe-may"}, {"name": "a"},
    {"old_price_vnd": 1500000}, {"old_price_vnd": 100}, {"rating": 6}, {"image_url": "javascript:alert(1)"},
    {"image_url": "//evil.com/x.png"}, {"image_url": "http://insecure.example/x.png"}, {"specs": {f"k{i}": "v" for i in range(31)}},
    {"specs": {"": "x"}}, {"price_vnd": 2_000_000_000},
])
def test_invalid_input_is_rejected_with_422(client, patch):
    assert client.post("/staff/products", json=NEW | patch, headers=STAFF).status_code == 422


def test_image_url_accepts_local_path_and_https(client):
    for slug, url in (("anh-noi-bo", "/products/x.jpg"), ("anh-https", "https://cdn.example.com/x.png")):
        assert client.post("/staff/products", json=NEW | {"slug": slug, "image_url": url}, headers=STAFF).json()["image_url"] == url


def test_product_with_orders_cannot_be_deleted_but_cart_only_product_can(client, shop):
    assert "đơn hàng" in client.delete("/staff/products/airpods-pro-2-usb-c", headers=STAFF).json()["detail"]  # có trong đơn mẫu
    client.post("/staff/products", json=NEW, headers=STAFF)
    shop.cart.add("session-aaaaaaaaaaaa", "tai-nghe-moi", 1)
    assert client.delete("/staff/products/tai-nghe-moi", headers=STAFF).status_code == 200
    assert shop.cart.view("session-aaaaaaaaaaaa")["lines"] == []  # giỏ chứa món đã xoá được dọn theo


async def test_price_and_stock_changes_are_live_for_the_assistant_tools(client, shop):
    body = {k: v for k, v in NEW.items() if k != "slug"} | {"name": "Củ sạc nhanh Anker 20W USB-C", "category": "phu-kien", "brand": "Anker"}
    client.put("/staff/products/anker-sac-20w", json=body | {"price_vnd": 250000, "old_price_vnd": 390000, "stock": 3}, headers=STAFF)
    import json

    result = await build_mcp(shop).call_tool("get_product", {"slug": "anker-sac-20w"})
    product = json.loads((result[0] if isinstance(result, tuple) else result)[0].text)["product"]
    assert (product["price_vnd"], product["stock"]) == (250000, 3)
    with pytest.raises(ShopError, match="chỉ còn 3"):
        shop.cart.add("session-aaaaaaaaaaaa", "anker-sac-20w", 4)  # tồn kho mới được áp dụng ngay cho giỏ hàng


def test_image_upload_replaces_old_file_and_validates_content(client, tmp_path):
    client.post("/staff/products", json=NEW, headers=STAFF)
    first = client.post("/staff/products/tai-nghe-moi/image", files={"file": ("a.png", PNG, "image/png")}, headers=STAFF).json()
    uploads = tmp_path / "uploads"
    assert first["image_url"].startswith("/uploads/products/tai-nghe-moi-") and len(list(uploads.iterdir())) == 1
    second = client.post("/staff/products/tai-nghe-moi/image", files={"file": ("b.jpg", JPG, "image/jpeg")}, headers=STAFF).json()
    assert second["image_url"].endswith(".jpg") and [p.name for p in uploads.iterdir()] == [second["image_url"].rsplit("/", 1)[1]]
    fake = client.post("/staff/products/tai-nghe-moi/image", files={"file": ("x.png", b"<script>alert(1)</script>", "image/png")}, headers=STAFF)
    assert fake.status_code == 400 and "PNG, JPG" in fake.json()["detail"]
    client.delete("/staff/products/tai-nghe-moi", headers=STAFF)
    assert list(uploads.iterdir()) == []  # xoá sản phẩm thì dọn cả ảnh đã tải lên


def test_image_upload_enforces_size_limit_and_does_not_orphan_files(shop, db_pool, tmp_path):
    client = make_client(shop, db_pool, tmp_path, max_product_image_mb=1)
    client.post("/staff/products", json=NEW, headers=STAFF)
    big = PNG + b"\x00" * (1024 * 1024)
    too_big = client.post("/staff/products/tai-nghe-moi/image", files={"file": ("big.png", big, "image/png")}, headers=STAFF)
    assert too_big.status_code == 400 and "lớn hơn" in too_big.json()["detail"]
    missing = client.post("/staff/products/khong-co/image", files={"file": ("a.png", PNG, "image/png")}, headers=STAFF)
    assert missing.status_code == 400
    assert not (tmp_path / "uploads").exists() or list((tmp_path / "uploads").iterdir()) == []
