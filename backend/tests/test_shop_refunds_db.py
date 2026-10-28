"""Hoàn tiền theo chính sách (7 ngày kể từ ngày giao, nhân viên duyệt) trên Postgres thật."""

import pytest

from app.shop.common import ShopError

PHONE = "0900000001"
DELIVERED = "SM000100"  # AirPods Pro 2, đã giao 2 ngày trước, 5.490.000₫ (miễn phí ship)


def age_delivery(pool, code, days):
    with pool.connection() as conn:
        conn.execute("UPDATE orders SET delivered_at = now() - make_interval(days => %s) WHERE code = %s", (days, code))


def test_check_eligible_within_window_returns_full_amount_and_deadline(shop):
    result = shop.refunds.check(DELIVERED, PHONE, "defective")
    assert result["eligible"] and result["amount_vnd"] == 5490000 and result["deadline"]


def test_check_is_read_only(shop, db_pool):
    shop.refunds.check(DELIVERED, PHONE, "defective")
    with db_pool.connection() as conn:
        assert conn.execute("SELECT count(*) FROM refund_requests").fetchone()[0] == 0


def test_changed_mind_is_never_eligible(shop):
    result = shop.refunds.check(DELIVERED, PHONE, "changed_mind")
    assert not result["eligible"] and "Đổi ý" in result["reason"]
    with pytest.raises(ShopError, match="Đổi ý"):
        shop.refunds.request(DELIVERED, PHONE, "changed_mind")


def test_not_delivered_orders_are_not_eligible(shop):
    for code in ("SM000101", "SM000102"):  # đang giao, đang xử lý
        assert "đã giao" in shop.refunds.check(code, PHONE, "defective")["reason"]


def test_expired_window_is_rejected(shop, db_pool):
    age_delivery(db_pool, DELIVERED, 8)
    result = shop.refunds.check(DELIVERED, PHONE, "defective")
    assert not result["eligible"] and "quá hạn" in result["reason"]
    age_delivery(db_pool, DELIVERED, 6)  # vẫn trong hạn 7 ngày
    assert shop.refunds.check(DELIVERED, PHONE, "defective")["eligible"]


def test_wrong_phone_or_unknown_order_look_identical(shop):
    with pytest.raises(ShopError) as a:
        shop.refunds.check(DELIVERED, "0911111111", "defective")
    with pytest.raises(ShopError) as b:
        shop.refunds.check("SM999999", PHONE, "defective")
    assert str(a.value) == str(b.value)
    with pytest.raises(ShopError, match="Lý do"):
        shop.refunds.check(DELIVERED, PHONE, "because")


def test_request_creates_pending_only_and_blocks_duplicates(shop, db_pool):
    refund = shop.refunds.request(DELIVERED, PHONE, "defective", "Tai nghe bên trái không có tiếng")
    assert refund["status"] == "pending" and refund["amount_vnd"] == 5490000
    with db_pool.connection() as conn:  # chưa hoàn tiền thật: đơn vẫn 'paid'
        assert conn.execute("SELECT payment_status FROM orders WHERE code = %s", (DELIVERED,)).fetchone()[0] == "paid"
    with pytest.raises(ShopError, match="đang xử lý"):
        shop.refunds.request(DELIVERED, PHONE, "defective")
    assert shop.orders.get(DELIVERED, PHONE)["refund"]["status"] == "pending"


def test_staff_approve_marks_full_refund(shop):
    refund_id = shop.refunds.request(DELIVERED, PHONE, "not_as_described")["refund_id"]
    pending = shop.refunds.list_pending()
    assert [p["id"] for p in pending] == [refund_id] and pending[0]["order_code"] == DELIVERED and pending[0]["phone"] == PHONE
    assert shop.refunds.decide(refund_id, True, "Đã xác nhận qua điện thoại")["status"] == "approved"
    order = shop.orders.get(DELIVERED, PHONE)
    assert order["payment_status"] == "refunded" and order["refund"]["status"] == "approved"
    assert shop.refunds.list_pending() == []
    with pytest.raises(ShopError, match="đã được xử lý"):
        shop.refunds.decide(refund_id, False)
    with pytest.raises(ShopError, match="đã có yêu cầu"):  # đã hoàn rồi thì không xin lại được
        shop.refunds.request(DELIVERED, PHONE, "defective")


def test_staff_reject_allows_new_request(shop):
    first = shop.refunds.request(DELIVERED, PHONE, "defective")["refund_id"]
    assert shop.refunds.decide(first, False, "Không thấy lỗi")["status"] == "rejected"
    assert shop.orders.get(DELIVERED, PHONE)["payment_status"] == "paid"
    assert shop.refunds.request(DELIVERED, PHONE, "defective")["status"] == "pending"


def test_partial_refund_covers_only_selected_items_without_shipping(shop):
    shop.cart.add("session-aaaaaaaaaaaa", "anker-sac-20w", 1)  # 290.000₫
    shop.cart.add("session-aaaaaaaaaaaa", "pin-du-phong-anker-10000", 1)  # 690.000₫ -> tổng 980.000₫, ship 0
    order = shop.orders.checkout("session-aaaaaaaaaaaa", "Nguyễn Văn A", PHONE, "12 Nguyễn Huệ, Quận 1, TP.HCM", "online")
    shop.orders.pay(order["code"], PHONE)
    shop.orders.set_status(order["code"], "shipped")
    shop.orders.set_status(order["code"], "delivered")
    assert shop.refunds.check(order["code"], PHONE, "defective", ["anker-sac-20w"])["amount_vnd"] == 290000
    assert shop.refunds.check(order["code"], PHONE, "defective", ["anker-sac-20w", "pin-du-phong-anker-10000"])["amount_vnd"] == 980000
    with pytest.raises(ShopError, match="không thuộc đơn"):
        shop.refunds.check(order["code"], PHONE, "defective", ["iphone-16-128gb"])
    refund_id = shop.refunds.request(order["code"], PHONE, "defective", item_slugs=["anker-sac-20w"])["refund_id"]
    shop.refunds.decide(refund_id, True)
    assert shop.orders.get(order["code"], PHONE)["payment_status"] == "paid"  # hoàn một phần: đơn vẫn 'paid'
