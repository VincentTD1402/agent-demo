# Deployment guide (database)

Phần này chỉ mô tả lớp database; hướng dẫn triển khai đầy đủ bổ sung khi hoàn thiện triển khai.

## Thứ tự khởi động

`db` -> `migrate` (chạy một lần, thoát 0) -> `mcp-server` -> `api` -> `frontend`.

`migrate` (`python -m app.db.bootstrap`) làm theo thứ tự, giữ một khoá advisory suốt quá trình nên chạy song song nhiều bản vẫn an toàn:
1. Bằng DSN superuser (`BOOTSTRAP_DATABASE_URL`, chỉ bước này dùng): `CREATE EXTENSION vector`, tạo/đặt lại 3 role, quyền database/schema.
2. Bằng role `shopbot_migrator`: `alembic upgrade head`: 0001 extension + hàm `immutable_unaccent()` + bảng cũ; 0002 `users`, `refresh_tokens`; 0003 catalog + embedding sản phẩm; 0004 `orders`, `order_items`, view `orders_for_agent`; 0005 `refunds`; 0006 hội thoại, phiếu hỗ trợ, thông báo, `status_events`, `tool_audit_log`; 0007 knowledge base. Mỗi revision tự cấp quyền cho bảng nó tạo.
3. `migrator`: tạo bảng LangGraph (`setup()` của checkpointer/store), `apply_grants` (cấp lại toàn bộ quyền, nguồn duy nhất: `app/db/roles.py`), nạp dữ liệu mẫu nếu `SEED_DEMO_DATA=true` (mặc định `false`; chỉ đặt `true` khi dev; seed chạy trong một transaction).

Seed (`app/shop/seed.py`) chỉ nạp vào bảng còn trống nên chạy lại không nhân đôi: 16 sản phẩm; 2 khách demo (id UUID cố định trong `app/shop/seed_data.py`, chưa có mật khẩu; **chỉ khi `ENV=dev`**); đơn mẫu `A100` (đã giao 2 ngày trước, còn hạn hoàn tiền), `A101` (đang giao), `A102` (COD đang xử lý), `B200` (của khách khác); KB song ngữ vi/en (hoàn tiền, bảo hành, vận chuyển, trả góp, đổi trả) với số liệu lấy từ `REFUND_WINDOW_DAYS`, `SHIPPING_FEE_VND`, `FREE_SHIPPING_FROM_VND`. Khách demo, đơn mẫu và tài khoản staff demo (`staff@shopbot.local`, cần thêm `STAFF_DEMO_PASSWORD` >= 12 ký tự, không có mật khẩu mặc định) chỉ được tạo khi `ENV=dev`; `ENV` khác chỉ nạp sản phẩm và KB. `ENV` mặc định `production`; `.env.example` đặt `ENV=dev` chỉ để dev, đừng sao chép nguyên sang production. Id khách demo nằm công khai trong bundle frontend nên **không phải danh tính an toàn cho production** (phase xác thực thay cơ chế này). Seed dừng với lỗi rõ ràng (và rollback cả lượt) nếu thiếu sản phẩm mẫu khi nạp đơn.

## Embedding (tách khỏi `migrate`)

Embedding không nằm trong cổng migrate: host embedding treo không làm treo deploy. Sau khi `migrate` xong, chạy riêng:

```
docker compose run --rm migrate python -m app.kb.reindex
```

Cần `EMBEDDING_BASE_URL` (không dùng lại `LLM_BASE_URL`) và `EMBEDDING_MODEL`; tuỳ chọn `EMBEDDING_API_KEY`, `EMBEDDING_TIMEOUT_S` (mặc định 30 giây mỗi lời gọi) và `--max-seconds N` (ngân sách tổng; hết hạn thì dừng sau lô hiện tại, giữ phần đã xong). Chỉ một lần chạy tại một thời điểm (khoá advisory `7102`, không chờ): lần thứ hai thoát mã 0 ngay với cảnh báo. Embedding của sản phẩm không còn hoạt động (`is_active = false`) bị xoá mỗi lần chạy. Lệnh chia nội dung KB thành chunk (xấp xỉ <= 400 token, tính theo 1200 ký tự) rồi embed chunk KB và sản phẩm. Idempotent nhờ `content_hash = sha256(model + nội dung)`: chạy lại không gọi endpoint cho dòng không đổi, đổi model/nội dung thì chỉ dòng đó được tính lại; lỗi giữa chừng giữ phần đã xong. Mã thoát: 0 xong (hoặc đã có lần chạy khác), 1 lỗi endpoint/DB, 2 thiếu cấu hình, 3 hết `--max-seconds`. `EMBEDDING_DIMS` cố định 1024 (cột `vector(1024)`): API, MCP và migrate từ chối giá trị khác khi khởi động. Đổi số chiều sau này là một revision `ALTER COLUMN ... TYPE vector(M)` kèm đổi hằng `FIXED_EMBEDDING_DIMS` (`app/settings/fixed_embedding_dims.py`) rồi chạy lại lệnh này. Chỉ `migrator` ghi bảng embedding/KB.

