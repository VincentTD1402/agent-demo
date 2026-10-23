"""Công cụ MCP issue_refund trên Postgres thật: kết quả phản ánh đúng trạng thái "chờ nhân viên", hạn hoàn, trần tiền."""
import psycopg

from app.shop.seed_data import (
    DEMO_CUSTOMER_ID, ORDER_COD_ID, ORDER_OTHER_CUSTOMER_ID, ORDER_REFUND_ELIGIBLE_ID, ORDER_SHIPPED_ID,
)

A100_GOODS = 5490000  # đơn A100 miễn phí ship: tiền hàng == tổng đơn


def _add_order(settings, order_id: str, goods: int, shipping: int = 0, delivered_days_ago: int | None = 1) -> None:
    """Đơn đã giao (hoặc đang xử lý nếu delivered_days_ago None) của khách demo với một dòng hàng giá `goods`."""
    with psycopg.connect(settings.migrator_database_url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO orders (id, user_id, status, subtotal_vnd, shipping_fee_vnd, total_vnd, shipping_address,"
            " delivered_at) VALUES (%s, %s, %s, %s, %s, %s, '{}', now() - %s * interval '1 day')",
            (order_id, DEMO_CUSTOMER_ID, "delivered" if delivered_days_ago is not None else "processing",
             goods, shipping, goods + shipping, delivered_days_ago),
        )
        conn.execute(
            "INSERT INTO order_items (order_id, product_id, product_name, unit_price_vnd, qty)"
            " SELECT %s, id, 'Hàng thử', %s, 1 FROM products WHERE slug = 'iphone-16-128gb'",
            (order_id, goods),
        )


def _sql(settings, query: str, params=()):
    with psycopg.connect(settings.migrator_database_url, autocommit=True) as conn:
        cur = conn.execute(query, params)
        return cur.fetchall() if cur.description else None


def test_issue_refund_reports_pending_staff_and_is_idempotent(run_with_mcp, bootstrapped_db):
    async def scenario(tools):
        first = await tools.issue_refund(ORDER_REFUND_ELIGIBLE_ID, DEMO_CUSTOMER_ID, A100_GOODS, "Lỗi sản phẩm")
        assert first["ok"] is True and first["status"] == "pending_staff" and first["already_requested"] is False
        assert first["message_key"] == "refund_request_submitted"
        assert first["order_id"] == ORDER_REFUND_ELIGIBLE_ID and first["amount_vnd"] == A100_GOODS
        assert first["request_id"] and "CHƯA" in first["message"] and "đã hoàn" not in first["message"].lower()
        assert "already_refunded" not in first

        again = await tools.issue_refund(ORDER_REFUND_ELIGIBLE_ID, DEMO_CUSTOMER_ID, 1, "gọi lại")
        assert again["ok"] is True and again["already_requested"] is True and again["status"] == "pending_staff"
        assert again["request_id"] == first["request_id"] and again["amount_vnd"] == A100_GOODS
        assert again["message_key"] == "refund_request_already_pending_staff"

        rows = _sql(bootstrapped_db, "SELECT status, source, requested_amount_vnd, user_id::text FROM refunds")
        assert rows == [("pending_staff", "customer_request", A100_GOODS, DEMO_CUSTOMER_ID)]
        order = await tools.lookup_order(ORDER_REFUND_ELIGIBLE_ID, DEMO_CUSTOMER_ID)
        assert order["refunded_vnd"] is None, "chưa chi trả thì không được báo là đã hoàn"
        assert order["pending_refund_vnd"] == A100_GOODS and order["refund_status"] == "pending_staff"

    run_with_mcp(scenario)


def test_lookup_reports_refunded_only_after_payout(run_with_mcp, bootstrapped_db):
    async def scenario(tools):
        await tools.issue_refund(ORDER_REFUND_ELIGIBLE_ID, DEMO_CUSTOMER_ID, 1000, "x")
        _sql(bootstrapped_db, "UPDATE refunds SET status = 'approved', approved_amount_vnd = 800,"
                              " decided_by = user_id, decided_at = now()")
        approved = await tools.lookup_order(ORDER_REFUND_ELIGIBLE_ID, DEMO_CUSTOMER_ID)
        assert approved["refunded_vnd"] is None and approved["pending_refund_vnd"] == 800
        assert approved["refund_status"] == "approved"
        assert (await tools.issue_refund(ORDER_REFUND_ELIGIBLE_ID, DEMO_CUSTOMER_ID, 5, "x"))["status"] == "approved"

        _sql(bootstrapped_db, "UPDATE refunds SET status = 'paid_out', payout_reference = 'REF-1'")
        paid = await tools.lookup_order(ORDER_REFUND_ELIGIBLE_ID, DEMO_CUSTOMER_ID)
        assert paid["refunded_vnd"] == 800 and paid["pending_refund_vnd"] is None and paid["refund_status"] == "paid_out"
        again = await tools.issue_refund(ORDER_REFUND_ELIGIBLE_ID, DEMO_CUSTOMER_ID, 5, "x")
        assert again["ok"] is True and again["already_requested"] is True
        assert again["message_key"] == "refund_request_already_paid_out"

    run_with_mcp(scenario)


def test_issue_refund_rejects_ineligible_requests(run_with_mcp, bootstrapped_db):
    async def scenario(tools):
        expected = {
            ORDER_SHIPPED_ID: "order_not_delivered", ORDER_COD_ID: "order_not_delivered",
            ORDER_OTHER_CUSTOMER_ID: "order_not_found", "NOPE": "order_not_found",
        }
        for order_id, key in expected.items():
            result = await tools.issue_refund(order_id, DEMO_CUSTOMER_ID, 100, "x")
            assert result["ok"] is False and result["message_key"] == key, order_id
        for amount in (0, -5, A100_GOODS + 1):
            result = await tools.issue_refund(ORDER_REFUND_ELIGIBLE_ID, DEMO_CUSTOMER_ID, amount, "x")
            assert result["ok"] is False and result["message_key"] == "amount_out_of_range", amount
        assert _sql(bootstrapped_db, "SELECT count(*) FROM refunds") == [(0,)]

    run_with_mcp(scenario)


def test_refund_window_boundary_day_7_ok_day_8_refused(run_with_mcp, bootstrapped_db):
    _add_order(bootstrapped_db, "W7", 100000, delivered_days_ago=7)
    _add_order(bootstrapped_db, "W8", 100000, delivered_days_ago=8)

    async def scenario(tools):
        ok = await tools.issue_refund("W7", DEMO_CUSTOMER_ID, 100000, "x")
        assert ok["ok"] is True and ok["status"] == "pending_staff"
        late = await tools.issue_refund("W8", DEMO_CUSTOMER_ID, 100000, "x")
        assert late["ok"] is False and late["message_key"] == "refund_window_expired" and "7 ngày" in late["message"]

    run_with_mcp(scenario)


def test_refund_cap_is_goods_amount_excluding_shipping(run_with_mcp, bootstrapped_db):
    _add_order(bootstrapped_db, "S1", goods=100000, shipping=30000)  # tổng đơn 130000

    async def scenario(tools):
        for amount in (130000, 100001):
            result = await tools.issue_refund("S1", DEMO_CUSTOMER_ID, amount, "x")
            assert result["ok"] is False and result["message_key"] == "amount_out_of_range", amount
            assert "100000" in result["message"]
        assert (await tools.issue_refund("S1", DEMO_CUSTOMER_ID, 100000, "x"))["ok"] is True

    run_with_mcp(scenario)


def test_refund_cap_subtracts_amounts_already_committed(run_with_mcp, bootstrapped_db):
    _add_order(bootstrapped_db, "C1", goods=100000)
    _sql(bootstrapped_db,
         "INSERT INTO refunds (order_id, user_id, source, requested_amount_vnd, reason, idempotency_key)"
         " VALUES ('C1', %s, 'system_cancel_paid', 40000, 'huỷ đơn', 'sys-1')", (DEMO_CUSTOMER_ID,))

    async def scenario(tools):
        too_much = await tools.issue_refund("C1", DEMO_CUSTOMER_ID, 60001, "x")
        assert too_much["ok"] is False and "60000" in too_much["message"]
        assert (await tools.issue_refund("C1", DEMO_CUSTOMER_ID, 60000, "x"))["ok"] is True

    run_with_mcp(scenario)


def test_resubmit_allowed_after_staff_rejection(run_with_mcp, bootstrapped_db):
    async def scenario(tools):
        await tools.issue_refund(ORDER_REFUND_ELIGIBLE_ID, DEMO_CUSTOMER_ID, 1000, "lần 1")
        _sql(bootstrapped_db, "UPDATE refunds SET status = 'rejected', decided_by = user_id, decided_at = now()")
        second = await tools.issue_refund(ORDER_REFUND_ELIGIBLE_ID, DEMO_CUSTOMER_ID, 2000, "lần 2")
        assert second["already_requested"] is False and second["amount_vnd"] == 2000

    run_with_mcp(scenario)


def test_policy_text_states_window_cap_and_that_staff_decides(run_with_mcp):
    async def scenario(tools):
        policy = await tools.get_refund_policy()
        for needle in ("7 ngày", "không gồm phí vận chuyển", "nhân viên", "CHƯA được hoàn", "đã thanh toán"):
            assert needle in policy, needle
        assert "mỗi đơn hoàn một lần" not in policy

    run_with_mcp(scenario)
