---
phase: 2
title: "Alembic and SQLAlchemy foundation"
status: pending
priority: P1
effort: "2.5d"
milestone: "M1"
dependencies: ["261023-1010-backend-alembic-and-langgraph-agent#1"]
---

# Phase 2: Alembic and SQLAlchemy foundation

## Overview

Dựng SQLAlchemy 2.0 (async) + Alembic, tách việc tạo schema khỏi lúc API chạy, tạo vai trò DB tối thiểu ngay từ đầu, và chốt hợp đồng cấu hình/kết nối.

## Requirements

- Functional: `alembic upgrade` chạy được local và trong compose; chạy song song an toàn; API chạy được bằng role **không có quyền DDL**.
- Non-functional: `scripts/check` chặn model lệch migration (`alembic check`, chạy tay trước mỗi mốc); chính sách **roll-forward-only**, revision chỉ thêm.

## Architecture

- **ORM là gì:** class Python (model) ánh xạ 1-1 với bảng; Alembic so model với DB để sinh migration. SQLAlchemy 2.0 kiểu `Mapped[...]`, session async qua `psycopg`.
- Phân vai: model + session cho miền giao dịch; SQL thuần (`text()`, bind parameter) cho tìm kiếm vector/lai. Không có lớp `repos/` riêng: truy vấn nằm trong module service dùng chúng.
- Vector: gói `pgvector` (`pgvector.sqlalchemy.Vector(1024)`).
- **Bootstrap** (service `migrate`, một lần): khoá advisory → `alembic upgrade head` → tạo role + cấp quyền → LangGraph `setup()` → `ALTER DEFAULT PRIVILEGES`/GRANT cho bảng LangGraph → thoát. `setup()` **bị gỡ khỏi `runtime.py`** của API.
- **3 role DB** (D11): `migrator` (DDL, chỉ `migrate` dùng), `app` (DML trên bảng nghiệp vụ + bảng LangGraph, API dùng), `mcp` (chỉ quyền tối thiểu, xem phase 3). Mật khẩu từng role từ env riêng.
- **Env contract theo tiến trình:** `ApiSettings`, `MigrateSettings`, `McpSettings` (mỗi cái chỉ có biến nó cần, secret thiếu/yếu thì không khởi động; `ApiSettings` bắt buộc `PAYOUT_ENCRYPTION_KEY` hợp lệ, `SHIPPING_FEE_VND=30000`, `FREE_SHIPPING_FROM_VND=500000`, `REFUND_WINDOW_DAYS=7`). <!-- Updated: Validation Session 1 - khoá mã hoá payout + cấu hình ship --> Liệt kê hết trong `.env.example`.
- **Ngân sách kết nối:** pool SQLAlchemy của API, pool riêng của LangGraph saver/store (`from_conn_string` nhận pool), pool MCP; tổng phải < `max_connections` Postgres, ghi công thức vào `deployment-guide`. Hằng số namespace cho khoá advisory (migrate ≠ khoá theo thread).
- Alembic `include_object` loại bảng LangGraph (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`, `store`, `store_vectors`) khỏi autogenerate và `alembic check`.
- Downgrade của revision extension là no-op (không `DROP EXTENSION`, vì bảng LangGraph phụ thuộc); rollback production = roll-forward, runbook có bước backup (`pg_dump`) trước upgrade.

## Related Code Files

- Create: `backend/alembic.ini`, `backend/migrations/{env.py,script.py.mako,versions/}`, `backend/app/db/{__init__,base,session,roles,bootstrap,langgraph_setup,locks}.py`, `backend/app/settings/{api,migrate,mcp}.py`, `backend/tests/db/{test_migrations,test_runtime_role}.py`
- Modify: `pyproject.toml` (sqlalchemy[asyncio], alembic, pgvector), `Dockerfile` (COPY `backend/migrations`, `backend/alembic.ini`), `docker-compose.yml` (service `migrate`, `depends_on: service_completed_successfully`, env riêng từng service), `backend/app/agent/runtime.py` (**bỏ `saver.setup()`/`store.setup()`**, nhận pool), `backend/app/main.py` (bỏ `ensure_schema`, pool có kích thước), `backend/app/mcp_server/server.py` (đọc `McpSettings`), `.env.example`
- Delete: `backend/app/shop/schema.py` (sau phase 3)

## Implementation Steps

1. Thêm dependency, sinh lại `uv.lock`; `alembic init`; `file_template` ngày + slug; naming convention constraint/index.
2. `env.py`: đọc `MigrateSettings`, đổi URL sang `postgresql+psycopg://`, `compare_type`, `compare_server_default`, `include_object` như trên.
3. `db/session.py`, `db/locks.py` (hằng số khoá), `db/roles.py` (tạo role + helper `grant_*`).
4. `db/bootstrap.py` theo thứ tự ở mục Architecture; lỗi thì thoát mã ≠ 0.
5. Compose: `migrate` (`restart: "no"`); `api`, `mcp-server` chờ hoàn tất; mỗi service chỉ nhận env của nó.
6. Gỡ `setup()` khỏi `runtime.py`; truyền pool riêng cho saver/store.
7. Test: upgrade → (downgrade từng bước đảo ngược được) → upgrade; `alembic check` sạch **sau khi** bootstrap đã chạy `setup()`; **API khởi động và chạy chat giả bằng role `app`** (thử `CREATE TABLE` bị từ chối); migrate 2 lần, 2 tiến trình song song.

## Todo List

- [ ] Alembic + `env.py` + `include_object`
- [ ] Service `migrate` + role DB + GRANT LangGraph
- [ ] Gỡ `setup()` khỏi `runtime.py`; chạy API bằng role `app`
- [ ] Settings theo tiến trình + ngân sách kết nối

## Success Criteria

- [ ] Volume trống: `migrate` thoát 0, `api` lên với role `app`, không còn DDL lúc runtime
- [ ] `alembic check` sạch kể cả khi bảng LangGraph đã tồn tại; không autogenerate nào đề xuất `DROP` bảng LangGraph
- [ ] Tổng kết nối tối đa của các tiến trình nằm trong `max_connections`

## Risk Assessment

Extension (`vector`, `pg_trgm`, `unaccent`) cần quyền cao: image pgvector đủ quyền; môi trường managed phải bật trước (ghi docs). Async SQLAlchemy trên Windows cần Selector loop khi chạy script ngoài Docker (đặt trong fixture test).

## Security Considerations

Ba role DB tối thiểu; API không có quyền DDL; secret theo tiến trình, thiếu/yếu thì không khởi động; bảng LangGraph được cấp quyền DML đúng phạm vi.

## Next Steps

Phase 3 (schema) dùng nền này; Plan A phase 9 hoàn thiện triển khai.
