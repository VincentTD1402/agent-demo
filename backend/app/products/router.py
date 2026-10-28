"""API danh mục sản phẩm cho storefront: GET /v1/products, GET /v1/products/{slug} (công khai, chỉ đọc)."""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/v1/products", tags=["products"])


class ProductOut(BaseModel):
    slug: str
    name: str
    category: str
    brand: str
    price_vnd: int
    old_price_vnd: int | None
    rating: float
    stock: int
    specs: dict[str, str]
    description: str
    image_url: str | None


@router.get("", response_model=list[ProductOut])
def list_products(
    request: Request,
    q: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[dict]:
    return request.app.state.product_repo.search(q, category, limit)


@router.get("/{slug}", response_model=ProductOut)
def get_product(slug: str, request: Request) -> dict:
    product = request.app.state.product_repo.get(slug)
    if product is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    return product
