# Deployment guide (database)

Phần này chỉ mô tả lớp database; hướng dẫn triển khai đầy đủ bổ sung khi hoàn thiện triển khai.

## Thứ tự khởi động

`db` -> `migrate` (chạy một lần, thoát 0) -> `mcp-server` -> `api` -> `frontend`.

`migrate` (`python -m app.db.bootstrap`) làm theo thứ tự, giữ một khoá advisory suốt quá trình nên chạy song song nhiều bản vẫn an toàn:
1. Bằng DSN superuser (`BOOTSTRAP_DATABASE_URL`, chỉ bước này dùng): `CREATE EXTENSION vector`, tạo/đặt lại 3 role, quyền database/schema.
2. Bằng role `shopbot_migrator`: `alembic upgrade head` (extension `pg_trgm`, `unaccent`, hàm `immutable_unaccent()`, bảng).
3. `migrator`: tạo bảng LangGraph (`setup()` của checkpointer/store), GRANT, nạp dữ liệu mẫu nếu `SEED_DEMO_DATA=true` (mặc định `false`; chỉ đặt `true` khi dev; seed chạy trong một transaction).

API và MCP không chạy DDL. Bảng do migrator tạo sau này (kể cả `alembic upgrade` chạy trực tiếp, không qua bootstrap) tự cấp SELECT cho `shopbot_app` nhờ `ALTER DEFAULT PRIVILEGES`; quyền ghi và quyền của `shopbot_mcp` chỉ được cấp rõ ràng bởi bootstrap (`app/db/roles.py`), nên bảng mới cần quyền ghi/MCP thì thêm vào đó.

## Volume Postgres cũ (tạo trước khi có Alembic)

**Dev: `docker compose down -v` rồi `up` lại** (mất dữ liệu mẫu, `migrate` nạp lại nếu `SEED_DEMO_DATA=true`). Đây là cách khuyến nghị.

Volume cũ (tạo bằng `ensure_schema`) không dùng được trực tiếp: mọi bảng (cả bảng LangGraph `checkpoints*`, `store*`), sequence và hàm do superuser sở hữu; `migrate` sẽ dừng ở `alembic upgrade` (`must be owner of function immutable_unaccent` / `relation "products" already exists`). Bảng LangGraph mà không đổi chủ thì `GRANT` của migrator không có tác dụng và API bị `permission denied` ở lần chat đầu. Sau `stamp`, tên index/constraint cũ (`products_category_idx`, `products_pkey`, `*_check`...) lệch với model nên `alembic check` báo lệch mãi.

Đường giữ dữ liệu (đã thử trên bản sao DB dạng cũ, Postgres 17 + pgvector, `alembic check` sạch và `shopbot_app` đọc được; chưa thử trên dữ liệu thật). `pg_dump` sao lưu trước. Lệnh chạy từ thư mục gốc repo, `PG` = DSN superuser của DB cũ:

1. Chuẩn hoá tên và tạo hàm bằng superuser (`psql "$PG" -f recipe-before-stamp.sql`):
   ```sql
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   CREATE EXTENSION IF NOT EXISTS unaccent;
   CREATE OR REPLACE FUNCTION public.immutable_unaccent(text) RETURNS text
   LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
   AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$;
   ALTER INDEX products_category_idx RENAME TO ix_products_category;
   ALTER INDEX orders_user_idx RENAME TO ix_orders_user_id;
   ALTER TABLE products RENAME CONSTRAINT products_pkey TO pk_products;
   ALTER TABLE products RENAME CONSTRAINT products_slug_key TO uq_products_slug;
   ALTER TABLE products RENAME CONSTRAINT products_price_vnd_check TO ck_products_price_non_negative;
   ALTER TABLE orders RENAME CONSTRAINT orders_pkey TO pk_orders;
   ALTER TABLE orders RENAME CONSTRAINT orders_status_check TO ck_orders_status_valid;
   ALTER TABLE orders RENAME CONSTRAINT orders_total_vnd_check TO ck_orders_total_non_negative;
   ALTER TABLE refunds RENAME CONSTRAINT refunds_pkey TO pk_refunds;
   ALTER TABLE refunds RENAME CONSTRAINT refunds_order_id_fkey TO fk_refunds_order_id_orders;
   ALTER TABLE refunds RENAME CONSTRAINT refunds_amount_vnd_check TO ck_refunds_amount_positive;
   ```
2. `docker compose run --rm migrate` lần 1: tạo 3 role rồi **dừng với lỗi ở bước `alembic upgrade`** (dự kiến; role đã được tạo và giữ lại).
3. Đổi chủ sở hữu toàn bộ bảng (gồm LangGraph), sequence và hàm sang migrator (`psql "$PG" -f recipe-chown.sql`):
   ```sql
   DO $$
   DECLARE r record;
   BEGIN
     FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
       EXECUTE format('ALTER TABLE public.%I OWNER TO shopbot_migrator', r.tablename);
     END LOOP;
     FOR r IN SELECT sequencename FROM pg_sequences WHERE schemaname = 'public' LOOP
       EXECUTE format('ALTER SEQUENCE public.%I OWNER TO shopbot_migrator', r.sequencename);
     END LOOP;
   END $$;
   ALTER FUNCTION public.immutable_unaccent(text) OWNER TO shopbot_migrator;
   ```
