"""REST cho storefront (giỏ hàng theo phiên) và cho nhân viên (duyệt hoàn tiền, cập nhật trạng thái đơn).

Giỏ hàng xác định bằng header `X-Session-Id` (UUID ngẫu nhiên do trình duyệt sinh), cùng khoá mà agent dùng cho tool,
nhờ vậy món agent thêm vào giỏ hiện ngay trên giao diện. API nhân viên cần header `X-Staff-Key`.
"""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.settings import Settings, get_settings
from app.shop.services import ShopServices

cart_router = APIRouter(prefix="/cart", tags=["cart"])
staff_router = APIRouter(prefix="/staff", tags=["staff"])


def get_shop(request: Request) -> ShopServices:
    return request.app.state.shop


def session_id_header(x_session_id: str = Header(default="")) -> str:
    return x_session_id  # định dạng được kiểm tra trong CartService (ShopError -> 400)


class CartLineOut(BaseModel):
    slug: str
    name: str
    category: str
    price_vnd: int
    image_url: str | None
    qty: int
    stock: int
    line_total_vnd: int


class CartOut(BaseModel):
    lines: list[CartLineOut]
    subtotal_vnd: int
    shipping_fee_vnd: int
    total_vnd: int
    out_of_stock: list[str]


class AddItemIn(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    qty: int = Field(default=1, ge=1, le=10)


class SetQtyIn(BaseModel):
    qty: int = Field(ge=0, le=10)


@cart_router.get("", response_model=CartOut)
def view_cart(session_id: str = Depends(session_id_header), shop: ShopServices = Depends(get_shop)) -> dict:
    return shop.cart.view(session_id)


@cart_router.post("/items", response_model=CartOut)
def add_item(body: AddItemIn, session_id: str = Depends(session_id_header), shop: ShopServices = Depends(get_shop)) -> dict:
    return shop.cart.add(session_id, body.slug, body.qty)


@cart_router.put("/items/{slug}", response_model=CartOut)
def set_item_quantity(
    slug: str, body: SetQtyIn, session_id: str = Depends(session_id_header), shop: ShopServices = Depends(get_shop)
) -> dict:
    return shop.cart.set_quantity(session_id, slug, body.qty)


@cart_router.delete("/items/{slug}", response_model=CartOut)
def remove_item(slug: str, session_id: str = Depends(session_id_header), shop: ShopServices = Depends(get_shop)) -> dict:
    return shop.cart.remove(session_id, slug)


def require_staff(x_staff_key: str | None = Header(default=None), settings: Settings = Depends(get_settings)) -> None:
    if not settings.staff_api_key:
        raise HTTPException(status_code=503, detail="API nhân viên chưa được bật (STAFF_API_KEY trống)")
    if not hmac.compare_digest(x_staff_key or "", settings.staff_api_key):
        raise HTTPException(status_code=401, detail="Thiếu hoặc sai X-Staff-Key")


class RefundDecisionIn(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=500)


class OrderStatusIn(BaseModel):
    status: str = Field(pattern="^(shipped|delivered)$")


@staff_router.get("/refunds", dependencies=[Depends(require_staff)])
def pending_refunds(shop: ShopServices = Depends(get_shop)) -> list[dict]:
    return shop.refunds.list_pending()


@staff_router.post("/refunds/{refund_id}/decision", dependencies=[Depends(require_staff)])
def decide_refund(refund_id: int, body: RefundDecisionIn, shop: ShopServices = Depends(get_shop)) -> dict:
    return shop.refunds.decide(refund_id, body.approve, body.note)


@staff_router.post("/orders/{code}/status", dependencies=[Depends(require_staff)])
def set_order_status(code: str, body: OrderStatusIn, shop: ShopServices = Depends(get_shop)) -> dict:
    return shop.orders.set_status(code, body.status)
