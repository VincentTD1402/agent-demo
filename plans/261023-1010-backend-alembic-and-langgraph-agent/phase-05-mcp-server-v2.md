---
phase: 5
title: "MCP server v2"
status: pending
priority: P1
effort: "3d"
milestone: "M1"
dependencies: ["261023-1010-backend-alembic-and-langgraph-agent#3"]
---

# Phase 5: MCP server v2

## Overview

Tách công cụ theo miền (7 tool), MCP tự xác thực danh tính bằng token ký ngắn hạn cho từng lời gọi, chạy bằng role DB `mcp` tối thiểu, và tạo yêu cầu hoàn tiền **chờ nhân viên duyệt** theo quy tắc hoàn tiền đã chốt.

## Requirements

- Functional: công cụ cho tư vấn, tra đơn, hoàn tiền, handoff, tra chính sách (có trích dẫn).
- Non-functional: mọi tool ghi audit; timeout; lỗi trả cấu trúc `{ok, code, message}`; không rò stack trace; fail-closed khi thiếu danh tính.

## Architecture

**Ranh giới tin cậy:** API → MCP qua mạng nội bộ. Mỗi lời gọi tool mang token JWT riêng `aud=mcp`, ký bằng `MCP_CONTEXT_KEY` (khác secret JWT người dùng), hạn ≤ 60 giây, claim `{user_id, thread_id, request_id, tool, args_hash, jti}`. Token ký **tại lúc thực thi tool** (sau resume), không nằm trong schema LLM thấy. Middleware MCP verify chữ ký, `aud`, hạn, khớp `tool` + `args_hash`, chống phát lại bằng `jti`; thiếu/sai → từ chối. Không publish cổng MCP ra host. Tool **không có tham số `user_id`**.

| Miền | Tool (7) | Loại |
|------|----------|------|
| catalog | `search_products(query?, category?, brand?, min/max_price?, in_stock_only?, slugs?, limit<=8)` lai trigram + embedding; trả cả thông số (so sánh bằng `slugs`) | đọc |
| orders | `list_my_orders(limit)`; `lookup_order(order_id)` — item, vận chuyển, trạng thái thanh toán (view tóm tắt của Plan B), **điều kiện hoàn tiền + `max_refundable` do server tính** | đọc |
| refunds | `request_refund(order_id, amount_vnd, reason)` → server kiểm lại, tạo refund `pending_staff`, không bao giờ tự chi tiền; `get_refund_status(order_id)` | **ghi nhạy cảm** / đọc |
| support | `create_support_ticket(category, summary, priority)` — chỉ nhận category enum; `due_at` do server đặt theo SLA | ghi, rủi ro thấp |
| knowledge | `search_knowledge_base(query, category?)` top-k chunk + `doc_slug` (trích dẫn), lọc theo ngôn ngữ | đọc |

**Quy tắc hoàn tiền (một nguồn, dùng chung cho `lookup_order` và `request_refund`, đọc từ cấu hình):**
- đủ điều kiện ⇔ đơn `delivered`, trong `REFUND_WINDOW_DAYS` (mặc định 7) kể từ `delivered_at`, **thanh toán đã `paid`** (COD: nhân viên đã đánh dấu thu tiền), chưa có refund ở trạng thái `pending_staff/approved/paid_out`;
- `max_refundable` = tổng tiền hàng đã thực thu (không gồm phí ship, trừ lỗi từ shop) − tổng đã hoàn; `amount_vnd` do LLM đưa vào chỉ hợp lệ nếu ≤ trần;
- `idempotency_key = thread_id:tool_call_id`; trùng khoá trả bản ghi đang sống; bản cũ `rejected/cancelled` thì cho tạo mới; ghi `status_events` + thông báo cho nhân viên.
- Thông tin nhận tiền hoàn **không** thu trong chat: khách điền ở trang đơn hàng sau khi yêu cầu được tạo (phase 7: `PATCH .../payout-info`); staff không chi trả khi chưa có.

**SQL an toàn:** bind parameter, cột sắp xếp/lọc từ allowlist; test SQL injection. Mô tả tool theo mẫu slide; annotation `readOnlyHint`/`destructiveHint`/`idempotentHint`.

## Related Code Files

- Create: `backend/app/mcp_server/{auth,audit,errors}.py`, `backend/app/mcp_server/tools/{catalog,orders,refunds,support,knowledge}.py`, `backend/app/refunds/policy.py` (quy tắc trên), `backend/tests/mcp/*`
- Modify: `backend/app/mcp_server/server.py` (chỉ ráp + middleware), `backend/app/settings/mcp.py`, `docker-compose.yml` (`MCP_CONTEXT_KEY`, DSN role `mcp`), `.env.example`
- Delete: `backend/app/mcp_server/db.py` (nếu còn)

## Implementation Steps

1. `auth.py`: verify token theo lời gọi, dựng `TrustedContext`; fail-closed.
2. `refunds/policy.py` + test bảng (đủ/không đủ điều kiện, đúng/sai trần, COD chưa thu, ngoài hạn, đã có refund).
3. Module tool; decorator `@audited` ghi `tool_audit_log` (cắt/ẩn nội dung dài).
4. `request_refund`: kiểm sở hữu + điều kiện + trần phía server, `SELECT ... FOR UPDATE` đơn, tạo refund theo idempotency ở trên, ghi event + notification.
5. Timeout 5s/tool, pool riêng, `LIMIT` cứng; tìm kiếm tụt về trigram khi embedding lỗi và **ghi log cảnh báo**.
6. Test (client MCP in-memory + Postgres thật bằng role `mcp`): truy cập đơn người khác bị từ chối; thiếu/sai/hết hạn/phát lại token bị chặn; yêu cầu song song chỉ 1 bản ghi; gửi lại sau từ chối được; số tiền vượt trần bị từ chối; COD chưa thu không hoàn được; SQL injection; role `mcp` không đọc `users`/`payout_info_enc`/`shipping_address`.

## Todo List

- [ ] Verify token theo lời gọi + middleware + test tấn công
- [ ] Chính sách hoàn tiền + test bảng
- [ ] 7 tool + audit + timeout
- [ ] Test quyền role `mcp` và đua yêu cầu hoàn tiền

## Success Criteria

- [ ] Không tool nào nhận danh tính từ tham số LLM; token không xuất hiện trong schema tool
- [ ] Phát lại token hoặc đổi tham số sau khi ký → bị từ chối
- [ ] Không tool nào chuyển refund sang `approved`/`paid_out`; COD chưa thu không đủ điều kiện hoàn

## Risk Assessment

Ký token lúc LLM phát tool_call sẽ hết hạn trước khi resume → ký tại node `tools`, có test resume trễ quá TTL. Hybrid search phụ thuộc embedding; lỗi thì tụt về trigram nhưng phải thấy trong log.

## Security Considerations

Khoá `MCP_CONTEXT_KEY` tách biệt, xoay vòng được; `mcp` không đọc PII; SQL tham số hoá; không có tool nào đổi trạng thái tiền.

## Next Steps

Phase 6 dùng 7 tool này; phase 7 dùng `refunds/policy.py` cho API nhân viên (chi trả đúng số được duyệt).
