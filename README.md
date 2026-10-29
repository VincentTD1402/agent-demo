# ShopMobile – Chatbot RAG + Agent mua sắm

Cửa hàng điện tử mẫu có trợ lý AI: tư vấn theo tài liệu (RAG), tra giá/tồn kho, thêm giỏ, đặt hàng (COD hoặc thanh toán giả lập), tra đơn, yêu cầu hoàn tiền (nhân viên duyệt). Có trang quản trị sản phẩm cho chủ shop.

Stack: FastAPI + LangGraph + MCP server, Postgres (pgvector), React + nginx. Mô hình LLM, embedding, reranker chạy **ngoài** compose.

## Yêu cầu
- Docker + Docker Compose
- Truy cập được các endpoint LLM / embedding / reranker (mặc định `https://your-api-model-host/...`, đặt trong `.env.example`)

## Chạy nhanh (Docker)

```bash
# 1. Tạo .env với khoá ngẫu nhiên (không ghi đè .env có sẵn)
scripts/init-env.sh          # Git Bash / Linux / macOS
# Windows PowerShell:  .\scripts\init-env.ps1

# 2. Nếu mô hình ở địa chỉ khác, sửa các dòng *_API_URL trong .env

# 3. Dựng và chạy
docker compose up -d --build
```

Khi khởi động, `migrate` tạo bảng + dữ liệu mẫu (16 sản phẩm, 3 đơn mẫu) và `ingest` nạp `./documents` vào vector DB; hai service này chạy một lần rồi thoát (Exited 0 là bình thường).

| Địa chỉ | Nội dung |
|---|---|
| http://localhost:3000 | Website + khung chat |
| http://localhost:3000/nhan-vien | Khu vực nhân viên (đăng nhập bằng `STAFF_API_KEY` trong `.env`) |
| http://localhost:8000/docs | Swagger API |

Kiểm tra: `docker compose ps` (api, frontend, mcp-server, db đều `healthy`).

## Thử nhanh
- Chat: "iPhone 15 giá bao nhiêu?", "chính sách hoàn tiền thế nào?", "thêm 1 tai nghe vào giỏ".
- Tra đơn mẫu: mã `SM000100` / `SM000101` / `SM000102`, SĐT `0900000001`.
- Nhân viên: vào `/nhan-vien` → tab **Sản phẩm** (thêm/sửa/xoá, tải ảnh) và **Hoàn tiền và đơn hàng** (duyệt hoàn tiền, cập nhật trạng thái).

## Lệnh thường dùng

```bash
docker compose logs -f api                 # xem log
docker compose run --rm ingest             # nạp lại tài liệu sau khi sửa documents/
docker compose up -d --build api mcp-server  # đổi code shop: build CẢ api và mcp-server
docker compose down                        # dừng (giữ dữ liệu)
docker compose down -v                     # dừng và XOÁ DB + ảnh sản phẩm
```

Dữ liệu nằm ở volume `pgdata` (DB) và `product-images` (ảnh tải lên); sao lưu cả hai trước khi `down -v`.

## Chạy tay để phát triển

Cần Python (quản lý bằng [uv](https://docs.astral.sh/uv/)) và Node 18+.

```bash
# DB: chỉ chạy Postgres
docker compose up -d chatbot-db-prod
# trong .env bỏ comment POSTGRES_HOST=localhost, POSTGRES_PORT=6024 và các URL localhost khác

uv sync
cd backend
uv run python -m alembic upgrade head
uv run python -m app.documents.ingest_cli          # nạp ./documents (chạy từ backend/ thì đặt DOCUMENTS_DIR=../documents)
uv run uvicorn app.main:app --reload --port 8000
uv run python -m app.mcp_server                    # terminal khác, cổng 8001
cd ..

cd frontend && npm install && npm run dev   # Vite dev (ảnh tải lên chỉ hiển thị qua nginx/Docker)
```

Test và lint:

```bash
# Cần Postgres pgvector tạm để chạy test DB (không đặt thì ~41 test bị skip)
export TEST_DATABASE_URL="host=localhost port=6025 user=langchain password=testpass dbname=postgres"
uv run python -m pytest
uv run ruff check backend scripts
cd frontend && npm run typecheck
# hoặc chạy gộp: scripts/check.sh (Windows: scripts\check.ps1)
```

## Cấu hình chính (`.env`)

| Nhóm | Biến |
|---|---|
| Mô hình | `LLM_API_URL`, `EMBEDDING_API_URL`, `RERANKER_API_URL` |
| Khoá | `MCP_API_KEY`, `STAFF_API_KEY`, `AUTH_SECRET_KEY`, `POSTGRES_PASSWORD` (do `init-env` sinh) |
| Cổng | `API_PORT` (8000), `FRONTEND_PORT` (3000), `POSTGRES_PUBLIC_PORT` (6024) |
| Chính sách shop | `SHIPPING_FEE_VND`, `FREE_SHIPPING_FROM_VND`, `REFUND_WINDOW_DAYS` |
| Chống spam | `CHAT_RATE_PER_MINUTE`, `LOOKUP_*`, `MAX_ORDERS_PER_SESSION_PER_HOUR` |

Không commit `.env`. Danh sách đầy đủ có trong `.env.example`.

## Cấu trúc

```
backend/app/   agent/ (LangGraph) · mcp_server/ · shop/ · products/ · documents/
frontend/src/  chat-widget · giỏ hàng · trang nhân viên
documents/     tài liệu chính sách + sản phẩm cho RAG
docs/          tài liệu chi tiết
```

## Tài liệu chi tiết
- [Hướng dẫn triển khai](docs/deployment-guide.md)
- [Luồng vận hành khách hàng và chủ shop](docs/luong-van-hanh-khach-hang-va-chu-shop.md)
- [Chat agent](docs/api/chat-agent.md) · [Nạp tài liệu](docs/api/document-ingestion.md) · [Danh mục sản phẩm](docs/api/product-catalog.md) · [Đơn hàng, MCP, nhân viên](docs/api/shop-orders-mcp-and-staff.md)

## Lưu ý
- Thanh toán online là **giả lập**; muốn cổng thật hãy cài `PaymentGateway` trong `backend/app/shop/payments.py`.
- Hoàn tiền luôn cần nhân viên duyệt.
- Có `init-env` thì khoá nhân viên được in ra màn hình; xem lại bằng `STAFF_API_KEY` trong `.env`.
