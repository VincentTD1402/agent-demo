"""Điểm vào FastAPI: /health, API nạp tài liệu (/documents/*) và API chat RAG (/chat/*) danh mục sản phẩm (/v1/products), giỏ hàng (/cart) và API nhân viên (/staff/*)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.agent.bootstrap import create_agent
from app.agent.guardrails import ChatGuard
from app.agent.router import router as chat_router
from app.documents.router import router as documents_router
from app.documents.store import PgDocumentStore, create_pool
from app.embedding_client import HttpEmbedder
from app.products.admin import ProductAdminService
from app.products.admin_router import router as product_admin_router
from app.products.repository import PgProductRepository
from app.products.router import router as products_router
from app.settings import EMBEDDING_DIMS, get_settings
from app.shop.common import ShopError
from app.shop.router import cart_router, staff_router
from app.shop.services import build_shop_services


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    pool = create_pool(settings)
    pool.open(wait=False)
    embedder = HttpEmbedder(
        base_url=settings.embedding_api_url,
        model=settings.embedding_model_name,
        dims=EMBEDDING_DIMS,
        batch_size=settings.embedding_batch_size,
        timeout_s=settings.embedding_timeout_s,
        api_key=settings.embedding_api_key,
    )
    app.state.document_store = PgDocumentStore(pool)
    app.state.embedder = embedder
    app.state.product_repo = PgProductRepository(pool)
    app.state.product_admin = ProductAdminService(pool)
    app.state.shop = build_shop_services(settings, pool)
    app.state.chat_guard = ChatGuard.from_settings(settings)
    app.state.agent = await create_agent(settings, pool, embedder)
    try:
        yield
    finally:
        await app.state.agent.close()
        embedder.close()
        pool.close()


logging.basicConfig(level=logging.INFO)  # uvicorn chỉ cấu hình logger của nó; log của agent (route, tool) cần dòng này
app = FastAPI(title="Chatbot backend", lifespan=lifespan)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(products_router)
app.include_router(cart_router)
app.include_router(staff_router)
app.include_router(product_admin_router)


@app.exception_handler(ShopError)
async def shop_error_handler(_: Request, exc: ShopError) -> JSONResponse:
    # Lỗi nghiệp vụ (hết hàng, sai phiên, ...) có thông điệp an toàn để hiển thị cho khách
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
