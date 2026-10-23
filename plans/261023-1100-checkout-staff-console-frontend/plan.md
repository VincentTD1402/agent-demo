---
title: "Checkout, payments, staff console, frontend auth and SSE (Plan B)"
description: "Đăng nhập + chat SSE trên frontend, checkout tạo đơn thật, thanh toán COD/chuyển khoản thủ công, console nhân viên (hoàn tiền, phiếu, chuyển khoản, đơn hàng), vòng đời đơn. Đã qua red-team."
status: pending
priority: P1
branch: ""
tags: [frontend, checkout, payments, staff-console, sse]
blockedBy: [261023-1010-backend-alembic-and-langgraph-agent]
blocks: []
created: "2026-10-23T03:16:52.269Z"
createdBy: "ck:plan"
source: skill
---

# Plan B: Checkout, payments, staff console, frontend auth/SSE

## Overview

Làm sau/xen kẽ với Plan A (cần schema, auth/RBAC, API v2). Biến storefront thành cửa hàng chạy thật: khách đăng nhập, chat qua SSE, đặt hàng, thanh toán (COD hoặc chuyển khoản có nhân viên xác nhận), nhân viên xử lý đơn, duyệt hoàn tiền và xử lý phiếu hỗ trợ trên console riêng.

**Cổng phát hành khách-facing = Plan A phase 7 + Plan B phase 1 + Plan B phase 2** (API v2 bỏ `user_id`/`API_KEY` và đổi hợp đồng chat; giao diện cũ sẽ hỏng nếu phát hành riêng).

## Phases

| Phase | Name | Effort | Mốc | Phụ thuộc | Status |
|-------|------|--------|-----|-----------|--------|
| 1 | [Frontend auth](./phase-01-frontend-auth.md) | 2.5d | M1 | A#4 | Pending |
| 2 | [Frontend chat SSE and notifications](./phase-02-frontend-chat-sse-and-notifications.md) | 2d | M2 | A#7, B#1 | Pending |
| 3 | [Checkout and order creation](./phase-03-checkout-and-order-creation.md) | 4d | M2 | A#3, A#4, B#1 | Pending |
| 4 | [Payments COD and bank transfer](./phase-04-payments-cod-and-bank-transfer.md) | 3d | M2 | B#3 | Pending |
| 5 | [Staff console](./phase-05-staff-console.md) | 4.5d | M1 (hoàn tiền + phiếu), M2 | B#1, A#7 | Pending |
| 6 | [Order lifecycle](./phase-06-order-lifecycle.md) | 2.5d | M2 | B#3, B#4, A#7 (khung worker) | Pending |
| 7 | [E2E tests and hardening](./phase-07-e2e-tests-and-hardening.md) | 3.5d | M2 + M3 | tất cả | Pending |

Tổng ~22 ngày công (đã gồm hạ tầng test frontend và hàng đợi phiếu hỗ trợ). Cùng Plan A (~34,5 ngày) ≈ 56,5 ngày cho 1 developer (≈ 12-13 tuần, **người dùng chọn 1 developer làm tuần tự**); frontend dùng mock theo OpenAPI v0 khi backend chưa sẵn.

## Mốc giao hàng (dùng chung hai plan)

| Mốc | Nội dung | Cổng thoát |
|-----|----------|-----------|
| **M0 Cổng và nền** (~4d) | Plan A phase 1 (probe model, spike danh tính, LangGraph), script kiểm tra `scripts/check`, test infra, đóng băng OpenAPI v0, các quyết định chốt | tool calling ≥ 95% đạt, spike danh tính đạt, `scripts/check` xanh |
| **M1 Lát dọc hoàn tiền** | A#2, A#3 (tập con), A#4, A#5, A#6 (bản mỏng), A#7 (chat JSON, hoàn tiền staff, phiếu), B#1, B#5 (tab Hoàn tiền + Phiếu) | demo trên compose sạch với LLM thật: khách xin hoàn tiền → xác nhận → nhân viên duyệt → thông báo; phiếu handoff có người xử lý |
| **M2 Checkout thật và chat đủ** | A#3/#6/#7 phần còn lại, A#8, B#2, B#3, B#4, B#5, B#6, B#7 (e2e) | phát hành cổng A#7+B#1+B#2; test đua/idempotency/giá giả; SSE qua nginx thật; eval ca cứng đạt |
| **M3 Hardening** | A#9, B#7 rà soát, docs, backup/restore thử, buổi thử với nhân viên | không còn lỗ hổng Critical/High; runbook đã kiểm chứng |

## Quyết định đã chốt

