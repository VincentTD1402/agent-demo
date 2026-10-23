---
phase: 6
title: "Order lifecycle"
status: pending
priority: P1
effort: "2.5d"
milestone: "M2"
dependencies: ["261023-1100-checkout-staff-console-frontend#3", "261023-1100-checkout-staff-console-frontend#4", "261023-1010-backend-alembic-and-langgraph-agent#7"]
---

# Phase 6: Order lifecycle

## Overview

Một máy trạng thái đơn hàng duy nhất kèm các bất biến với thanh toán, huỷ đơn an toàn (kể cả đã thanh toán), hết hạn đơn chuyển khoản, và thông báo.

## Requirements

- Functional: chuyển trạng thái hợp lệ, khách huỷ trong điều kiện cho phép, huỷ đơn đã thanh toán tạo hoàn tiền, tự huỷ đơn chuyển khoản quá hạn, thông báo.
- Non-functional: tồn kho luôn nhất quán; thao tác nền idempotent; không đua với nhân viên xác nhận thanh toán.

## Architecture

**Bảng chuyển trạng thái** (nằm trong `orders/state_machine.py`, kiểm bằng test và ràng buộc):

| Từ → Đến | Điều kiện | Ai |
|----------|-----------|----|
| (tạo) COD → `processing` | payment `cod` `pending`, `expires_at = NULL` | hệ thống |
| (tạo) chuyển khoản → `pending_payment` | payment `bank_transfer` `pending`, `expires_at = +24h` | hệ thống |
| `pending_payment` → `processing` | payment `paid` | nhân viên (xác nhận) |
| `pending_payment` → `cancelled` | khách/nhân viên/hết hạn; trả tồn | khách, staff, worker |
| `processing` → `shipped` | chuyển khoản: payment `paid`; COD: luôn được; nhập hãng + mã vận đơn | staff |
| `processing` → `cancelled` | trả tồn; nếu payment `paid` → **tạo refund `source=system_cancel_paid`, `pending_staff`** | khách (trước `shipped`), staff |
| `shipped` → `delivered` | ghi `delivered_at` (một lần, có audit) | staff |
| `shipped` → `cancelled` | "giao thất bại/khách từ chối nhận": hàng về kho, trả tồn; nếu payment `paid` → refund hệ thống | staff |
| COD `paid` | chỉ khi đơn `delivered`, nhân viên bấm "đã thu" | staff |

Không chuyển lùi; `delivered` chỉ đi từ `shipped`; mọi chuyển ghi `status_events` (actor, ghi chú); nhân viên không thao tác trên đơn của chính mình.

- **Hết hạn:** job chọn `status = pending_payment AND payment.method = bank_transfer AND payment.status = pending AND expires_at < now()` (đồng hồ DB), xử lý **từng đơn một transaction**, `FOR UPDATE SKIP LOCKED`, thứ tự khoá orders → payments → products; **không đụng payment `awaiting_confirmation`**. Nếu nhân viên xác nhận trên đơn đã `cancelled` → 409 và nhân viên dùng "ghi nhận tiền đã nhận" để tạo refund hệ thống.
- **`inventory.release(order)`** dùng cho huỷ/hết hạn/giao thất bại: khoá sản phẩm theo id, `stock = stock + qty`, đặt `orders.stock_released_at` (bảo đảm trả đúng một lần), retry `40001/40P01`.
- **Thông báo (chỉ các loại đã chốt):** `refund_decided`, `refund_paid_out`, `payment_confirmed`, `payment_rejected`, `ticket_updated`; kèm bảng ánh xạ loại → tiêu đề/nội dung tiếng Việt và liên kết. Trạng thái đơn khác xem ở trang đơn hàng, không tạo thông báo.
- **Worker:** dùng khung service `worker` của Plan A phase 7 (phụ thuộc rõ ràng, cùng mốc M2); job heartbeat hiển thị ở `/ready` (tuổi đơn quá hạn lâu nhất); xác nhận thanh toán còn kiểm hạn kiểu "lười" nên không phụ thuộc hoàn toàn vào job.
- Agent (`lookup_order`) hiển thị đúng mốc thời gian, trạng thái thanh toán, và điều kiện hoàn tiền (Plan A phase 5).

## Related Code Files

- Create: `backend/app/orders/{state_machine,service}.py`, `backend/app/worker/jobs/expire_orders.py`, `backend/app/api/routes_order_actions.py`, `frontend/src/lib/notification-copy.ts`, tests
- Modify: `backend/app/worker/main.py` (đăng ký job; khung worker do Plan A phase 7 tạo), `backend/app/inventory/service.py` (thêm `release`), `frontend/src/pages/order-detail-page.tsx` (mốc thời gian, nút Huỷ, trạng thái yêu cầu hoàn)

## Implementation Steps

1. `state_machine.py` + test bảng chuyển (mọi cặp hợp lệ/không hợp lệ, bất biến với payment).
2. `orders/service.py`: chuyển trạng thái trong transaction, kiểm quyền, ghi event, tạo refund hệ thống khi huỷ đơn đã `paid`, release tồn.
3. Route khách huỷ đơn; route staff đổi trạng thái (đã khai ở phase 5).
4. Job hết hạn + heartbeat; test đồng hồ giả và race xác nhận-vs-hết hạn.
5. Nối `delivered_at` với điều kiện hoàn tiền của Plan A; cập nhật test của Plan A.
6. Frontend: mốc thời gian đơn, nút Huỷ (chỉ khi được phép), thông báo theo bảng ánh xạ.

## Todo List

- [ ] Bảng chuyển trạng thái + test
- [ ] Service huỷ/giao/release tồn + refund hệ thống
- [ ] Job hết hạn + heartbeat + test race
- [ ] Frontend mốc thời gian/Huỷ/thông báo

## Success Criteria

- [ ] Không có chuyển trạng thái lùi hoặc sai quyền; không giao chuyển khoản khi chưa `paid`
- [ ] Huỷ đơn luôn trả đúng tồn một lần (kể cả huỷ/hết hạn/tạo đồng thời); huỷ đơn đã `paid` luôn có refund
- [ ] Test race "xác nhận vs hết hạn" pass; job chạy 2 lần không gây tác dụng phụ

## Risk Assessment

Deadlock hoặc trả tồn hai lần → thứ tự khoá cố định, `stock_released_at`, retry. Worker chưa có/đang chết → kiểm hạn lười ở bước xác nhận + heartbeat trong `/ready`. COD giao thất bại cần chính sách hàng trả → v1 coi như hàng về kho ngay.

## Security Considerations

Chuyển trạng thái chỉ qua service có kiểm quyền và tách nhiệm vụ; `delivered_at` ghi một lần có audit (không thể kéo dài hạn hoàn tiền bằng cách sửa); refund hệ thống không cần khách thao tác.

## Next Steps

Phase 7 kiểm thử toàn bộ các bất biến này bằng e2e và test đua.
