"""Điểm vào FastAPI của ShopBot agent."""
import logging
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.agent.runtime import open_runtime
from app.api import routes_chat, routes_health, routes_products
from app.db.session import create_engine_from_settings, create_session_factory
from app.settings.api import get_api_settings


def _open_pool(dsn: str, max_size: int) -> AsyncConnectionPool:
    return AsyncConnectionPool(
        dsn, min_size=1, max_size=max_size, open=False, kwargs={"row_factory": dict_row, "autocommit": True}
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_api_settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger(__name__).info("Số kết nối Postgres tối đa của API: %s", settings.max_connections)
    async with AsyncExitStack() as stack:
        # Schema do bước migrate tạo; API chỉ kết nối bằng role `app` (DML, không DDL)
        pool = _open_pool(settings.database_url, settings.db_pool_max)
        await pool.open()
        stack.push_async_callback(pool.close)
        app.state.pool = pool

        engine = create_engine_from_settings(settings)
        stack.push_async_callback(engine.dispose)
        app.state.session_factory = create_session_factory(engine)

        graph_pool = _open_pool(settings.database_url, settings.langgraph_pool_max)
        await graph_pool.open()
        stack.push_async_callback(graph_pool.close)
        app.state.graph = await open_runtime(settings, graph_pool)
        yield


def create_app() -> FastAPI:
    settings = get_api_settings()
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
