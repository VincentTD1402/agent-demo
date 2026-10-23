---
phase: 6
title: "Agent graph v2"
status: pending
priority: P1
effort: "6d"
milestone: "M1 (bản mỏng) + M2 (đầy đủ)"
dependencies: ["261023-1010-backend-alembic-and-langgraph-agent#1", "261023-1010-backend-alembic-and-langgraph-agent#5"]
---

# Phase 6: Agent graph v2

## Overview

Nâng đồ thị lên workflow có router (intent dính), guard đơn giản, xác nhận của khách trước khi gửi yêu cầu hoàn tiền, handoff sang nhân viên qua phiếu, bộ nhớ dài hạn có cấu trúc và có đồng ý. Giữ nguyên tắc slide: khung do code vẽ, LLM chỉ quyết định bên trong node, rẽ nhánh bằng code. Chỉ bắt đầu khi phase 1 báo go.

**M1 làm bản mỏng:** `confirm`, tool scope, intent dính, `guard_output` chặn khẳng định tiền, `handoff`. **M2 hoàn thiện:** tóm tắt hội thoại, TTL bộ nhớ, đồng ý bộ nhớ, tinh chỉnh prompt theo eval.

## Architecture

```
START → guard_input ─blocked→ END (từ chối lịch sự, không gọi LLM)
      → router (intent dính) ─handoff trigger/hỏi lại thất bại→ handoff → END
             └→ agent ⇄ tools
                  agent ─request_refund→ confirm (interrupt: khách xác nhận) → tools | agent (từ chối)
                  agent(final) → guard_output (bộ đệm) → remember → END
```

**Phạm vi bot v1 (D13):** tư vấn sản phẩm (giá/tồn từ tool), tra đơn/danh sách đơn, giải thích điều kiện hoàn tiền, gửi yêu cầu hoàn tiền sau khi khách xác nhận, trạng thái yêu cầu, chính sách/bảo hành có trích dẫn. **Không** tạo/huỷ đơn, đổi địa chỉ, huỷ yêu cầu hoàn, xác nhận chuyển khoản, mã giảm giá, tư vấn y tế/pháp lý; khách chưa đăng nhập không chat (API 401).

**Handoff triggers** (chuyển bằng phiếu, `create_support_ticket` xác định, không qua LLM): (1) khách yêu cầu gặp người; (2) khiếu nại/pháp lý → `priority=high`; (3) đổi hàng, đổi địa chỉ, hàng hư khi nhận; (4) khách không đồng ý với kết quả từ chối hoàn tiền; (5) router không chắc chắn: **hỏi lại một lần**, vẫn không rõ thì chuyển; (6) lặp lại thất bại (lỗi tool/ngoài phạm vi liên tục). Phiếu: mã, order_id, category, tóm tắt 3-5 dòng không PII thừa, thread; không đính kèm toàn bộ hội thoại. Sau handoff bot chỉ nhắc mã phiếu cho chủ đề đó, các chủ đề khác vẫn trả lời. SLA đề xuất: phản hồi trong 4 giờ làm việc (khiếu nại 2 giờ), giờ làm việc T2-T7 8:30-17:30 (chủ shop xác nhận).

**Luồng hoàn tiền (D2/D12):** `lookup_order` cho điều kiện + trần → khách xác nhận (interrupt) → `request_refund` tạo `pending_staff` → bot nói "đã gửi yêu cầu, đang chờ nhân viên duyệt" → nhân viên duyệt ở console → khách nhận thông báo và điền thông tin nhận tiền ở trang đơn; hỏi lại thì `get_refund_status`. Bot không bao giờ chi tiền.

**Quy tắc hội thoại:** tối đa ~120 từ/tin, ≤ 3 sản phẩm/lượt, trả lời theo ngôn ngữ tin gần nhất (mơ hồ → tiếng Việt), hỏi làm rõ tối đa 2 câu và không hỏi điều tool tra được, từ chối theo 3 phần (không làm được + lý do ngắn + việc thay thế), không emoji. Từ ngữ theo trạng thái: `pending_staff` → "đã gửi yêu cầu"; `approved` → "đã duyệt"; chỉ `paid_out` mới được nói "đã hoàn tiền". Giá/tồn kèm "tại thời điểm tra cứu".

State `AgentState`: `messages`, `lang`, `intent`, `confidence`, `tool_calls_used` (reset mỗi lượt), `summary`. Danh tính đi qua `context_schema`, dựng bằng **một helper duy nhất** cho chat, stream và **resume**; thiếu context → lỗi.

