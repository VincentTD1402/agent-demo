"""Điểm vào FastAPI: /health, API nạp tài liệu (/documents/*) và API chat RAG (/chat/*) và danh mục sản phẩm (/v1/products)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent.bootstrap import create_agent
from app.agent.router import router as chat_router
from app.documents.router import router as documents_router
from app.documents.store import PgDocumentStore, create_pool
from app.embedding_client import HttpEmbedder
from app.products.repository import PgProductRepository
from app.products.router import router as products_router
from app.settings import EMBEDDING_DIMS, get_settings


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
    app.state.agent = await create_agent(settings, pool, embedder)
    try:
        yield
    finally:
        await app.state.agent.close()
        embedder.close()
        pool.close()


app = FastAPI(title="Chatbot backend", lifespan=lifespan)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(products_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
