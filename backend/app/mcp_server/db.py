"""Truy vấn dữ liệu shop (Postgres) cho các công cụ MCP."""
import asyncio
import uuid
from contextlib import asynccontextmanager

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.settings.mcp import get_mcp_settings
from app.shop import repo

_pool: AsyncConnectionPool | None = None
_pool_lock = asyncio.Lock()

# Yêu cầu hoàn tiền "sống": đang chờ nhân viên, đã duyệt (chờ chi trả) hoặc đã chi trả
_LIVE = "('pending_staff', 'approved', 'paid_out')"
# Ngày theo giờ cửa hàng: "ngày thứ 7 sau khi giao" tính theo lịch Việt Nam, không theo UTC
_SHOP_TZ = "Asia/Ho_Chi_Minh"


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


def _as_uuid(value: str) -> uuid.UUID | None:
    """user_id từ agent là chuỗi; không phải UUID thì coi như không khớp khách nào."""
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def get_order(order_id: str, user_id: str) -> dict | None:
    """Chỉ trả đơn thuộc đúng user_id để khách không xem được đơn người khác.

    Đọc qua view orders_for_agent (role mcp không có quyền trên bảng orders nên không thấy địa chỉ giao).
    `refunded_vnd` chỉ có giá trị khi tiền ĐÃ chi trả (paid_out); `pending_refund_vnd` là số tiền đang chờ nhân viên
    duyệt/chi trả; `refund_status` là trạng thái của yêu cầu "sống" mới nhất."""
    owner = _as_uuid(user_id)
    if owner is None:
        return None
    async with _connect() as conn:
        cur = await conn.execute(
            f"""SELECT o.id, o.status, o.total_vnd, o.created_at,
                      COALESCE((SELECT jsonb_agg(jsonb_build_object('name', i.product_name, 'qty', i.qty)
                                                 ORDER BY i.product_id)
                                FROM order_items i WHERE i.order_id = o.id), '[]'::jsonb) AS items,
                      (SELECT sum(r.approved_amount_vnd)::bigint FROM refunds r
                        WHERE r.order_id = o.id AND r.status = 'paid_out') AS refunded_vnd,
                      (SELECT sum(COALESCE(r.approved_amount_vnd, r.requested_amount_vnd))::bigint FROM refunds r
                        WHERE r.order_id = o.id AND r.status IN ('pending_staff', 'approved')) AS pending_refund_vnd,
                      (SELECT r.status FROM refunds r WHERE r.order_id = o.id AND r.status IN {_LIVE}
                        ORDER BY r.created_at DESC LIMIT 1) AS refund_status
               FROM orders_for_agent o
               WHERE o.id = %s AND o.user_id = %s""",  # noqa: S608 - hằng số cố định, không có đầu vào người dùng
            (order_id, owner),
        )
        return await cur.fetchone()


async def get_refund_basis(order_id: str, user_id: str) -> dict | None:
    """Dữ kiện kiểm tra điều kiện hoàn tiền: số ngày kể từ lúc giao, tiền hàng (không gồm phí ship), số tiền đã hoặc
    đang hoàn ("sống", mọi nguồn) và yêu cầu "sống" của khách hiện có (nguồn customer_request). None nếu đơn không thuộc khách này."""
    owner = _as_uuid(user_id)
    if owner is None:
        return None
    async with _connect() as conn:
        cur = await conn.execute(
            f"""SELECT (now() AT TIME ZONE %(tz)s)::date - (o.delivered_at AT TIME ZONE %(tz)s)::date
                          AS days_since_delivered,
                      (SELECT COALESCE(sum(i.unit_price_vnd * i.qty), 0)::bigint FROM order_items i
                        WHERE i.order_id = o.id) AS goods_vnd,
                      (SELECT COALESCE(sum(COALESCE(r.approved_amount_vnd, r.requested_amount_vnd)), 0)::bigint
                         FROM refunds r WHERE r.order_id = o.id AND r.status IN {_LIVE}) AS committed_vnd,
                      (SELECT jsonb_build_object('id', r.id, 'status', r.status, 'amount_vnd', r.requested_amount_vnd)
                         FROM refunds r WHERE r.order_id = o.id AND r.source = 'customer_request'
                          AND r.status IN {_LIVE} ORDER BY r.created_at DESC LIMIT 1) AS live_request
               FROM orders_for_agent o WHERE o.id = %(order)s AND o.user_id = %(owner)s""",  # noqa: S608
            {"tz": _SHOP_TZ, "order": order_id, "owner": owner},
        )
        return await cur.fetchone()


async def create_refund(order_id: str, user_id: str, amount_vnd: int, reason: str) -> tuple[dict, bool]:
    """Tạo yêu cầu hoàn tiền chờ nhân viên duyệt, idempotent theo đơn: mỗi đơn tối đa một yêu cầu "sống" của khách
    (chỉ mục duy nhất một phần). status luôn là 'pending_staff' vì role mcp không có quyền đặt cột này.
    Trả (bản ghi, is_new)."""
    owner = _as_uuid(user_id)
    if owner is None:
        raise ValueError("user_id không phải UUID hợp lệ")
    async with _connect() as conn:
        cur = await conn.execute(
            f"""INSERT INTO refunds (order_id, user_id, source, requested_amount_vnd, reason, idempotency_key)
               VALUES (%s, %s, 'customer_request', %s, %s, %s)
               ON CONFLICT (order_id) WHERE source = 'customer_request' AND status IN {_LIVE} DO NOTHING
               RETURNING id, order_id, status, requested_amount_vnd AS amount_vnd""",  # noqa: S608
            (order_id, owner, amount_vnd, reason, f"mcp:{uuid.uuid4()}"),
        )
        row = await cur.fetchone()
        if row:
            return row, True
        cur = await conn.execute(
            f"""SELECT id, order_id, status, requested_amount_vnd AS amount_vnd FROM refunds
               WHERE order_id = %s AND source = 'customer_request' AND status IN {_LIVE}""",  # noqa: S608
            (order_id,),
        )
        return await cur.fetchone(), False


async def search_products(q: str | None, category: str | None, max_price: int | None) -> list[dict]:
    async with _connect() as conn:
        return await repo.search_products(conn, q=q, category=category, max_price=max_price, limit=8)


async def get_product(slug: str) -> dict | None:
    async with _connect() as conn:
        return await repo.get_product(conn, slug)
