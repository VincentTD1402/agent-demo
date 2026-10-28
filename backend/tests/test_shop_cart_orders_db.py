"""Giỏ hàng, chốt đơn, huỷ, thanh toán trên Postgres thật (cần TEST_DATABASE_URL, xem conftest.py)."""

import threading

import pytest

from app.shop.common import ShopError, normalize_phone

S1, S2 = "session-aaaaaaaaaaaa", "session-bbbbbbbbbbbb"
PHONE = "0900000001"  # SĐT của 3 đơn mẫu SM000100-102
ADDRESS = "12 Nguyễn Huệ, Bến Nghé, Quận 1, TP. Hồ Chí Minh"


def set_stock(pool, slug, stock):
    with pool.connection() as conn:
        conn.execute("UPDATE products SET stock = %s WHERE slug = %s", (stock, slug))


def stock_of(pool, slug):
    with pool.connection() as conn:
        return conn.execute("SELECT stock FROM products WHERE slug = %s", (slug,)).fetchone()[0]


def checkout(shop, session=S1, method="cod", phone=PHONE):
    return shop.orders.checkout(session, "Nguyễn Văn A", phone, ADDRESS, method)


def test_cart_totals_and_shipping_threshold(shop):
    cart = shop.cart.add(S1, "anker-sac-20w", 1)
    assert (cart["subtotal_vnd"], cart["shipping_fee_vnd"], cart["total_vnd"]) == (290000, 30000, 320000)
    cart = shop.cart.add(S1, "anker-sac-20w", 1)  # cộng dồn vào dòng cũ
    assert cart["lines"][0]["qty"] == 2 and (cart["subtotal_vnd"], cart["shipping_fee_vnd"]) == (580000, 0)
    assert shop.cart.view(S2)["lines"] == []  # giỏ tách biệt theo phiên


def test_cart_validates_stock_quantity_and_product(shop, db_pool):
    set_stock(db_pool, "sony-wh-1000xm5", 2)
    shop.cart.add(S1, "sony-wh-1000xm5", 2)
    with pytest.raises(ShopError, match="chỉ còn 2"):
        shop.cart.add(S1, "sony-wh-1000xm5", 1)
    with pytest.raises(ShopError, match="tối đa 10"):
        shop.cart.add(S1, "anker-sac-20w", 11)
    with pytest.raises(ShopError, match="Không tìm thấy"):
        shop.cart.add(S1, "khong-co", 1)
    with pytest.raises(ShopError, match="không hợp lệ"):
        shop.cart.add("short", "anker-sac-20w", 1)
    set_stock(db_pool, "lenovo-loq-15-rtx4050", 0)
    with pytest.raises(ShopError, match="hết hàng"):
        shop.cart.add(S1, "lenovo-loq-15-rtx4050", 1)


def test_cart_set_quantity_remove_and_clear(shop):
    shop.cart.add(S1, "anker-sac-20w", 3)
    assert shop.cart.set_quantity(S1, "anker-sac-20w", 1)["lines"][0]["qty"] == 1
    assert shop.cart.set_quantity(S1, "anker-sac-20w", 0)["lines"] == []
    shop.cart.add(S1, "anker-sac-20w", 1)
    assert shop.cart.clear(S1)["lines"] == []


def test_checkout_creates_order_decrements_stock_and_clears_cart(shop, db_pool):
    before = stock_of(db_pool, "iphone-16-128gb")
    shop.cart.add(S1, "iphone-16-128gb", 2)
    order = checkout(shop, phone="+84 900 000 001")
    assert order["code"].startswith("SM") and order["status"] == "processing" and order["payment_status"] == "unpaid"
    assert (order["subtotal_vnd"], order["shipping_fee_vnd"], order["total_vnd"]) == (45980000, 0, 45980000)
    assert order["items"][0]["qty"] == 2 and order["items"][0]["unit_price_vnd"] == 22990000
    assert stock_of(db_pool, "iphone-16-128gb") == before - 2
    assert shop.cart.view(S1)["lines"] == []
    assert shop.orders.get(order["code"].lower(), "0900 000 001")["code"] == order["code"]  # mã không phân biệt hoa thường
    assert [o["code"] for o in shop.orders.list_for_session(S1)] == [order["code"]]


