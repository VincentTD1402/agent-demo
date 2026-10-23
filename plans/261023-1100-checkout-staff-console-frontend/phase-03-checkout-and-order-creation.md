---
phase: 3
title: "Checkout and order creation"
status: pending
priority: P1
effort: "4d"
milestone: "M2"
dependencies: ["261023-1010-backend-alembic-and-langgraph-agent#3", "261023-1010-backend-alembic-and-langgraph-agent#4", "261023-1100-checkout-staff-console-frontend#1"]
---

# Phase 3: Checkout and order creation

## Overview

Tạo đơn thật từ giỏ hàng: giá và tồn kho do server quyết định, idempotent, trừ tồn trong transaction, địa chỉ nhập thẳng vào đơn (không có sổ địa chỉ), trang thanh toán và lịch sử đơn.

## Requirements

- Functional: xem giá/phí ship từ server, tạo đơn idempotent, trang "Đơn hàng của tôi".
- Non-functional: không tin giá/tổng từ client; không bán vượt tồn kho; không thể giữ tồn kho vô hạn.

## Architecture

- **Schema do Plan A phase 3 sở hữu** (`orders` đã có `subtotal_vnd, shipping_fee_vnd, note, expires_at, stock_released_at, idempotency_key, request_hash`, `UNIQUE(user_id, idempotency_key)`, `shipping_address` jsonb là bản chụp lúc đặt). Phase này **không** tạo bảng `addresses` và không tạo lại cột đơn hàng.
- **Giá/phí ship chỉ lấy từ server:** `POST /v1/checkout/price {items}` (cùng module `pricing.py` với tạo đơn) trả dòng hàng, tạm tính, phí ship (cấu hình `SHIPPING_FEE_VND=30000`, miễn phí từ `FREE_SHIPPING_FROM_VND=500000`; người dùng xác nhận), cảnh báo hết hàng/đổi giá/sản phẩm ngừng bán. Giỏ hàng và trang checkout đều gọi endpoint này; **xoá hằng số `FREE_SHIP_FROM`/`SHIP_FEE` ở `cart-page.tsx`**.
- `POST /v1/orders {items:[{slug,qty}], shipping_address, note, expected_total_vnd, payment_method}` + header `Idempotency-Key`:
  - validate: `1 ≤ qty ≤ 10`, không trùng slug, sản phẩm `is_active`; `expected_total_vnd` khác tổng server → **409** kèm giá mới;
  - idempotency: client sinh key khi vào trang checkout, giữ trong sessionStorage, đổi sau khi thành công hoặc khi giỏ thay đổi; server lưu `request_hash`; cùng key cùng hash → trả đơn cũ, cùng key khác hash → 422; unique `(user_id, key)`;
  - một transaction qua helper **`inventory.reserve(order)`**: khoá `products` theo id tăng dần, kiểm tồn, `stock = stock - qty`, chụp giá/tên vào `order_items`, tạo `orders` + payment (phase 4); lỗi `40001/40P01` thì retry.
- **Chống giữ tồn kho:** tối đa 3 đơn `pending_payment` chưa trả mỗi người dùng; rate limit `price`, `orders`, `mark-transferred` (module chung của Plan A phase 4); đơn COD bắt đầu `processing` (không giữ tồn vô hạn ở trạng thái chờ).
- Quy tắc thứ tự khoá toàn hệ thống: **orders → payments → products theo id** (áp dụng cho tạo đơn, huỷ, hết hạn, xác nhận).
- **Backfill:** migration dữ liệu tạo một `payments` cho mọi đơn có sẵn/seed (COD đã giao → `paid`; còn lại ánh xạ xác định, ghi trong migration) để `lookup_order` và chi trả hoàn tiền không gặp đơn thiếu payment.
- Frontend: `/thanh-toan` (địa chỉ nhập tay có kiểm tra, phương thức, tóm tắt giá từ server), `/don-hang/:id`, `/tai-khoan/don-hang` (mốc thời gian). Nút "ĐẶT HÀNG" ở `cart-page.tsx:63` và đường vào từ `cart-drawer.tsx` đều dẫn tới checkout.

## Related Code Files

- Create: `backend/app/checkout/{service,pricing,schemas}.py`, `backend/app/inventory/service.py`, `backend/app/api/routes_{checkout,orders}.py`, migration `backfill_payments` (sau migration `payments` ở phase 4), `frontend/src/pages/{checkout-page,order-detail-page,my-orders-page}.tsx`, `frontend/src/checkout/*`
- Modify: `frontend/src/pages/cart-page.tsx`, `frontend/src/components/cart-drawer.tsx`, `frontend/src/lib/cart.tsx`, `backend/app/db/models/order.py` (chỉ đọc), `backend/app/mcp_server/tools/orders.py` (Plan A phase 5: hiển thị phí ship/trạng thái thanh toán)

## Implementation Steps

1. `pricing.py` (+ test bảng: phí ship, ngưỡng, giá đổi) và `inventory.reserve` (+ test đua).
2. `service.create_order`: validate, idempotency, transaction, retry deadlock.
3. Route `price`/`orders` (mọi truy vấn lọc theo `user_id` JWT) + giới hạn số đơn chưa trả + rate limit.
4. Frontend checkout: key trong sessionStorage, xử lý 409 đổi giá/hết hàng (cập nhật giỏ rồi báo rõ), xoá hằng số phí ship cũ, nối `cart-drawer`.
5. Migration backfill payments + test trên dữ liệu seed.
6. Test: hai người mua sản phẩm còn 1 → đúng 1 đơn; double-click/gửi lại cùng key → 1 đơn; cùng key khác hash → 422; giá giả/`expected_total` sai → 409; slug trùng/qty vượt bị từ chối; vượt 3 đơn chưa trả bị chặn; IDOR đơn người khác.

## Todo List

- [ ] pricing + inventory helper + test đua
- [ ] create_order + idempotency + giới hạn
- [ ] Frontend checkout + cart/cart-drawer
- [ ] Backfill payments + test
- [ ] Test IDOR, giá giả, double submit

## Success Criteria

- [ ] Không thể tạo đơn với giá/tổng do client gửi; client không còn hằng số phí ship
- [ ] Test đua tồn kho và idempotency pass
- [ ] Khách chỉ thấy đơn của mình; đơn cũ/seed không làm gãy `lookup_order`

## Risk Assessment

Deadlock khi khoá nhiều sản phẩm → khoá theo id tăng dần + retry. Địa chỉ nhập tay tự do (danh mục hành chính để sau). Giá thay đổi giữa lúc xem và đặt → 409 có giá mới.

## Security Considerations

Giá/tồn/phí ship server-authoritative; idempotency theo `(user_id, key)` chống IDOR; giới hạn số đơn chưa trả + rate limit chống DoS giữ tồn; địa chỉ là PII (chỉ chủ đơn và staff đọc, `mcp` không đọc).

## Next Steps

Phase 4 (thanh toán) gắn payment vào đơn; phase 6 xử lý huỷ/hết hạn dùng `inventory.release`.
