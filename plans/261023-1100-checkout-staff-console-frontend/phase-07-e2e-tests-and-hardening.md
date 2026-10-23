---
phase: 7
title: "E2E tests and hardening"
status: pending
priority: P1
effort: "3.5d"
milestone: "M2 (luồng chính) + M3 (rà soát)"
dependencies: ["261023-1100-checkout-staff-console-frontend#1", "261023-1100-checkout-staff-console-frontend#2", "261023-1100-checkout-staff-console-frontend#3", "261023-1100-checkout-staff-console-frontend#4", "261023-1100-checkout-staff-console-frontend#5", "261023-1100-checkout-staff-console-frontend#6", "261023-1010-backend-alembic-and-langgraph-agent#8", "261023-1010-backend-alembic-and-langgraph-agent#9"]
---

# Phase 7: E2E tests and hardening

## Overview

Kiểm thử xuyên suốt luồng tiền, quyền và tồn kho; rà soát bảo mật; vận hành thử với nhân viên thật. Playwright được dựng từ đầu (chưa có trong repo).

## Requirements

- Functional: các luồng chính chạy end-to-end trên stack compose thật.
- Non-functional: test ổn định (LLM giả cho test xác định; model thật chỉ ở nhóm đánh dấu riêng); không rò dữ liệu chéo người dùng.

## Implementation Steps

1. Hạ tầng e2e: Playwright + compose profile `e2e` với **model giả** (Plan A cung cấp cờ model giả) và dữ liệu fixture cố định từ seed (đơn đã giao đủ điều kiện hoàn, đơn đang giao, đơn COD, user demo/staff demo).
2. Ba luồng chính (Playwright):
   - đăng ký → đăng nhập → thêm giỏ → checkout COD → thấy đơn → nhân viên giao/đã giao/đã thu;
   - checkout chuyển khoản → "Tôi đã chuyển khoản" → nhân viên xác nhận (nhập số tiền thực nhận) → đơn `processing`;
   - **hoàn tiền đầy đủ**: đơn đã giao → khách chat xin hoàn tiền → xác nhận → nhân viên duyệt → khách điền thông tin nhận tiền → chi trả → khách thấy thông báo; kèm biến thể bị từ chối rồi gửi lại.
3. Test an toàn dữ liệu và quyền: tải lại trang giữ phiên qua nginx; hai tab không bị đăng xuất; khách gọi route staff = 403; truy cập chéo đơn/thanh toán/hội thoại bị chặn; nhân viên không tự thao tác đơn của mình; chuỗi `<script>` và URL `javascript:` hiển thị an toàn ở console; header CSP có mặt; cổng API không truy cập trực tiếp được trong profile chạy cùng frontend.
4. Test tiền/tồn: giá giả/`expected_total` sai bị 409; double-click và gửi lại cùng key không tạo đơn thứ hai; hai người mua sản phẩm cuối cùng; qty/slug trùng; vượt 3 đơn chưa trả; xác nhận thanh toán hai lần; **xác nhận đua với hết hạn**; đơn đã `paid` bị huỷ tạo refund hệ thống; COD không `paid` trước `delivered`; chuyển khoản không giao khi chưa `paid`.
5. Luồng phiếu: khách yêu cầu gặp người → phiếu xuất hiện ở hàng đợi → nhân viên xử lý → khách thấy cập nhật.
6. Nhóm `live-llm` (chạy tay): hội thoại thật qua model tự host cho luồng hoàn tiền và handoff.
7. Rà soát bảo mật: `ck:security-scan`, `code-reviewer` (IDOR, giá, máy trạng thái tiền, cookie/CSRF, XSS console), kiểm tra trợ năng form checkout, `npm audit`/`pip-audit`.
8. Tài liệu vận hành cho nhân viên (hoàn tiền, xác nhận chuyển khoản, xử lý phiếu, COD, đối soát) bổ sung vào `docs/` do Plan A phase 9 tạo; sơ đồ máy trạng thái hợp nhất; checklist phát hành và rollback. Buổi hướng dẫn thử với nhân viên thật.

## Todo List

- [ ] Playwright + profile `e2e` + fixture + model giả
- [ ] 3 luồng chính + luồng phiếu
- [ ] Test quyền/an toàn hiển thị/header
- [ ] Test tiền/tồn/đua
- [ ] Rà soát bảo mật + tài liệu vận hành + buổi thử nhân viên

## Success Criteria

- [ ] 3 luồng e2e + luồng phiếu pass trên stack sạch
- [ ] Không còn lỗ hổng mức cao/trung trong báo cáo rà soát
- [ ] Tài liệu vận hành đủ để nhân viên làm theo từng bước; một buổi thử thật đã chạy

## Risk Assessment

E2E chậm/flaky → dữ liệu seed cố định, model giả, chờ theo điều kiện thay vì `sleep`, chạy tay bằng script trước mỗi mốc (chưa dùng CI). Tài liệu trùng với Plan A phase 9 → chỉ bổ sung phần vận hành nhân viên, không viết lại kiến trúc.

## Security Considerations

Đây là phase kiểm chứng: mọi bất biến về quyền, tiền, tồn kho, hiển thị an toàn phải có test tự động; báo cáo rà soát phải không còn mục Critical/High.

## Next Steps

Sau khi pass: M3 (hardening) của hai plan, phát hành theo cổng ghi trong `plan.md`.
