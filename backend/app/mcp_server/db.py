"""Truy vấn dữ liệu shop (Postgres) cho các công cụ MCP."""
import asyncio
from contextlib import asynccontextmanager

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.settings.mcp import get_mcp_settings
from app.shop import repo

_pool: AsyncConnectionPool | None = None
_pool_lock = asyncio.Lock()


async def _get_pool() -> AsyncConnectionPool:
    """Pool mở lười ở lần dùng đầu; kích thước giới hạn theo ngân sách kết nối (McpSettings.db_pool_max)."""
    global _pool
    async with _pool_lock:
        if _pool is None:
            s = get_mcp_settings()
            pool = AsyncConnectionPool(
                s.database_url, min_size=1, max_size=s.db_pool_max, open=False,
                kwargs={"row_factory": dict_row, "autocommit": True},
            )
            await pool.open()
            _pool = pool
    return _pool


@asynccontextmanager
async def _connect():
    pool = await _get_pool()
    async with pool.connection() as conn:
        yield conn


async def get_order(order_id: str, user_id: str) -> dict | None:
    """Chỉ trả đơn thuộc đúng user_id để khách không xem được đơn người khác."""
    async with _connect() as conn:
        cur = await conn.execute(
            """SELECT o.id, o.status, o.total_vnd, o.items, o.created_at,
                      r.amount_vnd AS refunded_vnd
               FROM orders o LEFT JOIN refunds r ON r.order_id = o.id
               WHERE o.id = %s AND o.user_id = %s""",
            (order_id, user_id),
        )
        return await cur.fetchone()


async def create_refund(order_id: str, amount_vnd: int, reason: str) -> tuple[dict, bool]:
    """Tạo hoàn tiền idempotent. Trả (bản ghi, is_new)."""
    async with _connect() as conn:
        cur = await conn.execute(
            """INSERT INTO refunds (order_id, amount_vnd, reason) VALUES (%s, %s, %s)
               ON CONFLICT (order_id) DO NOTHING
               RETURNING order_id, amount_vnd, reason""",
            (order_id, amount_vnd, reason),
        )
        row = await cur.fetchone()
        if row:
            return row, True
        cur = await conn.execute(
            "SELECT order_id, amount_vnd, reason FROM refunds WHERE order_id = %s",
            (order_id,),
        )
        return await cur.fetchone(), False


async def search_products(q: str | None, category: str | None, max_price: int | None) -> list[dict]:
    async with _connect() as conn:
        return await repo.search_products(conn, q=q, category=category, max_price=max_price, limit=8)


async def get_product(slug: str) -> dict | None:
    async with _connect() as conn:
        return await repo.get_product(conn, slug)
