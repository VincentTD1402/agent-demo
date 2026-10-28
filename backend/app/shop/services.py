"""Gom các dịch vụ nghiệp vụ cửa hàng để MCP server và API (REST giỏ hàng, nhân viên) dùng chung một bản cài đặt."""

from dataclasses import dataclass

from psycopg_pool import ConnectionPool

from app.products.repository import PgProductRepository
from app.settings import Settings
from app.shop.cart import CartService
from app.shop.common import ShopPolicy
from app.shop.lookup_guard import LookupGuard
from app.shop.orders import OrderService
from app.shop.payments import PaymentGateway, SimulatedPaymentGateway
from app.shop.refunds import RefundService


@dataclass(frozen=True)
class ShopServices:
    products: PgProductRepository
    cart: CartService
    orders: OrderService
    refunds: RefundService


def build_shop_services(settings: Settings, pool: ConnectionPool, gateway: PaymentGateway | None = None) -> ShopServices:
    policy = ShopPolicy.from_settings(settings)
    guard = LookupGuard(pool, policy)
    return ShopServices(
        products=PgProductRepository(pool),
        cart=CartService(pool, policy),
        orders=OrderService(pool, policy, gateway or SimulatedPaymentGateway(), guard),
        refunds=RefundService(pool, policy, guard),
    )
