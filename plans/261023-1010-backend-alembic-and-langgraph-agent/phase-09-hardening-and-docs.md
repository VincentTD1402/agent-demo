---
phase: 9
title: "Hardening and docs"
status: pending
priority: P2
effort: "3.5d"
milestone: "M3"
dependencies: ["261023-1010-backend-alembic-and-langgraph-agent#7", "261023-1010-backend-alembic-and-langgraph-agent#8"]
---

# Phase 9: Hardening and docs

## Overview

Đưa về trạng thái vận hành được: healthcheck thật, job dọn dữ liệu trên worker dùng chung, cấu hình triển khai an toàn, rà soát bảo mật, hoàn thiện tài liệu. (Phân quyền DB đã làm ở phase 2-3; tài liệu từng hành vi được viết ngay trong phase tạo ra nó, phase này tổng hợp.)

## Requirements

- Functional: `/ready` kiểm DB + MCP + LLM + embedding + số dòng thiếu embedding; worker dọn dữ liệu; runbook migration/rollback/xoay secret.
- Non-functional: không bí mật nào trong repo; giới hạn song song gọi LLM; API không publish cổng ra host khi chạy thật.

## Implementation Steps

1. `/ready` kiểm DB, MCP (`tools/list`), LLM + embedding (cache 10 giây), báo số sản phẩm/chunk thiếu embedding; semaphore giới hạn song song LLM (`LLM_MAX_CONCURRENCY`).
2. **Thêm job vào service `worker`** (khung đã có từ phase 7; chỉ một worker cho cả hai plan) cho mọi việc dọn: checkpoint hội thoại đã đóng quá N ngày, hội thoại soft-delete, refresh token hết hạn, lease hết hạn; Plan B thêm job hết hạn đơn vào đây (không dựng worker thứ hai). Lệnh `reindex` KB.
3. Compose: resource limit, log rotation, healthcheck mọi service, `migrate` chạy trước; profile production **bỏ publish cổng 8000/DB**; tài liệu hoá HTTPS + HSTS.
4. **Triển khai và vận hành:** cấu hình deploy, thử backup/restore (`pg_dump`) và roll-forward migration, runbook (xoay secret gồm `JWT_SECRET`, `MCP_CONTEXT_KEY`, `PAYOUT_ENCRYPTION_KEY` — xoay khoá mã hoá cần giải mã lại `payout_info_enc` — và khôi phục), `.env` không bao giờ commit; retention thực thi bằng worker (hội thoại/checkpoint đóng 180 ngày, trace 30 ngày, audit 24 tháng — đã xác nhận ở validation, nên rà thêm quy định pháp lý); worker có heartbeat hiển thị ở `/ready`.
5. Smoke test (không phải load test): vài chat đồng thời với LLM giả để kiểm tra lease và pool, không đo hiệu năng.
6. Rà soát bảo mật: `ck:security-scan`, `code-reviewer` (auth, RBAC, token MCP, máy trạng thái hoàn tiền, role DB), `pip-audit`; thử injection và truy cập chéo.
7. Hoàn thiện `./docs` (hiện chưa có thư mục): `system-architecture.md` (ranh giới tin cậy, luồng hoàn tiền, ngân sách kết nối), `code-standards.md`, `codebase-summary.md`, `deployment-guide.md` (env theo tiến trình, migration roll-forward + backup, xoay `JWT_SECRET`/`MCP_CONTEXT_KEY`), `project-roadmap.md`, `project-changelog.md`.

## Todo List

- [ ] `/ready` đầy đủ + semaphore LLM
- [ ] Job dọn trong `worker` (khung từ phase 7) + hiển thị heartbeat ở `/ready`
- [ ] Compose production (không publish cổng) + backup/restore thử
- [ ] Rà soát bảo mật + `pip-audit`
- [ ] Hoàn thiện `docs/` (7 file)

## Success Criteria

- [ ] `docker compose up` môi trường sạch chạy end-to-end, `/ready` xanh
- [ ] Profile production không publish cổng API/DB; worker là tiến trình duy nhất chạy job dọn
- [ ] Báo cáo bảo mật không còn mục mức cao

## Risk Assessment

Worker chạy 2 bản làm dọn trùng → khoá advisory + job idempotent. Bỏ publish cổng làm khó debug local → có profile dev giữ cổng.

## Security Considerations

Không publish cổng API/DB ở profile production; backup mã hoá; runbook xoay `JWT_SECRET`/`MCP_CONTEXT_KEY`; worker chạy bằng role tối thiểu.

## Next Steps

Hoàn tất M3 cùng Plan B phase 7; cập nhật `project-roadmap.md` và `project-changelog.md`.
