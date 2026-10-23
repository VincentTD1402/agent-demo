---
phase: 5
title: "Staff console"
status: pending
priority: P1
effort: "4.5d"
milestone: "M1 (hàng đợi hoàn tiền + phiếu) + M2 (chuyển khoản, đơn hàng)"
dependencies: ["261023-1100-checkout-staff-console-frontend#1", "261023-1010-backend-alembic-and-langgraph-agent#7"]
---

# Phase 5: Staff console

## Overview

Giao diện riêng cho nhân viên (`/staff`): một trang với các tab **Hoàn tiền, Phiếu hỗ trợ, Chuyển khoản, Đơn hàng**. Ưu tiên rõ ràng và an toàn khi thao tác tiền. **Hàng đợi hoàn tiền và phiếu làm trước ở M1** để có bản demo đầu-cuối; chuyển khoản và đơn hàng ở M2. Không có dashboard thống kê.

## Requirements

- Functional: duyệt/từ chối/chi trả hoàn tiền; xử lý phiếu; xác nhận chuyển khoản; cập nhật trạng thái đơn; xem lịch sử sự kiện.
- Non-functional: chỉ `staff|admin` (API kiểm lại, không chỉ ẩn nút); danh sách phân trang (limit + con trỏ); dùng được bằng bàn phím.

## Architecture

- Layout riêng, lazy-load để không làm nặng bundle khách. Mỗi tab có lọc trạng thái và tìm theo mã đơn.
- **Hoàn tiền** (API Plan A phase 7): danh sách theo trạng thái; chi tiết có đơn, lý do, điều kiện + trần, trích đoạn hội thoại gắn với yêu cầu (log truy cập), thông tin nhận tiền khách đã điền (che bớt); nút Duyệt/Từ chối **bắt buộc ghi chú**; sau duyệt có form `payout_reference` (**chặn khi khách chưa điền thông tin nhận tiền**); số tiền chi = số được duyệt. Không tự duyệt/chi yêu cầu của chính mình.
- **Phiếu hỗ trợ** (mới): hàng đợi theo `priority` và `due_at`; nhận phiếu (assign), ghi phản hồi, đóng; mỗi thay đổi thông báo khách (`ticket_updated`). Chi tiết có category, tóm tắt, đơn liên quan, trích đoạn hội thoại.
- **Chuyển khoản:** danh sách `awaiting_confirmation`: số tiền, `reference_code`, mã giao dịch khách nhập; **bắt buộc nhập số tiền thực nhận**; Xác nhận/Từ chối có ghi chú. Không thao tác trên đơn của chính mình (API chặn, UI báo lý do).
- **Đơn hàng:** tìm theo mã; đổi trạng thái theo bảng chuyển hợp lệ (phase 6): giao (hãng + mã vận đơn), đã giao, đánh dấu COD đã thu, giao thất bại, huỷ; "ghi nhận tiền đã nhận cho đơn đã huỷ" tạo refund hệ thống.
- **Hiển thị an toàn:** mọi văn bản do khách nhập (lý do, ghi chú, địa chỉ, tóm tắt phiếu, mã giao dịch) render dạng text, không `dangerouslySetInnerHTML`; trường URL (mã vận đơn, ảnh) chỉ cho `https?://`; CSP và các header an toàn ở nginx dùng chung một snippet `include` cho mọi `location` (`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; frame-ancestors 'none'; object-src 'none'; base-uri 'none'`, kèm `X-Content-Type-Options`, `Referrer-Policy`). Có test header.
- Mọi thao tác tiền: hộp xác nhận, vô hiệu nút khi đang gửi, xử lý 409 bằng tải lại, không cập nhật lạc quan.
- API mới (Plan B backend): `GET /v1/staff/payments`, `POST /v1/staff/payments/{id}/confirm|reject`, `GET /v1/staff/orders`, `POST /v1/staff/orders/{id}/status` (đều phân trang). Hoàn tiền/phiếu dùng API Plan A.

## Related Code Files

- Create: `frontend/src/staff/{staff-layout,refund-tab,refund-detail,ticket-tab,ticket-detail,payment-tab,order-tab,event-timeline}.tsx`, `backend/app/api/routes_staff_{payments,orders}.py`, tests
- Modify: `frontend/src/App.tsx` (route `/staff/*` lazy + `RequireRole`), `frontend/src/components/site-layout.tsx` (liên kết Console), `frontend/nginx.conf.template` (CSP + snippet header dùng chung)

## Implementation Steps

1. Layout + guard + tab Hoàn tiền (M1) + tab Phiếu hỗ trợ (M1).
2. API staff payments/orders (phân trang) + test phân quyền + tách nhiệm vụ.
3. Tab Chuyển khoản; tab Đơn hàng; timeline sự kiện (M2).
4. nginx: snippet header an toàn + CSP; test header.
5. Test component (hộp xác nhận, 409, chuỗi `<script>`/URL `javascript:` hiển thị an toàn, chi trả bị chặn khi thiếu thông tin nhận tiền) + test API (khách 403, chuyển trạng thái sai 409, tự thao tác đơn của mình bị chặn).

## Todo List

- [ ] Layout + tab Hoàn tiền + tab Phiếu (M1)
- [ ] API staff payments/orders phân trang
- [ ] Tab Chuyển khoản + Đơn hàng + timeline (M2)
- [ ] CSP/header nginx + test
- [ ] Test an toàn hiển thị và phân quyền

## Success Criteria

- [ ] Quy trình hoàn tiền (khách yêu cầu → nhân viên duyệt → khách điền thông tin nhận tiền → chi trả → thông báo) chạy hoàn toàn bằng giao diện
- [ ] Phiếu handoff có người xử lý, khách xem được trạng thái
- [ ] Khách gọi API staff trực tiếp vẫn 403; mỗi thao tác tiền để lại event có người thực hiện

## Risk Assessment

Hai nhân viên mở trùng một mục → `FOR UPDATE` + kiểm trạng thái, người sau 409 và UI tải lại. Lộ hội thoại → chỉ trả trích đoạn gắn yêu cầu/phiếu và ghi log truy cập. CSP chặt làm hỏng font/inline style → cho phép đúng nguồn font + `'unsafe-inline'` cho style, không cho script inline.

## Security Considerations

Console cùng origin với storefront nên XSS lưu trữ là rủi ro chính: render text, validate URL, CSP, `frame-ancestors 'none'` chống clickjacking; RBAC đọc từ DB; `payout_info_enc` và mã giao dịch là PII/nhạy cảm nên che khi hiển thị.

## Next Steps

Phase 6 định nghĩa bảng chuyển trạng thái mà tab Đơn hàng dùng; phase 7 e2e kiểm tra toàn bộ.
