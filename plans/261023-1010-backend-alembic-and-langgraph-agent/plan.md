---
title: "Backend: Alembic/SQLAlchemy + auth + LangGraph/MCP support agent (Plan A)"
description: "Schema có version (Alembic + SQLAlchemy 2.0), đăng nhập JWT + RBAC, agent CSKH (router, HITL, memory, MCP tin cậy, handoff), nhân viên duyệt hoàn tiền, eval. Đã qua red-team, PM và BA review."
status: pending
priority: P1
branch: ""
tags: [backend, alembic, sqlalchemy, auth, langgraph, mcp, agent]
blockedBy: []
blocks: [261023-1100-checkout-staff-console-frontend]
created: "2026-10-23T03:06:11.869Z"
createdBy: "ck:plan"
source: skill
---

# Plan A: Alembic/SQLAlchemy + auth + agent

## Overview

Hiện tại: bảng tạo bằng `ensure_schema()` lúc API chạy; agent là 1 vòng ReAct + cổng duyệt do chính khách bấm (và `issue_refund` ghi hoàn tiền ngay — vi phạm quyết định "nhân viên duyệt", **không phát hành bản này**); `user_id` do client gửi; chưa có đăng nhập, guardrail, eval, tracing, hàng đợi phiếu hỗ trợ.
Mục tiêu: (1) schema có version bằng **Alembic + SQLAlchemy 2.0**, role DB tối thiểu; (2) **đăng nhập JWT + RBAC**; (3) agent CSKH theo slide Week 7 (workflow có router, MCP, HITL, memory, handoff); (4) **hoàn tiền do nhân viên duyệt** với quy trình/audit rõ; (5) quan sát + eval.
Checkout/thanh toán, console nhân viên, frontend: xem [Plan B](../261023-1100-checkout-staff-console-frontend/plan.md) (cùng bảng mốc M0-M3 ở đó).

## Kiến trúc đích

```
Frontend ─JWT─► API (FastAPI: auth, chat SSE, staff) ─token ký theo lời gọi─► MCP server (7 tool, role DB `mcp`) ─► Postgres+pgvector
                 │ LangGraph: guard_input → router(dính) → agent ⇄ tools
                 │            agent → confirm (khách xác nhận) → tools[request_refund → pending_staff]
                 │            agent(final) → guard_output(bộ đệm) → remember(có đồng ý) → END   (+ handoff → phiếu hỗ trợ)
                 ├─► Staff: duyệt/từ chối/chi trả hoàn tiền, xử lý phiếu (RBAC từ DB, audit chỉ-thêm)
                 ├─► worker: job dọn/hết hạn (khung ở phase 7)
                 └─► LLM / Embedding tự host (Qwen3-Embedding-0.6B, 1024 chiều, tối đa 2048 token)
migrate (one-shot, role migrator): alembic upgrade → tạo role/quyền → langgraph setup() → grants
```

## Phases

| Phase | Name | Effort | Mốc | Phụ thuộc | Status |
|-------|------|--------|-----|-----------|--------|
| 1 | [Preflight and decisions](./phase-01-preflight-and-decisions.md) (cổng go/no-go) | 2d | M0 | - | Completed (M0 GO, 2026-10-23) |
| 2 | [Alembic and SQLAlchemy foundation](./phase-02-alembic-and-sqlalchemy-foundation.md) | 2.5d | M1 | 1 | Pending |
| 3 | [Schema models and seed](./phase-03-schema-models-and-seed.md) | 5d | M1/M2 | 2 | Pending |
| 4 | [Auth and RBAC](./phase-04-auth-and-rbac.md) | 5d | M1 | 3 | Pending |
| 5 | [MCP server v2](./phase-05-mcp-server-v2.md) | 3d | M1 | 3 | Pending |
| 6 | [Agent graph v2](./phase-06-agent-graph-v2.md) | 6d | M1/M2 | 1, 5 | Pending |
| 7 | [API v2](./phase-07-api-v2.md) | 5.5d | M1/M2 | 4, 6 | Pending |
| 8 | [Observability and evals](./phase-08-observability-and-evals.md) | 2d | M2 | 6 | Pending |
| 9 | [Hardening and docs](./phase-09-hardening-and-docs.md) | 3.5d | M3 | 7, 8 | Pending |