API và MCP không chạy DDL. Bảng do migrator tạo (kể cả `alembic upgrade` chạy trực tiếp, không qua bootstrap) tự cấp SELECT cho `shopbot_app` nhờ `ALTER DEFAULT PRIVILEGES`; quyền ghi của `shopbot_app` và mọi quyền của `shopbot_mcp` được cấp rõ ràng trong từng revision và lặp lại trong `apply_grants`. Thêm bảng cần quyền ghi/MCP thì cấp trong revision của bảng đó **và** thêm vào `roles.py`; `backend/tests/db/test_privileges.py::test_grants_after_upgrade_only_equal_grants_after_bootstrap` so ACL của hai đường và thất bại nếu lệch.

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

Khi quyết định đường này cho dữ liệu thật, thử lại trên bản sao `pg_dump` trước. Lưu ý: sau `stamp 0001`, lần `migrate` thứ hai chạy tiếp 0002-0007, trong đó 0004/0005 xoá đơn và hoàn tiền cũ nên **từ chối chạy nếu hai bảng này còn dòng** (xem Chính sách migration). Sao lưu rồi mới đặt `ALLOW_DESTROY_LEGACY_ORDERS=true` cho lần chạy đó (chỉ giữ được danh mục sản phẩm).

## Role DB

| Role | Quyền | Dùng bởi |
|------|-------|----------|
| `shopbot_migrator` | DDL, sở hữu bảng, ghi bảng embedding/KB (reindex) | `migrate` |
| `shopbot_app` | SELECT mọi bảng nghiệp vụ; INSERT/UPDATE `users`, `orders`, `order_items`, `refunds`, `support_tickets`, `notifications`; UPDATE `products`; INSERT/UPDATE/DELETE `refresh_tokens`, `conversations`; **chỉ INSERT** `status_events`, `tool_audit_log` (kèm trigger chặn UPDATE/DELETE); DML bảng LangGraph. Không DELETE `orders`/`refunds`/`users`/`products`, không ghi KB/embedding, không `alembic_version`, không DDL, không bảng tạm | `api` |
| `shopbot_mcp` | SELECT `products`, `product_embeddings`, `order_items`, `kb_*`, view `orders_for_agent` (không có địa chỉ giao), `refunds` **trừ cột `payout_info_enc`**; INSERT **theo cột** (xem dưới) trên `refunds`, `tool_audit_log`, `support_tickets` (không INSERT `status_events`/`notifications`: do API ghi). Không thấy `users`, `refresh_tokens`, `conversations`, bảng `orders` (kể cả `shipping_address`). Không DDL, không bảng tạm | `mcp-server` |

INSERT của `mcp` là quyền theo cột (nguồn: `MCP_INSERT_COLUMNS` trong `app/db/roles.py`, lặp lại trong revision 0005/0006): `refunds` chỉ `order_id, user_id, source, requested_amount_vnd, reason, idempotency_key, thread_id` nên `status` luôn lấy DEFAULT `pending_staff` (mcp không thể tạo `paid_out`) và không đặt được `approved_amount_vnd`, `decided_by`, `payout_*`; khoá ngoại ghép `(order_id, user_id)` -> `orders(id, user_id)` bảo đảm khoản hoàn thuộc đúng chủ đơn. `status_events` không có `actor_id`, `at`; `tool_audit_log` không có `at`; `support_tickets` không có `status`/`assigned_to`/`resolved_*`; `notifications` không có `read_at`. Còn lại rủi ro: mcp vẫn chọn được `entity_type`/`type` hợp lệ (CHECK không phân biệt role) nên có thể ghi sự kiện/thông báo giả cho `user_id` tuỳ ý; thu hồi INSERT trên `status_events`/`notifications` nếu MCP v2 không cần (hiện chưa có code nào ghi hai bảng này từ MCP). Quyền `refunds` phục vụ tool `issue_refund` hiện tại; thu hồi khi luồng hoàn tiền chuyển hẳn sang API. `TEMPORARY` trên database bị thu khỏi PUBLIC. `status_events`/`tool_audit_log` không dọn được bằng `DELETE` (trigger chặn cả chủ bảng); dọn theo hạn lưu trữ làm có chủ đích bằng `TRUNCATE` hoặc partition do migrator.

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

