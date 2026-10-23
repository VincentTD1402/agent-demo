---
phase: 2
title: "Frontend chat SSE and notifications"
status: pending
priority: P1
effort: "2d"
milestone: "M2"
dependencies: ["261023-1010-backend-alembic-and-langgraph-agent#7", "261023-1100-checkout-staff-console-frontend#1"]
---

# Phase 2: Frontend chat SSE and notifications

## Overview

Chat hiện trạng thái công cụ ngay, câu trả lời sau khi được kiểm duyệt (hiệu ứng gõ chữ phía client tuỳ chọn), thẻ xác nhận hoàn tiền, thông báo đồng ý bộ nhớ; thông báo kết quả duyệt hoàn tiền/xác nhận thanh toán/cập nhật phiếu bằng huy hiệu chưa đọc. **Thuộc cổng phát hành cùng Plan A phase 7 và Plan B phase 1.**

## Requirements

- Functional: luồng SSE, nút dừng, mở lại hội thoại gần nhất, huy hiệu thông báo, đồng ý lưu bộ nhớ, hiển thị mã phiếu khi handoff.
- Non-functional: không gửi lại lượt khi mất kết nối; tôn trọng `prefers-reduced-motion`.

## Architecture

- `EventSource` không gửi được POST/header → dùng `fetch` + `ReadableStream` tự parse SSE (`sse-client.ts`) với `AbortController`.
- Sự kiện (Plan A phase 7): `status` (chip "Đang tra đơn hàng…"), `message` (câu trả lời cuối đã qua `guard_output`, nhận trọn một lần), `confirm_required` (thẻ xác nhận), `done`, `error`. Không có sự kiện token trực tiếp. Gửi tin lúc thread đang chờ xác nhận nhận 409 kèm hành động đang chờ; có nút huỷ → `cancel-pending`. `thread_id` do server cấp.
- Mất kết nối giữa chừng: không tự gửi lại; tải lại hội thoại từ `GET /v1/conversations/{id}`.
- **Cắt:** không có UI danh sách/xoá hội thoại (chat mở hội thoại gần nhất, có nút "Cuộc trò chuyện mới"); không có chuông thông báo. Thông báo: một lần fetch khi điều hướng/focus tab và poll 60 giây, hiển thị huy hiệu chưa đọc + trang liệt kê; nội dung lấy từ bảng ánh xạ `notification-copy.ts` (phase 6).
- Đồng ý bộ nhớ: lần chat đầu hiện thông báo + nút đồng ý; gọi `POST /v1/me/memory/consent`; có chỗ thu hồi và xem/xoá bộ nhớ trong cài đặt chat.
- **nginx (diff cụ thể):** `location = /api/v1/chat/stream` riêng với `proxy_buffering off; proxy_http_version 1.1; proxy_set_header Connection ""; proxy_read_timeout 300s;`; backend đặt `X-Accel-Buffering: no`; các `location /api/` khác giữ timeout thường; dùng chung snippet header an toàn của phase 5.

## Related Code Files

- Create: `frontend/src/lib/{sse-client,notification-copy}.ts`, `frontend/src/chat/{use-chat-stream,message-view,memory-consent}.tsx`, `frontend/src/components/unread-badge.tsx`, `frontend/src/pages/notifications-page.tsx`, tests
- Modify: `frontend/src/components/{chat-widget,approval-card}.tsx`, `frontend/nginx.conf.template`, `frontend/src/components/site-layout.tsx`

## Implementation Steps

1. Parser SSE + hook `useChatStream` (messages, trạng thái công cụ, pending confirm, đang chạy, lỗi, xử lý 409).
2. Cập nhật widget: chip trạng thái, câu trả lời hiện sau kiểm duyệt, nút dừng, thẻ xác nhận payload mới, hiển thị phiếu handoff.
3. Đồng ý bộ nhớ + cài đặt xem/xoá.
4. Huy hiệu thông báo + trang liệt kê + đánh dấu đã đọc.
5. nginx location SSE riêng.
6. Test (MSW/SSE giả): nhận `status`/`message`, ngắt giữa chừng, dừng bằng nút, parse sự kiện phân mảnh, 409, đồng ý bộ nhớ.

## Todo List

- [ ] SSE client + hook
- [ ] Widget mới (chip, confirm, 409, handoff)
- [ ] Đồng ý/xoá bộ nhớ
- [ ] Huy hiệu + trang thông báo
- [ ] nginx location SSE + test qua nginx thật

## Success Criteria

- [ ] Chip trạng thái hiện ngay trên LLM thật; câu trả lời chỉ hiện sau kiểm duyệt; nút dừng huỷ lượt phía server
- [ ] Ngắt mạng giữa lượt không tạo tin trùng; thread đang chờ xác nhận không bị kẹt
- [ ] Nhân viên duyệt xong, khách thấy thông báo trong vòng ≤ 60 giây

## Risk Assessment

Proxy nuốt luồng SSE → test qua nginx thật trong compose, không chỉ Vite dev.

## Security Considerations

Không lưu nội dung chat ngoài state phiên; dọn khi đăng xuất (phase 1); nội dung bot render dạng text/markdown an toàn (không innerHTML).

## Next Steps

Phase 5/6 dùng huy hiệu thông báo; phase 7 e2e kiểm tra luồng hoàn tiền qua chat.