Tổng ~34,5 ngày công (ước lượng lại sau review PM: trước đó 22, thiếu test, quyền DB, phiếu hỗ trợ, quy tắc hoàn tiền). Phase 4 và 5 làm song song được sau phase 3.

## Mốc giao hàng

1 developer làm tuần tự (D16). Bảng M0-M3 và cổng thoát ở [Plan B](../261023-1100-checkout-staff-console-frontend/plan.md#mốc-giao-hàng-dùng-chung-hai-plan). Thứ tự: giữ chiều ngang cho phase 1-3 (ràng buộc kỹ thuật), sau đó **lát dọc hoàn tiền (M1)** trước khi làm phần còn lại. Điều kiện lát dọc: không bỏ auth/kiểm tra IDOR, bản mỏng của guard "không khẳng định đã hoàn tiền" có từ M1, kiểm bằng LLM thật.

## Decision log (đã chốt 2026-10-23)

| # | Quyết định |
|---|-----------|
| D1 | JWT do chính backend cấp sau đăng nhập; không còn `user_id` từ client; gỡ hẳn `API_KEY` |
| D2 | **Nhân viên duyệt hoàn tiền**, không ngưỡng tự động. Agent chỉ tạo yêu cầu `pending_staff` sau khi khách xác nhận; tiền ra chỉ sau staff duyệt + ghi tham chiếu chi trả |
| D3 | Arize Phoenix tự host (có xác thực, chỉ mạng nội bộ) |
| D4 | Embedding `Qwen/Qwen3-Embedding-0.6B`, 1024 chiều, `https://your-api-model-host/embed/v1` (đã kiểm tra, không cần key) |
| D5 | Reset DB dev (`down -v`), không viết migration baseline |
| D6 | Tiếng Việt + tiếng Anh: agent trả lời theo ngôn ngữ khách; KB/prompt/eval song ngữ; giao diện web giữ tiếng Việt |
| D7 | SQLAlchemy 2.0 (model + autogenerate); truy vấn vector/tìm kiếm lai viết SQL thuần (có tham số) |
| D8 | Chia 2 plan; thanh toán: COD + chuyển khoản thủ công, interface cổng nhỏ (2 class), không route webhook |
| D9 | Streaming "kiểm tra rồi mới hiện": câu trả lời cuối giữ trong bộ đệm đến khi `guard_output` duyệt; trạng thái tool hiện ngay |
| D10 | Cắt phạm vi: 7 tool, bỏ Prometheus/LLM judge/cổng baseline, `guard_output` xác định, bỏ lớp `repos/` và load test |
| D11 | 3 role DB (`migrator`/`app`/`mcp`) từ phase 2-3; MCP không thấy `users`/`refresh_tokens`/`payout_info_enc`/`shipping_address` |
| D12 | **Quy tắc hoàn tiền và đơn** (chủ shop xác nhận số liệu): 7 ngày từ `delivered_at`; trần = tiền hàng đã thực thu, không ship trừ lỗi shop, trừ phần đã hoàn; 1 yêu cầu "sống" mỗi đơn, không tạo mới sau `paid_out`, bị từ chối/huỷ thì gửi lại được; chỉ hoàn khi payment `paid`; COD bắt đầu `processing`, payment `pending` đến khi staff thu; đơn đã trả rồi huỷ tự tạo refund `pending_staff`; chuyển khoản hết hạn 24h chỉ với payment `pending`, không gia hạn khi khách báo đã chuyển; khách điền thông tin nhận tiền ở trang đơn |
| D13 | **Chatbot v1:** tư vấn/tra đơn/giải thích điều kiện/gửi yêu cầu hoàn tiền/chính sách có trích dẫn; KHÔNG tạo/huỷ đơn, đổi địa chỉ, huỷ yêu cầu hoàn; khách chưa đăng nhập không chat; bộ nhớ có thông báo + đồng ý lần đầu, xem/xoá được; router không chắc → hỏi lại một lần rồi chuyển người (lệch có chủ đích so với slide); **hàng đợi phiếu hỗ trợ cho nhân viên**, SLA đề xuất 4 giờ làm việc (khiếu nại 2 giờ); nhân viên xem trích đoạn hội thoại có log truy cập |
| D14 | Cắt phạm vi Plan B + lát dọc + mốc M0-M3; ước lượng lại ~56 ngày cho 1 developer |
| D16 | Một developer làm tuần tự (~56,5 ngày, ≈ 12-13 tuần); frontend dùng mock theo OpenAPI v0 |
| D17 | Chưa dùng CI; script `scripts/check` chạy tay là cổng chất lượng |
| D18 | localhost cho dev; HTTPS + tên miền cho staging/production (cookie `Secure` luôn bật ở đó) |
| D19 | Go/no-go phase 1: ≥ 95% kịch bản probe đạt |
| D20 | `payout_info` mã hoá cấp ứng dụng (`PAYOUT_ENCRYPTION_KEY`), che khi hiển thị |
| D21 | Lưu trữ: hội thoại/checkpoint 180 ngày, trace 30 ngày, audit 24 tháng (cấu hình được) |
| D22 | Đối soát chuyển khoản thủ công từ app ngân hàng, bắt buộc nhập số tiền thực nhận |
| D23 | Phí ship 30.000₫, miễn phí từ 500.000₫, lấy từ cấu hình server |
| D15 | Plan A phase 3 là chủ duy nhất của schema `users/orders/order_items/refunds/support_tickets/notifications/status_events/kb_*`; Plan B chỉ thêm `payments` + view; một bảng sự kiện chung `status_events` (thay `refund_events`/`payment_events`/`order_events`) |

## Kết quả M0 / phase 1 (2026-10-23)

**GO** cho model chat tự host (probe 100% khi tắt chế độ suy luận; ngưỡng ≥ 95%); spike danh tính MCP, LangGraph đều PASS; `scripts/check` xanh; OpenAPI v0 đóng băng ở `docs/api/openapi-v0.yaml`. Chi tiết và các phát hiện ảnh hưởng phase 2-7 (model "thinking" phải tắt suy luận, extension `vector` cần superuser, adapter trả lỗi tool dạng nội dung, context phải truyền lại khi resume) ở cuối [phase 1](./phase-01-preflight-and-decisions.md).

## Không làm (YAGNI)

Multi-agent, planning, reflection loop, email xác minh/quên mật khẩu, MFA, xoá tài khoản/xuất dữ liệu (ghi roadmap), A2A, cổng thanh toán thật, Prometheus, LLM judge, upload ảnh lỗi sản phẩm, heuristic prompt-injection bằng từ khoá (hoãn đến khi eval cho thấy cần).

## Rủi ro chính

| Rủi ro | Giảm thiểu |
|--------|-----------|
| Model chat tự host chưa kiểm tra tool calling/structured output (lịch phụ thuộc vào đây) | Phase 1 là cổng go/no-go; không đạt thì lập lại phase 5-6 |
| Danh tính MCP bị giả mạo/phát lại | Token ký ngắn hạn theo từng lời gọi, khoá riêng, ký lúc thực thi, fail-closed (phase 5) |
| Nói sai về tiền cho khách khi stream | Bộ đệm + `guard_output` xác định (D9) |
| Auth tự xây dễ sai | argon2id, quyền đọc từ DB, `token_version`, refresh có ân hạn, secret fail-closed, rà soát bảo mật phase 9 |
| Ước lượng lạc quan; phạm vi lớn so với codebase hiện tại (~580 dòng) | Đã ước lại ~56 ngày, cắt theo D10/D14, làm theo lát dọc M1 |
| Hạ tầng thiếu: test frontend, docs; **chưa dùng CI** (quyết định validation) | Script `scripts/check` chạy tay trước mỗi mốc; test infra frontend ở Plan B phase 1; thêm CI khi mã nguồn có nền tảng runner |
| Nội dung không phải code: KB song ngữ, chính sách hoàn tiền, đối soát | Chủ shop sở hữu; chính sách trước M1, KB trước M2 |

## Dependencies

Chặn [Plan B](../261023-1100-checkout-staff-console-frontend/plan.md). Cổng phát hành khách-facing = **Plan A phase 7 + Plan B phase 1 + phase 2**.

## Red Team Review

### Session 1 — 2026-10-23 (Plan A)
**Findings:** 15 chính (15 accepted, 0 rejected) + nhóm phát hiện nhỏ đã gộp
**Severity breakdown:** 4 Critical, 9 High, 2 Medium
**Reviewers:** Security Adversary, Failure Mode Analyst, Assumption Destroyer, Scope & Complexity Critic (mọi phát hiện có bằng chứng `file:line`)

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | Danh tính MCP chưa chứng minh, HMAC phát lại được, secret chung cho phép mạo danh | Critical | Accept | Phase 1, 5, 6 |
| 2 | Streaming đi trước `guard_output` | Critical | Accept (D9) | Phase 6, 7 |
| 3 | Secret fail-open và tài khoản staff demo mặc định | Critical | Accept | Phase 2, 3, 4 |
| 4 | API vẫn chạy DDL LangGraph lúc khởi động | Critical | Accept | Phase 2 |
| 5 | Alembic vs bảng LangGraph; downgrade extension; rollback | High | Accept | Phase 2, 3 |
| 6 | Idempotency hoàn tiền mâu thuẫn, số tiền do LLM, không có đường huỷ | High | Accept | Phase 3, 5, 7 |
| 7 | Chat vào thread đang chờ xác nhận; bộ đếm tool; scope; batch trộn | High | Accept | Phase 6, 7 |
| 8 | Khoá advisory/pool/ownership/thread_id | High | Accept (lease) | Phase 2, 3, 7 |
| 9 | Router theo từng lượt làm gãy luồng hoàn tiền | High | Accept (intent dính) | Phase 6, 8 |
| 10 | Rate limit/lockout sai chỗ, IP sau nginx, cổng 8000 | High | Accept | Phase 4, 9 |
| 11 | Token revocation, refresh không ân hạn, đăng ký nhận `role` | High | Accept | Phase 4 |
| 12 | Prompt injection bền vững qua memory/KB, XSS console | High | Accept | Phase 6, Plan B phase 5 |
| 13 | Phân quyền DB đến quá muộn | High | Accept (D11) | Phase 2, 3 |
| 14 | Quan sát lộ dữ liệu; Prometheus/judge/baseline thừa | Medium | Accept (D10) | Phase 8 |
| 15 | TTL bộ nhớ không chạy, `refresh_on_read` | Medium | Accept | Phase 6 |

### Session 2 — PM và BA review (hai plan)
Báo cáo: `plans/reports/from-project-manager-to-planner-chatbot-feature-clarification-report.md`, `...-plan-a-and-b-delivery-review-report.md`, `from-business-analyst-to-planner-plan-a-and-b-requirements-review-report.md`. Đã áp dụng (D12-D15): quy tắc hoàn tiền/đơn; phiếu hỗ trợ có hàng đợi; chính sách bộ nhớ (đồng ý, retention); hợp nhất schema `orders` và bảng sự kiện; mốc M0-M3 và ước lượng lại; khung `worker` kéo lên phase 7 để Plan B phase 6 không phụ thuộc phase cuối.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01 → phase-09 (Plan A); plan.md, phase-01 → phase-07 (Plan B)
- Decision deltas checked: 15 (D1-D15)
- Reconciled stale references: 3 (phụ thuộc Plan B phase 6 → worker của phase 9 sai mốc: kéo khung worker lên phase 7; "~20 ca eval" còn sót ở phase 8 → ~30; lỗi chính tả ở phase 6). Đã quét: `refund_events`/`payment_events`/`order_events` (chỉ còn trong câu loại bỏ), `addresses`, `payment_status`, `check_refund_eligibility`, `API_KEY`, `repos/`, Prometheus, mốc worker
- Unresolved contradictions: 0 (câu hỏi mở dành cho chủ shop ở Plan B `plan.md`)

## Validation Log

### Session 1 — 2026-10-23
**Trigger:** sau red-team Plan B, review PM/BA và áp dụng toàn bộ quyết định (`/ck:plan validate`)
**Questions asked:** 8 (bước kiểm chứng đã bỏ vì cả hai plan đã có Red Team Review kèm bằng chứng)

#### Questions & Answers

1. **[Assumptions]** Ai sẽ triển khai? (1 developer tuần tự ~56 ngày | 2 developer 1 BE + 1 FE ~9-10 tuần | 3 người)
   - **Answer:** 1 developer làm tuần tự
   - **Rationale:** lịch, khả năng song song, ownership phase.
2. **[Architecture]** Nền tảng CI/nơi lưu mã nguồn? (GitHub Actions | GitLab CI | chưa CI, chạy tay)
   - **Answer:** Chưa dùng CI, chạy tay bằng script
   - **Rationale:** cổng chất lượng của kế hoạch dựa nhiều vào test; phải thay bằng script chạy tay có kỷ luật.
3. **[Risks]** Môi trường chạy thật/demo? (localhost + HTTPS staging/prod | LAN HTTP | chưa quyết)
   - **Answer:** localhost cho dev, HTTPS + tên miền cho staging/production
   - **Rationale:** cookie `Secure` của refresh token và việc không mở cổng API.
4. **[Risks]** Ngưỡng go/no-go phase 1 cho model chat? (≥ 95% | ≥ 80% + retry | quyết sau)
   - **Answer:** ≥ 95% kịch bản đạt
   - **Rationale:** toàn bộ lịch phụ thuộc năng lực tool calling.
5. **[Architecture]** Bảo vệ `payout_info`? (mã hoá cấp ứng dụng | lưu rõ + hạn chế quyền)
   - **Answer:** Mã hoá cấp ứng dụng + che khi hiển thị
   - **Rationale:** dữ liệu tài khoản ngân hàng của khách; thêm ~0,5 ngày (phase 7).
6. **[Assumptions]** Thời hạn lưu trữ? (180/30/24 tháng | 90/14/12 tháng | chủ shop chốt sau)
   - **Answer:** Hội thoại/checkpoint 180 ngày, trace 30 ngày, audit 24 tháng
   - **Rationale:** cấu hình worker dọn dữ liệu và chính sách riêng tư (nên rà thêm quy định pháp lý).
7. **[Scope]** Đối soát chuyển khoản? (thủ công nhập số tiền thực nhận | import CSV)
   - **Answer:** Thủ công từ app ngân hàng
   - **Rationale:** đúng phạm vi; import CSV (+2-3 ngày) ngoài phạm vi.
8. **[Assumptions]** Phí ship và ngưỡng miễn phí? (30.000₫/500.000₫ | khác)
   - **Answer:** Giữ 30.000₫, miễn phí từ 500.000₫
   - **Rationale:** server là nguồn duy nhất, client bỏ hằng số.

#### Confirmed Decisions
- D16-D23 (xem Decision log).

#### Action Items
- [x] Thay CI bằng `scripts/check` (phase 1, 2, 4, 8; Plan B phase 1, 7)
- [x] Đổi `payout_info` thành `payout_info_enc` mã hoá cấp ứng dụng (phase 3, 5, 7, 9; Plan B phase 5)
- [x] Cấu hình ship/hoàn tiền (phase 2; Plan B phase 3)
- [ ] Chủ shop xác nhận số ngày hoàn tiền (7), nội dung KB bảo hành/đổi trả/vận chuyển; rà quy định bảo vệ người tiêu dùng và dữ liệu cá nhân

#### Impact on Phases
- Phase 1: `scripts/check`, ngưỡng go/no-go 95%, thêm thư viện `cryptography`.
- Phase 2: biến cấu hình mới (`PAYOUT_ENCRYPTION_KEY`, ship, hạn hoàn); `scripts/check` thay CI.
- Phase 3, 5, 7, 9; Plan B phase 1, 3, 5, 7: xem `<!-- Updated: Validation Session 1 -->` trong từng file.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01 → phase-09 (Plan A); plan.md, phase-01 → phase-07 (Plan B)
- Decision deltas checked: 8 (D16-D23)
- Reconciled stale references: 14 (nhắc CI/GitHub ở 7 chỗ; `payout_info` → `payout_info_enc` ở nhiều file; tổng effort Plan A/B)
- Unresolved contradictions: 0