Roll-forward-only: chỉ thêm revision mới, không sửa revision đã phát hành. Revision 0004 và 0005 biến đổi `orders`/`refunds` của 0001 tại chỗ và **xoá đơn/hoàn tiền hiện có** (`user_id` text cũ không ánh xạ được sang `users`); catalog được giữ. **Có dòng thì revision từ chối chạy** (lỗi nêu số dòng và cách bật) trừ khi chạy `alembic -x allow_destroy_legacy_orders=true`; downgrade 0004/0005 cũng bị chặn như vậy (đơn/hoàn tiền mới bị xoá khi quay lại dạng cũ). Qua bootstrap/compose, cờ đi theo `ALLOW_DESTROY_LEGACY_ORDERS=true` (mặc định `false`, qua `MigrateSettings.allow_destroy_legacy_orders`); chỉ đặt cho một lần chạy trên DB dev đã sao lưu, rồi bỏ. DB trống chạy bình thường không cần cờ. Downgrade của revision đầu không `DROP EXTENSION` (bảng LangGraph phụ thuộc). Trước khi upgrade production: `pg_dump` sao lưu. `scripts/check` chạy `alembic check` để chặn model lệch migration: phải đặt `TEST_DATABASE_URL` (DSN superuser Postgres pgvector tạm) hoặc `ALEMBIC_DATABASE_URL`, nếu không script thất bại; `SKIP_DB_CHECKS=1` cố ý bỏ qua và kết thúc bằng cảnh báo `SKIPPED-DB-CHECKS` thay vì "TẤT CẢ ĐẠT".

## Quy tắc ở lớp DB cần biết

**Hoàn tiền.** Hạn hoàn `REFUND_WINDOW_DAYS` (mặc định 7) tính theo ngày lịch giờ cửa hàng (`Asia/Ho_Chi_Minh`) từ `orders.delivered_at`: giao đủ 7 ngày vẫn hoàn được, ngày thứ 8 thì không. Trần hoàn = tổng `order_items.unit_price_vnd * qty` (không gồm `shipping_fee_vnd`) trừ các khoản hoàn "sống" của đơn. Mỗi đơn tối đa một yêu cầu "sống" của khách (`customer_request`) và tối đa một khoản "sống" do hệ thống tạo (`system_cancel_paid`, đơn đã thanh toán bị huỷ), mỗi loại một chỉ mục duy nhất một phần nên không chặn nhau. Tool MCP `issue_refund` chỉ tạo yêu cầu `pending_staff` cho nhân viên duyệt; tiền chưa được hoàn và agent không có quyền chi trả. `lookup_order.refunded_vnd` chỉ có giá trị khi `paid_out`, `pending_refund_vnd` là số đang chờ. Điều kiện "đơn đã thanh toán" chưa kiểm tra vì chưa có bảng `payments` (bổ sung khi thanh toán có mặt); tới lúc đó đơn đã giao được coi là đã thu tiền. Ràng buộc DB: `delivered` bắt buộc có `delivered_at` (ghi một lần), `total_vnd = subtotal_vnd + shipping_fee_vnd`, `paid_out` cần `payout_reference` và `approved_amount_vnd`, `approved`/`rejected` cần `decided_by` và `decided_at`.

**Chuyển trạng thái do ứng dụng bảo đảm.** DB chỉ kiểm tra giá trị trạng thái hợp lệ (CHECK) và luật "một yêu cầu sống", không kiểm tra đường chuyển (ví dụ `paid_out` là trạng thái cuối, `approved` không về `rejected`). Lớp API/nhân viên phải chặn các chuyển không hợp lệ; chưa có trigger ở DB.

**Bảng chỉ-thêm và dữ liệu cá nhân.** `status_events` và `tool_audit_log` bị trigger chặn UPDATE/DELETE nên không ẩn danh hoá được sau khi ghi. Vì vậy chúng chỉ được chứa dữ liệu đã che hoặc không phải dữ liệu cá nhân (không email, số điện thoại, địa chỉ, nội dung chat, thông tin nhận tiền); việc che áp dụng **lúc ghi**, ở lớp audit của tool (chưa có trong phase này, hiện không có code nào ghi hai bảng này: `status_events.note` và `tool_audit_log.args` chưa nhận dữ liệu nào). Người ghi sau này phải che trước khi INSERT và có test.

**SQLSTATE 23001.** Trigger chỉ-thêm (`forbid_row_change`) và ghi-một-lần (`forbid_delivered_at_rewrite`) ném `restrict_violation` (SQLSTATE `23001`) kể cả với chủ bảng; lớp API/retention phải ánh xạ mã này (không phải `P0001`). Dọn theo hạn lưu trữ dùng `TRUNCATE`/partition do migrator, không dùng DELETE.
