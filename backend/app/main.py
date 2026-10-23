"""Điểm vào FastAPI của ShopBot agent."""
import logging
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.agent.runtime import open_runtime
from app.api import routes_chat, routes_health, routes_products
from app.config import get_settings
from app.shop.schema import ensure_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    await ensure_schema(settings.database_url, settings.seed_demo_data)
    async with AsyncExitStack() as stack:
        pool = AsyncConnectionPool(
            settings.database_url, open=False, kwargs={"row_factory": dict_row, "autocommit": True}
        )
        await pool.open()
        stack.push_async_callback(pool.close)
        app.state.pool = pool
        app.state.graph = await open_runtime(settings, stack)
        yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="ShopBot Agent API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
    )
    app.include_router(routes_health.router)
    app.include_router(routes_chat.router)
    app.include_router(routes_products.router)
    return app


app = create_app()
