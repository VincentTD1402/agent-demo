"""Chống dò tìm đơn hàng và spam đơn trên Postgres thật (cần TEST_DATABASE_URL)."""

import pytest

from app.shop.common import ShopError

PHONE = "0900000001"
ADDRESS = "12 Nguyễn Huệ, Bến Nghé, Quận 1, TP. Hồ Chí Minh"
SESSION = "session-aaaaaaaaaaaa"


def count_failures(pool) -> int:
    with pool.connection() as conn:
        return conn.execute("SELECT count(*) FROM lookup_failures").fetchone()[0]


def test_wrong_phone_five_times_locks_the_code_even_for_the_right_phone(shop, db_pool):
    for _ in range(5):
        with pytest.raises(ShopError, match="Không tìm thấy"):
            shop.orders.get("SM000100", "0911111111")
    assert count_failures(db_pool) >= 5  # lần sai vẫn được ghi dù tra cứu ném lỗi
    with pytest.raises(ShopError, match="quá nhiều lần"):
        shop.orders.get("SM000100", PHONE)
    assert shop.orders.get("SM000102", PHONE)["code"] == "SM000102"  # mã đơn khác của cùng SĐT vẫn tra được


def test_many_wrong_codes_with_one_phone_locks_that_phone(shop):
    for i in range(10):
        with pytest.raises(ShopError, match="Không tìm thấy"):
            shop.orders.get(f"SM9990{i:02d}", PHONE)
    with pytest.raises(ShopError, match="quá nhiều lần"):
        shop.orders.get("SM000100", PHONE)


def test_successful_lookups_never_count_as_failures(shop, db_pool):
    for _ in range(20):
        assert shop.orders.get("SM000100", PHONE)["status"] == "delivered"
    assert count_failures(db_pool) == 0


def test_lock_expires_after_the_window(shop, db_pool):
    for _ in range(5):
        with pytest.raises(ShopError):
            shop.orders.get("SM000100", "0911111111")
    with db_pool.connection() as conn:
        conn.execute("UPDATE lookup_failures SET created_at = now() - interval '16 minutes'")
    assert shop.orders.get("SM000100", PHONE)["code"] == "SM000100"


def test_lock_applies_to_refund_cancel_and_pay_tools(shop):
    for _ in range(5):
        with pytest.raises(ShopError):
            shop.refunds.check("SM000100", "0911111111", "defective")
    for call in (
        lambda: shop.refunds.check("SM000100", PHONE, "defective"),
        lambda: shop.refunds.request("SM000100", PHONE, "defective"),
        lambda: shop.orders.cancel("SM000100", PHONE),
        lambda: shop.orders.pay("SM000100", PHONE),
    ):
        with pytest.raises(ShopError, match="quá nhiều lần"):
            call()


def test_malformed_phone_still_counts_against_the_order_code(shop):
    for _ in range(5):
        with pytest.raises(ShopError, match="Không tìm thấy"):
            shop.orders.get("SM000100", "abc")
    with pytest.raises(ShopError, match="quá nhiều lần"):
        shop.orders.get("SM000100", PHONE)


def test_session_cannot_place_more_than_five_orders_per_hour(shop):
    for _ in range(5):
        shop.cart.add(SESSION, "anker-sac-20w", 1)
        shop.orders.checkout(SESSION, "Nguyễn Văn A", PHONE, ADDRESS, "cod")
    shop.cart.add(SESSION, "anker-sac-20w", 1)
    with pytest.raises(ShopError, match="nhiều đơn"):
        shop.orders.checkout(SESSION, "Nguyễn Văn A", PHONE, ADDRESS, "cod")
    shop.cart.add("session-bbbbbbbbbbbb", "anker-sac-20w", 1)  # phiên khác không bị ảnh hưởng
    assert shop.orders.checkout("session-bbbbbbbbbbbb", "Trần Thị B", "0912345678", ADDRESS, "cod")["code"].startswith("SM")
