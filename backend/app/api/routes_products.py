"""Danh mục sản phẩm cho trang bán hàng."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import require_api_key
from app.shop import repo

router = APIRouter(prefix="/v1/products", tags=["products"], dependencies=[Depends(require_api_key)])


@router.get("")
async def list_products(
    request: Request,
    q: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=50, ge=1, le=50),
):
    async with request.app.state.pool.connection() as conn:
        return await repo.search_products(conn, q=q, category=category, limit=limit)


@router.get("/{slug}")
async def get_product(request: Request, slug: str):
    async with request.app.state.pool.connection() as conn:
        product = await repo.get_product(conn, slug)
    if not product:
        raise HTTPException(404, "product not found")
    return product
