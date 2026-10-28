"""Test API sản phẩm bằng repository giả: không cần Postgres."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.products.repository import _escape_like
from app.products.router import router

PRODUCT = {
    "slug": "iphone-16-128gb", "name": "iPhone 16 128GB", "category": "dien-thoai", "brand": "Apple",
    "price_vnd": 22990000, "old_price_vnd": 24990000, "rating": 4.8, "stock": 25,
    "specs": {"Chip": "A18"}, "description": "Chip A18 mạnh mẽ.", "image_url": "/products/iphone-16-128gb.jpg",
}


class FakeRepo:
    def __init__(self):
        self.calls = []

    def search(self, q, category, limit):
        self.calls.append((q, category, limit))
        return [PRODUCT]

    def get(self, slug):
        return PRODUCT if slug == PRODUCT["slug"] else None


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.state.product_repo = FakeRepo()
    return TestClient(app)


def test_list_passes_filters_and_returns_frontend_shape(client):
    r = client.get("/v1/products", params={"q": "iphone", "category": "dien-thoai", "limit": 5})
    assert r.status_code == 200
    assert r.json() == [PRODUCT]
    assert client.app.state.product_repo.calls == [("iphone", "dien-thoai", 5)]


def test_list_defaults_and_limit_bounds(client):
    client.get("/v1/products")
    assert client.app.state.product_repo.calls == [(None, None, 50)]
    assert client.get("/v1/products", params={"limit": 0}).status_code == 422
    assert client.get("/v1/products", params={"limit": 101}).status_code == 422


def test_get_product_and_404(client):
    assert client.get("/v1/products/iphone-16-128gb").json()["name"] == "iPhone 16 128GB"
    assert client.get("/v1/products/khong-co").status_code == 404


def test_like_wildcards_are_escaped():
    assert _escape_like("50%_off\\") == "50\%\_off\\\\"
