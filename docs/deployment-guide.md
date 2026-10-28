# Deployment guide

Chạy toàn bộ bằng `docker compose up -d --build` (tạo `.env` bằng `scripts/init-env.sh` hoặc `scripts/init-env.ps1`). Cách dùng cho khách và chủ shop: `docs/luong-van-hanh-khach-hang-va-chu-shop.md`.

## Service và thứ tự khởi động

```
chatbot-db-prod (pgvector/pg17) ─> migrate (một lần) ─┬─> ingest (một lần) ─────────┐
redis                                                 └─> mcp-server ─> api ─> frontend (nginx)
```

| Service | Việc | Ghi chú |
|---|---|---|
| `chatbot-db-prod` | Postgres 17 + pgvector | volume `pgdata`, cổng `POSTGRES_PUBLIC_PORT` (mặc định 6024) chỉ để debug |
| `redis` | chưa được code dùng | giữ sẵn cho cache sau này |
| `migrate` | `alembic upgrade head` | thoát mã 0 thì các service sau mới chạy; tạo bảng, dữ liệu mẫu (sản phẩm, 3 đơn mẫu) |
| `ingest` | nạp `./documents` vào pgvector | idempotent; lỗi (vd endpoint embedding chưa lên) không chặn api; nạp lại: `docker compose run --rm ingest` |
| `mcp-server` | tool giỏ hàng/đơn/hoàn tiền cho agent | không publish cổng, cần `MCP_API_KEY`; có healthcheck |
| `api` | FastAPI: chat, tài liệu, sản phẩm, giỏ hàng, API nhân viên | cổng `API_PORT` (8000); đợi `mcp-server` khoẻ |
| `frontend` | giao diện React + nginx | cổng `FRONTEND_PORT` (3000); proxy `/api` -> `api` (gắn `X-API-Key` nếu có, truyền `X-Forwarded-For`, tắt buffering cho SSE) |

Mô hình LLM, embedding và reranker chạy **ngoài compose** (địa chỉ trong `.env`, mặc định `https://your-api-model-host/...`).

## Cấu hình (`.env`, mẫu trong `.env.example`)

| Nhóm | Biến chính |
|---|---|
| Postgres | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (`POSTGRES_HOST=chatbot-db-prod` trong Docker) |
| Mô hình | `LLM_API_URL`, `LLM_MODEL_NAME`, `EMBEDDING_API_URL`, `EMBEDDING_MODEL_NAME`, `RERANKER_API_URL`, `RERANKER_MODEL_NAME` |
| Bí mật | `MCP_API_KEY` (agent <-> MCP server), `STAFF_API_KEY` (API/trang nhân viên), `API_KEY` (tuỳ chọn: nginx gắn `X-API-Key` khi gọi API) |
| Chính sách shop | `SHIPPING_FEE_VND`, `FREE_SHIPPING_FROM_VND`, `REFUND_WINDOW_DAYS`, `MAX_QTY_PER_LINE` |
| Chống lạm dụng | `CHAT_RATE_*`, `CHAT_DUPLICATE_LIMIT`, `LOOKUP_*`, `MAX_ORDERS_PER_SESSION_PER_HOUR` |
| RAG | `RAG_TOP_K`, `RAG_TOP_N`, `RAG_MIN_SCORE`, `RAG_SUMMARIZE_AFTER`, ... |

Không commit `.env`. Đổi giá trị rồi chạy `docker compose up -d` để áp dụng.

## Vận hành

```
docker compose ps -a                       # trạng thái (migrate và ingest ở trạng thái Exited (0) là bình thường)
docker compose logs -f api mcp-server      # log agent (route, tool đã gọi), log tool
docker compose up -d --build               # cập nhật sau khi đổi code (build lại cả api, mcp-server, migrate, ingest)
docker compose down                        # dừng, giữ dữ liệu;  down -v: xoá cả dữ liệu
```

Sao lưu: `docker compose exec chatbot-db-prod sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup.sql`.

Dữ liệu dạy trợ lý ở `documents/` (bind mount chỉ đọc vào `api` và `ingest`), không nằm trong image.

## Lưu ý bảo mật khi đưa lên máy chủ thật

- Đổi mọi khoá trong `.env` (dùng `init-env`), không dùng giá trị mẫu `change-me...`.
- Chỉ mở cổng của `frontend`; không publish `API_PORT` và `POSTGRES_PUBLIC_PORT` ra Internet (đặt sau tường lửa hoặc bỏ dòng `ports` tương ứng). Đặt TLS (HTTPS) trước nginx.
- Giới hạn tần suất chat nằm trong bộ nhớ một tiến trình: chạy nhiều replica `api` thì mỗi replica đếm riêng.
- Thanh toán online hiện là mô phỏng; thay `PaymentGateway` (`backend/app/shop/payments.py`) khi tích hợp cổng thật.

## Kiểm thử

`uv run python -m pytest -q` (test nghiệp vụ trên Postgres cần `TEST_DATABASE_URL="host=... port=... user=... password=... dbname=postgres"`, một Postgres pgvector có quyền tạo database; không đặt thì các test đó bị bỏ qua), `uv run ruff check backend`, `cd frontend && npm run typecheck`.
