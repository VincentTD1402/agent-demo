---
phase: 7
title: "API v2"
status: pending
priority: P1
effort: "5.5d"
milestone: "M1 (chat JSON, hoàn tiền staff, phiếu) + M2 (SSE, hội thoại, bộ nhớ)"
dependencies: ["261023-1010-backend-alembic-and-langgraph-agent#4", "261023-1010-backend-alembic-and-langgraph-agent#6"]
---

# Phase 7: API v2

## Overview

Chat có SSE (kiểm tra rồi mới hiện), quản lý hội thoại/bộ nhớ/thông báo, **API nhân viên duyệt hoàn tiền và xử lý phiếu hỗ trợ**, chống chạy trùng lượt. **Cổng phát hành = phase này + Plan B phase 1 + phase 2** (API bỏ `user_id`/`API_KEY` và đổi hợp đồng chat nên giao diện cũ sẽ hỏng nếu phát hành riêng).

## Requirements

- Functional: chat JSON + SSE; resume; hội thoại/bộ nhớ/thông báo; luồng duyệt và chi trả hoàn tiền; phiếu hỗ trợ cho khách và nhân viên; thông tin nhận tiền hoàn.
- Non-functional: mọi endpoint cần JWT trừ catalog + `/health`; lỗi một định dạng `{code, message, request_id}`; huỷ lượt khi client ngắt mà không rò lease.

## Architecture

- Danh tính từ `current_user` (phase 4); không còn `user_id` trong body. Ownership kiểm **trước** khi chiếm lease. `thread_id` do server sinh.
- **Lượt chạy tuần tự bằng lease** `conversations.running_since` (UPDATE có điều kiện, hết hạn theo `LLM_TIMEOUT × số bước`); lượt thứ hai trên cùng thread nhận **409**; nhả lease trong `finally` bọc `asyncio.shield`; không giữ kết nối pool suốt lượt chạy.
- Thread đang chờ xác nhận: chat → **409** kèm hành động đang chờ; `POST /v1/chat/{id}/cancel-pending` huỷ rồi chat tiếp.
- **SSE kiểm tra rồi mới hiện:** `status` (node/tool_start/tool_end), `message` (câu trả lời cuối đã qua `guard_output`, gửi trọn một lần), `confirm_required`, `done`, `error`. Không có sự kiện `token`.
- Một helper `build_context()` cho chat, stream, resume.

| Endpoint | Ghi chú |
|----------|---------|
| `POST /v1/chat`, `POST /v1/chat/stream`, `POST /v1/chat/{id}/resume`, `.../cancel-pending` | như trên; khách chưa đăng nhập 401 |
| `GET/DELETE /v1/conversations[/{id}]` | tin nhắn đã lọc; xoá = soft delete + xoá checkpoint + bộ nhớ liên quan |
| `GET/DELETE /v1/me/memory[/{key}]`, `POST /v1/me/memory/consent` (đồng ý/thu hồi) | quyền riêng tư theo slide |
| `GET /v1/me/notifications`, `POST .../{id}/read` | loại: `refund_decided`, `refund_paid_out`, `payment_confirmed`, `payment_rejected`, `ticket_updated` |
| `GET /v1/me/refunds[/{id}]`, `POST /v1/refunds/{id}/cancel`, `PATCH /v1/refunds/{id}/payout-info` | khách xem trạng thái, huỷ khi `pending_staff`, điền tài khoản nhận tiền (chỉ chủ yêu cầu; **mã hoá cấp ứng dụng** vào `payout_info_enc`, che khi hiển thị; staff giải mã chỉ ở bước chi trả, ghi log truy cập) |
| `GET /v1/me/tickets[/{id}]` | khách xem trạng thái phiếu (mã, trạng thái, hạn dự kiến) |
| `GET /v1/staff/refunds?status=` `/{id}`, `POST .../{id}/decision`, `POST .../{id}/payout` | `staff|admin` (quyền đọc từ DB); payout **bị chặn khi chưa có `payout_info_enc`**, số tiền = `approved_amount_vnd`, chỉ sau `approved`; chuyển hợp lệ do `refunds/service.py` kiểm; không duyệt/chi yêu cầu của chính mình |
| `GET /v1/staff/tickets?status=` `/{id}`, `POST .../{id}/assign`, `.../respond`, `.../resolve` | hàng đợi phiếu; mỗi thay đổi ghi `status_events` + thông báo `ticket_updated` cho khách |
| `GET /v1/staff/conversations/{thread_id}/excerpt` | trích đoạn hội thoại **gắn với yêu cầu hoàn tiền hoặc phiếu** (không mở toàn bộ lịch sử); ghi log truy cập (ai, khi nào, vì sao) |