def test_checkout_rejects_bad_input_and_empty_cart(shop):
    with pytest.raises(ShopError, match="trống"):
        checkout(shop)
    shop.cart.add(S1, "anker-sac-20w", 1)
    with pytest.raises(ShopError, match="Số điện thoại"):
        checkout(shop, phone="123")
    with pytest.raises(ShopError, match="Phương thức"):
        shop.orders.checkout(S1, "Nguyễn Văn A", PHONE, ADDRESS, "bitcoin")
    with pytest.raises(ShopError, match="địa chỉ"):
        shop.orders.checkout(S1, "Nguyễn Văn A", PHONE, "abc", "cod")
    assert shop.cart.view(S1)["lines"]  # lỗi thì giỏ giữ nguyên


def test_checkout_rolls_back_when_stock_dropped_after_adding(shop, db_pool):
    shop.cart.add(S1, "anker-sac-20w", 5)
    set_stock(db_pool, "anker-sac-20w", 3)  # có người khác mua trước
    with pytest.raises(ShopError, match="chỉ còn 3"):
        checkout(shop)
    assert stock_of(db_pool, "anker-sac-20w") == 3 and shop.cart.view(S1)["lines"]


def test_concurrent_checkout_of_last_item_sells_exactly_once(shop, db_pool):
    set_stock(db_pool, "sony-wh-1000xm5", 1)
    for session in (S1, S2):
        shop.cart.add(session, "sony-wh-1000xm5", 1)
    results = []

    def run(session):
        try:
            results.append(checkout(shop, session=session)["code"])
        except ShopError as exc:
            results.append(str(exc))

    threads = [threading.Thread(target=run, args=(s,)) for s in (S1, S2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(r.startswith("SM") for r in results) == 1 and sum("hết hàng" in r for r in results) == 1
    assert stock_of(db_pool, "sony-wh-1000xm5") == 0


def test_order_lookup_needs_matching_code_and_phone_with_same_error(shop):
    wrong_phone = pytest.raises(ShopError)
    with wrong_phone as a:
        shop.orders.get("SM000100", "0911111111")
    with pytest.raises(ShopError) as b:
        shop.orders.get("SM999999", PHONE)
    with pytest.raises(ShopError) as c:
        shop.orders.get("SM000100", "abc")
    assert str(a.value) == str(b.value) == str(c.value)
    order = shop.orders.get("SM000100", PHONE)
    assert order["status"] == "delivered" and order["items"][0]["slug"] == "airpods-pro-2-usb-c"


def test_cancel_restores_stock_only_for_unpaid_processing_orders(shop, db_pool):
    shop.cart.add(S1, "anker-sac-20w", 2)
    order = checkout(shop)
    after_order = stock_of(db_pool, "anker-sac-20w")
    assert shop.orders.cancel(order["code"], PHONE)["status"] == "cancelled"
    assert stock_of(db_pool, "anker-sac-20w") == after_order + 2
    with pytest.raises(ShopError, match="đang xử lý"):
        shop.orders.cancel(order["code"], PHONE)  # đã huỷ
    with pytest.raises(ShopError, match="đang xử lý"):
        shop.orders.cancel("SM000101", PHONE)  # đang giao
    shop.cart.add(S1, "anker-sac-20w", 2)
    paid = checkout(shop, method="online")
    shop.orders.pay(paid["code"], PHONE)
    with pytest.raises(ShopError, match="nhân viên"):
        shop.orders.cancel(paid["code"], PHONE)


def test_pay_online_once_and_never_for_cod(shop):
    shop.cart.add(S1, "anker-sac-20w", 1)
    online = checkout(shop, method="online")
    paid = shop.orders.pay(online["code"], PHONE)
    assert paid["payment_status"] == "paid"
    with pytest.raises(ShopError, match="đã được thanh toán"):
        shop.orders.pay(online["code"], PHONE)
    with pytest.raises(ShopError, match="COD"):
        shop.orders.pay("SM000102", PHONE)
    with pytest.raises(ShopError, match="Không tìm thấy"):
        shop.orders.pay(online["code"], "0911111111")


def test_staff_status_flow_and_cod_collected_on_delivery(shop):
    order = shop.orders.get("SM000102", PHONE)  # COD, đang xử lý
    assert order["payment_status"] == "unpaid"
    assert shop.orders.set_status("SM000102", "shipped")["status"] == "shipped"
    with pytest.raises(ShopError, match="Không thể chuyển"):
        shop.orders.set_status("SM000102", "processing")
    done = shop.orders.set_status("SM000102", "delivered")
    assert done["status"] == "delivered" and done["delivered_at"] and done["payment_status"] == "paid"


def test_normalize_phone_variants():
    assert {normalize_phone(p) for p in ("0912345678", "+84 912 345 678", "84912345678", "0912.345.678")} == {"0912345678"}
