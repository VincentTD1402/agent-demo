---
phase: 4
title: "Payments COD and bank transfer"
status: pending
priority: P1
effort: "3d"
milestone: "M2"
dependencies: ["261023-1100-checkout-staff-console-frontend#3"]
---

# Phase 4: Payments COD and bank transfer

## Overview

Thanh toán có máy trạng thái và audit; hai phương thức: COD và chuyển khoản thủ công (nhân viên đối chiếu). Interface cổng thanh toán giữ nhỏ (2 class) để gắn VNPay/PayOS sau, **không** dựng route webhook khi chưa có cổng.

## Requirements

- Functional: tạo payment cùng đơn, hướng dẫn chuyển khoản, khách báo "đã chuyển", nhân viên xác nhận/từ chối kèm số tiền thực nhận, COD thu khi giao.
- Non-functional: chuyển trạng thái chỉ qua service, idempotent, mọi thay đổi ghi `status_events`.

## Architecture

- Bảng `payments(order_id, method CHECK(cod, bank_transfer), amount_vnd, status CHECK(pending, awaiting_confirmation, paid, failed, cancelled), reference_code unique, provider_txn_id null, received_amount_vnd null, confirmed_by fk null, paid_at, timestamps)`; `provider_txn_id` **unique khi khác NULL**, chỉ `[A-Za-z0-9-]` tối đa 64 ký tự. Không có trạng thái `refunded` (trạng thái hoàn tiền suy ra từ `refunds` của Plan A). Sự kiện ghi vào bảng chung `status_events` (`entity_type='payment'`) của Plan A; **không** tạo `payment_events`/`order_events`.
- `PaymentProvider` tối giản: `create(order) -> PaymentInstructions`; hai lớp `CodProvider`, `ManualBankTransferProvider`, đăng ký theo `method`. Không có `verify_webhook`/`refund`/route webhook (YAGNI; thêm khi có cổng thật, cùng chữ ký bí mật + cờ bật).
- **Chuyển khoản:** hiển thị tài khoản từ env (`BANK_NAME`, `BANK_ACCOUNT_NO`, `BANK_ACCOUNT_NAME`) + nội dung = `reference_code`. Khách bấm "Tôi đã chuyển khoản" (mã giao dịch tuỳ chọn) → `awaiting_confirmation`; **không gia hạn `expires_at`**; hết hạn chỉ tác động đơn có payment `pending` (phase 6). Nhân viên đối chiếu sao kê: **bắt buộc nhập `received_amount_vnd`**, phải bằng `amount_vnd` (lệch → không xác nhận, tạo ghi chú/từ chối); mã giao dịch đã gắn với payment `paid` khác thì bị từ chối → `paid` → đơn `processing`. Từ chối → `failed` (khách thấy lý do; đơn còn `pending_payment` nên khách đặt lại phương thức trong hạn).
- **COD:** payment `pending` đến khi đơn `delivered`; chỉ khi đó nhân viên được đánh dấu `paid` (đã thu), **không** cho đánh dấu trước khi giao.
- **Phân tách nhiệm vụ:** nhân viên không xác nhận/từ chối/đánh dấu thu COD cho **đơn của chính mình** (`actor_id != orders.user_id`).
- Hoàn tiền (Plan A): `paid_out` không đổi trạng thái payment; điều kiện hoàn tiền yêu cầu payment `paid`; tổng `refunds.approved_amount_vnd ≤ amount_vnd` (ràng buộc kiểm trong `refunds/service.py` + CHECK/trigger).
- **GRANT:** `app` chỉ INSERT trên `status_events` (đã có); view `order_payment_summary` (method, status, amount) cấp SELECT cho `mcp`, không có `provider_txn_id`; `payments` không cấp cho `mcp`.

## Related Code Files

- Create: `backend/app/payments/{service,providers/{base,cod,manual_bank}}.py`, `backend/app/api/routes_payments.py`, migration `payments` (+ view + GRANT), `frontend/src/checkout/payment-instructions.tsx`, tests
- Modify: `backend/app/checkout/service.py` (tạo payment), `backend/app/settings/api.py` + `.env.example` (thông tin ngân hàng), `backend/app/refunds/service.py` (kiểm payment `paid` + tổng hoàn)

## Implementation Steps

1. Model + migration + view/GRANT + test quyền (copy mẫu của Plan A).
2. `payments/service.py`: chuyển trạng thái hợp lệ (`FOR UPDATE`, ghi `status_events`), kiểm tách nhiệm vụ, số tiền thực nhận, mã giao dịch unique.
3. Hai provider + registry; route khách `POST /v1/payments/{id}/mark-transferred` (rate limit).
4. Frontend: trang hướng dẫn chuyển khoản (sao chép nội dung/số tiền), trạng thái thanh toán ở chi tiết đơn.
5. Test: chuyển sai bị từ chối, xác nhận hai lần chỉ hiệu lực một lần, khách không xác nhận được, nhân viên không xác nhận đơn của mình, số tiền lệch bị từ chối, mã giao dịch trùng bị từ chối, COD không `paid` trước `delivered`, `mark-transferred` không gia hạn hạn.

## Todo List

- [ ] Migration payments + view/GRANT + test quyền
- [ ] Payment service + provider COD/chuyển khoản
- [ ] Frontend hướng dẫn chuyển khoản
- [ ] Test tách nhiệm vụ, số tiền, mã giao dịch

## Success Criteria

- [ ] Không có đường nào đặt `paid` mà không do nhân viên (đúng quy tắc) — không có webhook
- [ ] Mọi thay đổi trạng thái có `status_events` (ai, khi nào, ghi chú)
- [ ] `mcp` không đọc được `provider_txn_id`; thêm provider mới = thêm một lớp + đăng ký

## Risk Assessment

Khách khai man "đã chuyển" → chỉ nhân viên xác nhận sang `paid`, bắt buộc khớp số tiền, chặn mã giao dịch trùng. Mã giao dịch của người khác bị dùng lại → unique + đối chiếu số tiền và `reference_code`.

## Security Considerations

Số tiền luôn server-tính; `provider_txn_id` nhập tự do bị giới hạn ký tự/độ dài và hiển thị dạng text; mọi thao tác tiền có actor và audit chỉ-thêm; không có endpoint công khai không xác thực.

## Next Steps

Phase 5 dựng hàng đợi xác nhận chuyển khoản; phase 6 gắn payment vào máy trạng thái đơn.
