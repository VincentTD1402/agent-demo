---
phase: 1
title: "Preflight and decisions"
status: completed
priority: P1
effort: "2d"
milestone: "M0"
dependencies: []
---

# Phase 1: Preflight and decisions

## Overview

Các quyết định D1-D15 đã chốt (xem `plan.md`). Phase này là **cổng go/no-go và mốc M0**: chạy các spike để biết thiết kế có khả thi trước khi viết code sản phẩm. Kết quả xấu thì dừng và lập lại phase 5-6.

## Requirements

- Functional: biết năng lực model chat tự host; chứng minh truyền danh tính ký cho từng lời gọi tool sang MCP.
- Non-functional: spike chỉ thêm script trong `backend/scripts/`, không đổi code sản phẩm.

## Implementation Steps

1. `backend/scripts/probe_model.py` (`uv run`): `/v1/models`, chat, tool calling (1 và song song), structured output (`json_schema`/`json_mode`), `tool_choice`, streaming, độ trễ. Embedding: xác nhận 1024 chiều, câu tiếng Việt có dấu (gửi UTF-8 đúng), nội dung vượt 2048 token trả lỗi gì. Xuất `probe-report.json`.
2. Kiểm tra chất lượng model với câu hỏi tiếng Việt, tiếng Anh và trộn (nhận intent, gọi tool, trả lời đúng ngôn ngữ).
3. **Spike danh tính MCP (bắt buộc đạt):** token ký ngắn hạn gắn header cho từng lời gọi qua `langchain-mcp-adapters` 0.3.2 (header theo lời gọi ở `tools.py:440-454`, `runtime` được tiêm theo tên tham số ở `langgraph/prebuilt/tool_node.py:2038-2040`) và MCP đọc được header qua FastMCP `request_context.request`. Chứng minh ký **tại lúc thực thi tool** (sau resume), kể cả khi resume trễ hơn TTL token.
4. Spike LangGraph 1.2: `context_schema` phải truyền lại ở **mọi** lần gọi kể cả `Command(resume=...)`; `interrupt`+`Command` async; store `ttl` + `start_ttl_sweeper`; `stream_mode="messages"` lọc theo node; `AsyncPostgresSaver/Store` nhận pool riêng.
5. Xác nhận `unaccent()` cần hàm bọc IMMUTABLE để làm index; xác nhận `CREATE EXTENSION` cần quyền gì với image pgvector.
6. Chốt thư viện auth/kiểm tra: `argon2-cffi`, `PyJWT`, `cryptography` (mã hoá `payout_info_enc`), `pip-audit`; sinh lại `uv.lock`.
7. Xác nhận quy trình test dùng Postgres của compose (Docker Desktop phải bật; Windows 11 Home cần WSL2).
8. **Cổng kiểm tra chạy tay** (chưa dùng CI, quyết định validation): script `scripts/check` (PowerShell + sh) chạy lint, typecheck, `pytest` trên Postgres của compose, `alembic check`, `pip-audit`, và kiểm tra frontend khi có (`typecheck`, `test`, `npm audit`); chạy trước mỗi mốc và mỗi lần merge nhánh. Thêm CI khi mã nguồn được đưa lên nền tảng có runner. <!-- Updated: Validation Session 1 - không CI, script kiểm tra tay -->
   Ngưỡng go/no-go: **≥ 95%** kịch bản probe đạt (tool calling, structured output, trả lời đúng ngôn ngữ); dưới ngưỡng thì dừng và lập lại phase 5-6. <!-- Updated: Validation Session 1 - ngưỡng go/no-go 95% -->
9. **Đóng băng OpenAPI v0** (chat, hoàn tiền, phiếu, thông báo, auth, staff) làm hợp đồng cho frontend dùng mock song song.
10. Chốt các câu hỏi cho chủ shop còn mở (số ngày hoàn tiền, KB bảo hành/đổi trả/vận chuyển, đội ngũ, đối soát chuyển khoản).

## Todo List

- [x] Chạy `probe_model.py` + ghi `probe-report.json`
- [x] Spike danh tính MCP + LangGraph
- [x] Script `scripts/check` + OpenAPI v0
- [x] Ghi go/no-go vào `plan.md`

## Success Criteria

- [x] `probe-report.json` kết luận rõ: tool calling, structured output, `tool_choice`, dims embedding = 1024, chất lượng vi/en; mỗi nhóm ≥ 95%
- [x] Spike danh tính MCP đạt (token ký theo lời gọi, hết hạn thì bị từ chối đúng lý do, thiếu context thì fail-closed)
- [x] **Go/no-go:** GO (nếu model không có tool calling → dừng, lập lại phase 5-6)

## Risk Assessment