- Thanh toán: **COD + chuyển khoản thủ công**; `PaymentProvider` nhỏ (2 class) cho tương lai; không có route webhook.
- Giá/phí ship/tồn kho do **server** quyết định; client gửi `expected_total_vnd`, server trả 409 nếu lệch.
- **Quy tắc hoàn tiền & đơn (D12):** hoàn trong 7 ngày từ `delivered_at`; trần = tiền hàng đã thực thu (không gồm ship trừ lỗi shop) trừ phần đã hoàn; 1 yêu cầu "sống" mỗi đơn và không tạo mới sau `paid_out`; chỉ hoàn khi payment `paid`; COD bắt đầu `processing`, payment `pending` đến khi nhân viên thu; đơn đã trả rồi huỷ tự tạo refund `pending_staff`; chuyển khoản hết hạn 24h chỉ với payment `pending`, "đã chuyển" không gia hạn; thông tin nhận tiền hoàn do khách điền ở trang đơn. Số liệu do chủ shop xác nhận.
- **Chatbot v1 (D13) và cắt phạm vi (D14)** như ghi ở Plan A.

## Red Team Review

### Session — 2026-10-23
**Findings:** 15 chính (15 accepted, 0 rejected); chi tiết ở `plans/reports/from-red-team-to-planner-plan-b-findings-summary-report.md`
**Severity breakdown:** 3 Critical, 10 High, 2 Medium
**Reviewers:** Security Adversary, Failure Mode Analyst, Assumption Destroyer, Scope & Complexity Critic

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | Idempotency-Key không có lưu trữ/phạm vi/hash | Critical | Accept | B#3 (cột ở Plan A#3) |
| 2 | Hết hạn đua với xác nhận chuyển khoản; thứ tự khoá | Critical | Accept | B#4, B#6 |
| 3 | Đơn đã trả rồi huỷ không có đường hoàn; eligibility bỏ qua payment | Critical | Accept | B#6, Plan A#5, A#7 |
| 4 | Vòng đời COD; bảng chuyển trạng thái; giao khi chưa paid | High | Accept | B#6 |
| 5 | Báo giá không gắn tạo đơn; `expected_total`; số tiền thực nhận | High | Accept | B#3, B#4 |
| 6 | Khoá/trả tồn kho không nhất quán | High | Accept | B#3, B#6 |
| 7 | Nhân viên tự thao tác đơn của mình; mã giao dịch không unique | High | Accept | B#4, B#5, B#6 |
| 8 | DoS giữ tồn kho (không rate limit/trần) | High | Accept | B#3 |
| 9 | Bảng mới thiếu GRANT/append-only; payment_status trùng; PII | High | Accept | B#4, Plan A#3 |
| 10 | Plan B sở hữu lại orders; hai nguồn địa chỉ; thiếu backfill | High | Accept | Plan A#3, B#3 |
| 11 | Cookie qua nginx, Secure trên HTTP, XFF, cổng 8000 | High | Accept | B#1 |
| 12 | Cổng phát hành phải gồm B#2 | High | Accept | plan.md |
| 13 | Không dọn state client khi đăng xuất | High | Accept | B#1 |
| 14 | CSP/nginx chưa đặc tả; XSS console | Medium | Accept | B#2, B#5 |
| 15 | Thừa (webhook, 3 bảng event, địa chỉ lưu, chuông...), thiếu test infra, worker/lát dọc | Medium | Accept (D14) | B#1, B#2, B#4, B#5, B#6 |

Cũng áp dụng từ PM/BA: hàng đợi phiếu hỗ trợ (B#5), thông tin nhận tiền hoàn (Plan A#7 + trang đơn B#3/B#6), đồng ý bộ nhớ (B#2), bảng ánh xạ thông báo (B#6), mốc M0-M3.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01 → phase-07 (Plan B); plan.md và phase-03/05/06/07 (Plan A)
- Decision deltas checked: 7 (D12-D15 + 3 quyết định red-team B)
- Reconciled stale references: 3 (phụ thuộc worker phase 9 → phase 7; dòng bảng phase 6; ghi chú "chuông" thành huy hiệu). Đã quét cùng bộ thuật ngữ như Plan A
- Unresolved contradictions: 0 (các câu hỏi mở nằm ở mục dưới)

## Câu hỏi mở (cần chủ shop/người dùng)

1. Số ngày hoàn tiền (7), trần theo dòng, ship trong hoàn tiền: chờ chủ shop xác nhận và rà quy định bảo vệ người tiêu dùng VN.
2. Nghĩa vụ pháp lý với bộ nhớ dài hạn (đồng ý, thời hạn lưu) cần người có chuyên môn xác nhận.
3. Hoá đơn/VAT và hạn mức COD. (Đã chốt ở validation: đối soát thủ công, 1 developer, chưa dùng CI.)
4. Nội dung KB bảo hành/đổi trả/vận chuyển đã có văn bản chưa.

## Dependencies

Bị chặn bởi [Plan A](../261023-1010-backend-alembic-and-langgraph-agent/plan.md) theo từng phase (xem cột "Phụ thuộc"; `A#n` = phase n của Plan A).

## Validation Log

Phiên validate chung hai plan: xem `Validation Log` Session 1 trong [Plan A](../261023-1010-backend-alembic-and-langgraph-agent/plan.md). Ảnh hưởng tới Plan B: chưa dùng CI (phase 1, 7 dùng `scripts/check`), `payout_info_enc` (phase 5), cấu hình ship (phase 3), đối soát chuyển khoản thủ công (phase 4/5), 1 developer tuần tự (≈ 12-13 tuần cho cả hai plan).
