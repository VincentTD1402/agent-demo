"""Truy vấn sản phẩm dùng chung cho REST API và công cụ MCP (nhận sẵn một connection dict_row)."""

_COLS = "slug, name, category, brand, price_vnd, old_price_vnd, rating, stock, specs, description, image_url"


async def search_products(
    conn, q: str | None = None, category: str | None = None,
    max_price: int | None = None, limit: int = 20,
) -> list[dict]:
    where, params = ["TRUE"], []
    if q:
        where.append("(name ILIKE %s OR brand ILIKE %s OR description ILIKE %s)")
        params += [f"%{q}%"] * 3
    if category:
        where.append("category = %s")
        params.append(category)
    if max_price is not None:
        where.append("price_vnd <= %s")
        params.append(max_price)
    params.append(min(limit, 50))
    cur = await conn.execute(
        f"SELECT {_COLS} FROM products WHERE {' AND '.join(where)} ORDER BY id LIMIT %s", params
    )
    return await cur.fetchall()


async def get_product(conn, slug: str) -> dict | None:
    cur = await conn.execute(f"SELECT {_COLS} FROM products WHERE slug = %s", (slug,))
    return await cur.fetchone()