Model chat không hỗ trợ tool calling → thiết kế agent phải đổi; phát hiện ở đây là rẻ nhất. Spike danh tính không đạt → không bỏ đoạn ghi đè danh tính trong node agent, thiết kế lại cơ chế trước khi sang phase 5.

## Security Considerations

Không đưa secret/khoá thật vào `probe-report.json`; spike chạy với dữ liệu giả; token ký theo lời gọi phải fail-closed khi sai/hết hạn/phát lại.

## Next Steps

Go → phase 2. No-go → lập lại phase 5-6 và ước lượng lại trước khi tiếp tục.

## Kết quả thực thi (2026-10-23)

**Go/no-go: GO.** Probe (`backend/scripts/probe_model.py`, 3 lần/kịch bản, 10 kịch bản): tool calling 100%, structured output 100% (`json_schema` dùng được), ngôn ngữ vi/en 100%, streaming 100%; độ trễ p50 0,32 giây; embedding 1024 chiều, tiếng Việt có dấu OK, nội dung quá giới hạn trả `BadRequestError`. Báo cáo: `backend/scripts/probe-report.json` (không chứa secret).

Spike danh tính MCP (`spike_mcp_identity.py`): **PASS**. Spike LangGraph (`spike_langgraph.py`, Postgres tạm): **PASS**. `scripts/check` (ruff, pytest, pip-audit, frontend typecheck + npm audit): xanh. OpenAPI v0 (`docs/api/openapi-v0.yaml`): hợp lệ (32 đường dẫn, 22 schema).

**Phát hiện ảnh hưởng các phase sau:**
1. **Model là loại "thinking"**: mặc định suy luận ("Thinking Process: …") bị trộn vào `content`. Mọi lời gọi chat phải gửi `extra_body={"chat_template_kwargs": {"enable_thinking": false}}` (`app/llm.py`, phase 6; router, agent, remember, tóm tắt). Code agent hiện chạy trong compose chưa có cờ này nên có thể đang rò suy luận ra khách. Kịch bản ngôn ngữ cũng cần chỉ thị tường minh "trả lời theo ngôn ngữ của tin cuối" (model từng trả lời tiếng Việt cho câu hỏi tiếng Anh khi chỉ thị mơ hồ) và model có xu hướng bịa chính sách nếu không có KB (ví dụ tự nêu "đổi trả 7 ngày") → bắt buộc dựa vào `search_knowledge_base` + guard.
2. **Router `json_schema` phải có định nghĩa nhãn** trong prompt (không có thì "máy lỗi, hoàn tiền" bị phân thành `human_handoff`).
3. **Extension `vector` cần superuser** (không "trusted"); `pg_trgm` và `unaccent` thì role thường tạo được. Phase 2: bước đầu của bootstrap chạy bằng DSN superuser để `CREATE EXTENSION vector`, sau đó role `migrator` chạy `CREATE EXTENSION IF NOT EXISTS` (đã thử: chạy được khi extension đã có). `unaccent()` trực tiếp trong index bị từ chối, cần hàm bọc `immutable_unaccent()` (đã thử, chuẩn hoá "Điện thoại" → "dien thoai").
4. **Adapter 0.3.2 trả lỗi tool dưới dạng nội dung** ("Error executing tool …"), không ném ngoại lệ: agent sẽ thấy lỗi như một ToolMessage (phase 5/6 phải xử lý và test theo hành vi này). Header theo lời gọi qua `tool_interceptors` hoạt động; adapter tạo kết nối mới cho mỗi lời gọi nên phù hợp MCP stateless; tham số `ctx` của FastMCP không lọt vào schema LLM thấy.
5. **`context_schema` không được lưu trong checkpoint**: resume không truyền context thì `runtime.context` là `None` (đã xác nhận); phase 6/7 phải dùng một helper `build_context()` cho cả resume. Store TTL (`refresh_on_read=False`) + `sweep_ttl()` hoạt động; saver/store dùng pool riêng được; stream `updates` lọc theo tên node được (cổng `guard_output` khả thi).
6. **Công cụ:** `pip-audit.exe` bị chính sách Application Control của Windows chặn → dùng `python -m pip_audit`; `uvx` cũng không chạy được tệp thực thi (dùng `uvx --from <gói> python -m ...`); psycopg async trên Windows cần Selector loop khi chạy script ngoài Docker; `pytest` nâng lên 9.0.3 (sửa lỗ hổng `PYSEC-2026-1845`), `pytest-asyncio` 1.4.0.

**Đã thêm vào repo:** `backend/scripts/{probe_model,spike_mcp_identity,spike_langgraph}.py`, `scripts/{check.sh,check.ps1}`, `docs/api/openapi-v0.yaml`, dependency `PyJWT`, `argon2-cffi`, `cryptography` (dự phòng cho phase 4/7), dev `ruff`, `pip-audit`; cấu hình ruff trong `pyproject.toml`.