Máy trạng thái hoàn tiền: `pending_staff → approved | rejected | cancelled`, `approved → paid_out`; mọi chuyển ghi `status_events` (actor, thời gian). Khi đơn đã `paid` bị huỷ (Plan B) hệ thống tạo refund `source=system_cancel_paid` ở `pending_staff`.

## Related Code Files

- Create: `backend/app/api/{errors,sse,context}.py`, `backend/app/api/routes_{conversations,memory,notifications,refunds,tickets,staff_refunds,staff_tickets}.py`, `backend/app/refunds/service.py`, `backend/app/support/service.py`, `backend/tests/api/*`
- Modify: `backend/app/api/{routes_chat,deps,schemas}.py` (bỏ `user_id`, dùng `current_user`), `backend/app/main.py`, `.env.example`
- Delete: mọi tham chiếu `user_id` trong request model

## Implementation Steps

1. **Kiểm kê và thay `user_id`:** `backend/app/api/schemas.py:10,16`, `routes_chat.py` (~10 chỗ), `frontend/src/api.ts:25,28`, `frontend/src/components/chat-widget.tsx`; grep gate: không còn `user_id` trong request model/tool schema.
2. Route chat sang `current_user`, `thread_id` server sinh, lease, 409; sửa test cũ kiểm ownership qua `snap.metadata["user_id"]`.
3. SSE theo luồng "kiểm tra rồi mới hiện"; interrupt → `confirm_required`.
4. `refunds/service.py` (máy trạng thái, FOR UPDATE, kiểm vai trò + tự duyệt + khớp số tiền + có `payout_info_enc`, ghi event + notification) và `support/service.py` (vòng đời phiếu, `due_at` theo SLA).
5. Rate limit chat dùng module chung (20 req/phút/người); endpoint đồng ý bộ nhớ; helper mã hoá/giải mã `payout_info_enc` (Fernet, `PAYOUT_ENCRYPTION_KEY`, có quy trình xoay khoá) <!-- Updated: Validation Session 1 - mã hoá payout_info_enc +0,5d -->
   **Khung `worker`** (service riêng, cùng image, role `app`): vòng lặp job có khoá advisory (namespace riêng), registry để Plan B thêm job (hết hạn đơn), heartbeat ghi vào bảng/khoá để `/ready` đọc. Job dọn dữ liệu thêm ở phase 9.
6. Export OpenAPI + mô tả SSE vào `docs/` làm contract cho frontend (**đóng băng bản v0 ở M0**, frontend dùng mock).
7. Test httpx ASGI với graph giả: sở hữu thread, lượt thứ hai 409, chat khi chờ xác nhận 409 rồi `cancel-pending`, client ngắt giữa lượt xong lượt mới (lease nhả), khách gọi route staff 403, chuyển trạng thái sai/tự duyệt/chi sai số tiền/chưa có `payout_info_enc` bị từ chối, hai nhân viên cùng quyết định → người sau 409, vòng đời phiếu, trích đoạn hội thoại ghi log truy cập, bộ nhớ/hội thoại xoá thật.

## Todo List

- [ ] Thay `user_id` + grep gate + sửa test cũ (M1)
- [ ] Refund service + API staff + `payout-info` (M1)
- [ ] Support service + API phiếu khách/nhân viên + trích đoạn (M1)
- [ ] Chat JSON, resume, cancel-pending, lease (M1)
- [ ] Khung `worker` + registry job + heartbeat (M2)
- [ ] SSE, hội thoại, bộ nhớ + consent, thông báo (M2)
- [ ] OpenAPI v0 đóng băng, v1 export

## Success Criteria

- [ ] Không còn endpoint nào nhận danh tính từ client
- [ ] Khách A không đọc/resume/xoá được thread của B; thread không kẹt sau khi client ngắt
- [ ] Hoàn tiền chỉ đi qua đúng máy trạng thái; số chi khớp số được duyệt; có `payout_info_enc` mới chi được
- [ ] Phiếu hỗ trợ có người xử lý và khách xem được trạng thái (handoff không còn là ngõ cụt)

## Risk Assessment

SSE qua nginx cần `proxy_buffering off` (Plan B phase 2). Lease quá ngắn cho lượt dài → cấu hình theo timeout. Hai nhân viên quyết định cùng lúc → `FOR UPDATE` + kiểm trạng thái, người sau 409. Contract churn → đóng băng OpenAPI v0 trước khi frontend bắt đầu.

## Security Considerations

RBAC đọc từ DB mỗi route; mọi truy vấn lọc theo `user_id` từ JWT (IDOR); `payout_info_enc` chỉ staff/admin đọc và che khi hiển thị; trích đoạn hội thoại giới hạn theo phiếu/yêu cầu và có log truy cập; trạng thái tiền chỉ đổi qua service.

## Next Steps

Phát hành cùng Plan B phase 1 và 2. Plan B phase 5 dựng màn hình nhân viên cho các endpoint staff ở đây.