4. Stamp bằng migrator (để `alembic_version` thuộc migrator): từ `backend/`, `ALEMBIC_DATABASE_URL=<DSN shopbot_migrator> python -m alembic stamp 0001`.
5. `docker compose run --rm migrate` lần 2: `upgrade` không làm gì, `setup()` không DDL, GRANT chạy đúng. Kiểm tra: `ALEMBIC_DATABASE_URL=<DSN migrator> python -m alembic check` phải in "No new upgrade operations detected".

Khi quyết định đường này cho dữ liệu thật, thử lại trên bản sao `pg_dump` trước.

## Role DB

| Role | Quyền | Dùng bởi |
|------|-------|----------|
| `shopbot_migrator` | DDL, sở hữu bảng | `migrate` |
| `shopbot_app` | SELECT `products`, `orders`, `refunds`; SELECT/INSERT/UPDATE/DELETE trên bảng LangGraph (không `alembic_version`, không DDL, không bảng tạm) | `api` |
| `shopbot_mcp` | SELECT `products`, `orders`, `refunds`; INSERT `refunds` (không DDL, không bảng tạm) | `mcp-server` |

API hiện không ghi bảng nghiệp vụ nào (chỉ đọc sản phẩm + ghi bảng LangGraph); mở rộng quyền ghi của `shopbot_app` ở phase thêm tính năng ghi. `INSERT refunds` của MCP là tạm thời vì tool `issue_refund` ghi thẳng; thu hồi khi hoàn tiền chuyển sang luồng nhân viên duyệt. `TEMPORARY` trên database bị thu khỏi PUBLIC.

Mật khẩu role đặt trong `.env` (`MIGRATOR_DB_PASSWORD`, `APP_DB_PASSWORD`, `MCP_DB_PASSWORD`): tối thiểu 12 ký tự và **chỉ** `[A-Za-z0-9]` (được nhúng vào URL kết nối không mã hoá), khác giá trị mẫu, và khác nhau đôi một cũng như khác `POSTGRES_PASSWORD`. `POSTGRES_PASSWORD` cùng ràng buộc; `POSTGRES_USER`/`POSTGRES_DB` chỉ chữ-số-gạch dưới. `migrate` kiểm tra và dừng với lỗi nêu tên biến (không in giá trị). Role là đối tượng toàn cluster: hai database trên cùng một cluster dùng chung tên `shopbot_*` và mỗi lần `migrate` đặt lại mật khẩu, nên chỉ dùng một bộ mật khẩu cho mỗi cluster. Môi trường managed (không có superuser): bật sẵn extension `vector`, tạo role thủ công rồi chạy `migrate` với DSN có quyền tạo role.

Lưu ý nhật ký server (M9): `CREATE/ALTER ROLE ... PASSWORD '<literal>'` gửi mật khẩu dạng văn bản; nếu Postgres bật `log_statement=ddl|all` hoặc lệnh lỗi với `log_min_error_statement`, mật khẩu nằm trong log của server. Không bật các tuỳ chọn đó trong lúc chạy `migrate`, hoặc coi log Postgres là dữ liệu nhạy cảm.

Biến cấu hình mỗi service nhận nằm tường minh trong `docker-compose.yml` (không `env_file`); `backend/tests/test_compose_env_forwarding.py` kiểm tra mọi biến của `ApiSettings`/`McpSettings`/`MigrateSettings` và mọi biến trong `.env.example` đều tới đúng service.

## Ngân sách kết nối

```
API (mỗi replica) = DB_POOL_MAX + SA_POOL_SIZE + SA_MAX_OVERFLOW + LANGGRAPH_POOL_MAX   (mặc định 5+5+2+5 = 17)
MCP (mỗi replica) = DB_POOL_MAX                                                          (mặc định 5)
migrate           = 2
Điều kiện: replicas_api*API + replicas_mcp*MCP + 2 < max_connections - superuser_reserved_connections
```

Postgres mặc định `max_connections=100`, `superuser_reserved_connections=3`. Test `backend/tests/db/test_runtime_role.py::test_connection_budget_fits_postgres_limit` kiểm tra cấu hình mặc định.
Khoá advisory của bootstrap dùng namespace `7101` (`app/db/locks.py`); khoá theo thread phải dùng namespace khác.

## Chính sách migration

Roll-forward-only: chỉ thêm revision mới, không sửa revision đã phát hành. Downgrade của revision đầu không `DROP EXTENSION` (bảng LangGraph phụ thuộc). Trước khi upgrade production: `pg_dump` sao lưu. `scripts/check` chạy `alembic check` để chặn model lệch migration: phải đặt `TEST_DATABASE_URL` (DSN superuser Postgres pgvector tạm) hoặc `ALEMBIC_DATABASE_URL`, nếu không script thất bại; `SKIP_DB_CHECKS=1` cố ý bỏ qua và kết thúc bằng cảnh báo `SKIPPED-DB-CHECKS` thay vì "TẤT CẢ ĐẠT".