| Node | Việc chính |
|------|-----------|
| guard_input | giới hạn độ dài, bỏ ký tự điều khiển, che số thẻ/CCCD cho log; reset bộ đếm tool (heuristic injection hoãn đến khi eval cho thấy cần) |
| router | structured output `{label, lang, confidence}`; intent dính (chỉ đổi khi tin cậy cao; bỏ qua khi đang có luồng hoàn tiền mở; câu ngắn kế thừa intent trước) |
| agent | prompt Role/Goal/Backstory theo intent; scope: advice→search+kb, order→orders+kb, refund→orders+refunds+kb, faq→kb; dữ liệu tool/KB bọc `<data>` (không phải lệnh); cắt/tóm tắt lịch sử **không tách cặp tool_call/ToolMessage**; sửa mâu thuẫn trong prompt hiện tại (vừa "nêu giá theo công cụ" vừa "ngoài phạm vi: giá") |
| tools | ToolNode **kiểm phạm vi theo intent tại đây** (tên tool ngoài danh sách → ToolMessage lỗi); wrapper ký token danh tính cho từng lời gọi (phase 5) |
| confirm | chỉ chạy khi batch **đúng một** `request_refund`; batch trộn → trả ToolMessage bảo agent gọi riêng; payload `interrupt({action, order, amount, reason, max_refundable})`; tác dụng phụ chỉ ở `tools` sau đó |
| guard_output | **xác định, không dùng LLM**: giữ câu trả lời cuối trong bộ đệm; chặn câu khẳng định tiền đã hoàn/đã duyệt/đã chi (vi + en) khi trạng thái refund của lượt chưa tương ứng; chặn → viết lại 1 lần, vẫn sai → câu an toàn. Chỉ nội dung qua guard mới tới khách (D9) |
| remember | **chỉ khi `users.memory_consent_at` có giá trị** (khách thấy thông báo + đồng ý lần đầu ở frontend; thu hồi được); tối đa 3 mục có cấu trúc (`preferred_category`, `preferred_brand`, `language`, `issue_type`), không văn bản tự do/PII |
| handoff | gọi `create_support_ticket` xác định, trả mã phiếu và thời gian dự kiến |

Bộ nhớ: namespace `(user_id, "memory")`; `ttl` 180 ngày, `refresh_on_read=False`, sweeper trong lifespan; nội dung đưa vào prompt là khối dữ liệu đóng khung. Giới hạn: `recursion_limit`, tối đa 6 lần gọi tool/lượt, LLM retry/timeout, lỗi tool vào `ToolMessage`.

## Related Code Files

- Create: `backend/app/agent/{state,context}.py`, `backend/app/agent/nodes/{guard_input,router,agent,tools,confirm,guard_output,remember,handoff}.py`, `backend/app/agent/prompts/*.py`, `backend/app/agent/guards/{claims,pii}.py`, `backend/app/agent/tool_scopes.py`, `backend/app/agent/identity.py`
- Modify: `backend/app/agent/{graph,routing,runtime}.py` (runtime: `ttl` + sweeper + pool), `backend/tests/test_agent_graph.py` (viết lại: 4 test cũ dựa vào ghi đè `user_id`/metadata checkpoint; tách nhiều file)
- Delete: `backend/app/agent/nodes.py`

## Implementation Steps

1. State + context + helper `build_context()`; node `tools` ký danh tính lúc thực thi; bỏ ghi đè `tool_calls` ở node agent chỉ **sau khi** spike phase 1 đạt.
2. Router structured output (fallback parse JSON theo probe), intent dính, triggers handoff.
3. Tool scope kiểm tại node `tools`; test tên tool ảo/ngoài scope.
4. `confirm` + `guard_output` xác định có bộ đệm + `handoff` (bản mỏng cho M1).
5. Cắt/tóm tắt hội thoại pair-safe; bọc dữ liệu tool/KB; `remember` có đồng ý + TTL; viết lại prompt theo quy tắc hội thoại (M2).
6. Test LLM giả: định tuyến + intent dính nhiều lượt ("hoàn tiền" → "A101" → "ok"), scope tool, hoàn tiền xác nhận/từ chối, batch trộn, hết ngân sách, bộ đếm reset, `guard_output` chặn câu "đã hoàn tiền xong" khi chưa `paid_out`, từng trigger handoff tạo phiếu đúng category/priority, resume thiếu context bị từ chối, memory không lưu khi chưa đồng ý, TTL hết hạn không trả về.

## Todo List

- [ ] State/context/identity + tools node (M1)
- [ ] Router intent dính + handoff triggers (M1)
- [ ] confirm + guard_output + handoff (M1)
- [ ] Tóm tắt hội thoại, remember có đồng ý + TTL, prompt mới (M2)
- [ ] Bộ test LLM giả đầy đủ

## Success Criteria

- [ ] Toàn bộ test xác định pass (không cần server model)
- [ ] Không có đường nào gọi `request_refund` khi khách chưa xác nhận
- [ ] Luồng hoàn tiền nhiều lượt không mất tool; bot không bao giờ nói "đã hoàn tiền" trước `paid_out`
- [ ] Mỗi trigger handoff tạo phiếu đúng; bộ nhớ không lưu khi chưa đồng ý

## Risk Assessment

Router sai làm nghẽn luồng → intent dính + hỏi lại, đo bằng eval (phase 8). `guard_output` quá chặt → chỉ chặn nhóm khẳng định tiền/trạng thái, bắt đầu log-only rồi bật chặn khi eval ổn. Bộ đệm làm chậm hiện chữ → UI hiện chip trạng thái (Plan B). Slide gợi ý "chuyển ngay khi không chắc", plan chọn "hỏi lại một lần rồi chuyển" (lệch có chủ đích, ghi D13).

## Security Considerations

Chống prompt injection bằng đóng khung dữ liệu, tool scope kiểm ở `tools`, guard xác định, token danh tính ký theo lời gọi; bộ nhớ không văn bản tự do và chỉ lưu khi đồng ý; phiếu không chứa PII thừa.

## Next Steps

Phase 7 (API) bọc đồ thị; phase 8 đo hành vi bằng eval; Plan B phase 2/5 hiển thị chat và hàng đợi phiếu.
