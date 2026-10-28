# Giỏ hàng, đơn hàng, hoàn tiền: MCP tool, REST và API nhân viên

Một lớp nghiệp vụ duy nhất `backend/app/shop/` (giỏ hàng, đơn, thanh toán giả lập, hoàn tiền) được dùng bởi: MCP server (cho agent), REST giỏ hàng (cho UI) và API nhân viên. Số liệu chính sách lấy từ settings (`SHIPPING_FEE_VND=30000`, `FREE_SHIPPING_FROM_VND=500000`, `REFUND_WINDOW_DAYS=7`, `MAX_QTY_PER_LINE=10`) và phải khớp `documents/policies`.

## Danh tính khách

Không đăng nhập. Hai khoá:
- `session_id`: UUID ngẫu nhiên do trình duyệt sinh (localStorage). Là khoá giỏ hàng và danh sách đơn đã đặt trong phiên. Chat và REST giỏ hàng dùng chung khoá này nên món agent thêm vào giỏ hiện ngay trên UI.
- Mã đơn + SĐT đặt hàng: chứng minh quyền xem/huỷ/thanh toán/hoàn tiền một đơn. Sai mã hay sai SĐT đều trả cùng một thông báo.

Agent không để model tự điền `session_id`: tham số này bị ẩn khỏi schema tool và luôn lấy từ cấu hình lượt chat do server đặt (`app/agent/shop_tools.py`).

## MCP server (`python -m app.mcp_server`, service `mcp-server`)

Streamable HTTP, stateless, chỉ trong mạng nội bộ compose (không publish cổng), yêu cầu `Authorization: Bearer $MCP_API_KEY` (thiếu khoá thì không khởi động). Tool trả `{"ok": true, ...}` hoặc `{"ok": false, "error": "..."}`.

| Tool | Việc |
|---|---|
| `search_products`, `get_product` | giá và tồn kho thật từ bảng `products` (lọc theo từ khoá, danh mục, khoảng giá, còn hàng) |
| `view_cart`, `add_to_cart`, `set_cart_quantity` | giỏ hàng theo phiên, kiểm tra tồn kho, tối đa 10/dòng |
| `checkout` | chốt đơn từ giỏ (COD hoặc online), trừ tồn kho trong một transaction |
| `pay_order` | thanh toán đơn online (cổng giả lập `SIM-...`), số tiền lấy từ DB |
| `lookup_order`, `list_my_orders` | trạng thái đơn, thanh toán, yêu cầu hoàn tiền |
| `cancel_order` | huỷ đơn đang xử lý và chưa thanh toán, hoàn lại tồn kho |
| `check_refund_eligibility`, `request_refund` | kiểm tra điều kiện / tạo yêu cầu hoàn tiền **chờ nhân viên duyệt** |

Quy tắc phía server (không dựa vào prompt): giá, phí ship và số tiền hoàn do server tính; tồn kho khoá hàng (`FOR UPDATE`) nên hai đơn cùng mua món cuối cùng chỉ một đơn thành công; mỗi đơn chỉ một yêu cầu hoàn tiền đang hiệu lực (ràng buộc unique một phần trong DB).

Prompt yêu cầu khách xác nhận rõ ràng trước `checkout`, `pay_order`, `cancel_order`, `request_refund`; đây là ràng buộc ở mức prompt, không phải ở server.

## Hoàn tiền (human-in-the-loop)

Điều kiện: đơn đã giao, trong 7 ngày kể từ `delivered_at`, lý do thuộc `not_as_described | defective | wrong_or_missing_item | damaged_in_shipping` (đổi ý không được hoàn), chưa có yêu cầu đang xử lý. Hoàn cả đơn (kèm phí ship) hoặc chọn một số sản phẩm (không hoàn ship). Agent chỉ tạo yêu cầu `pending`; tiền không đổi cho tới khi nhân viên duyệt. Không thu số tài khoản ngân hàng trong chat: nhân viên gọi vào SĐT đặt hàng để xác nhận cách nhận tiền.

## REST (qua nginx `/api/...`)

| Endpoint | Mô tả |
|---|---|
| `GET /cart`, `POST /cart/items`, `PUT/DELETE /cart/items/{slug}` | giỏ hàng; header `X-Session-Id`; lỗi nghiệp vụ trả 400 kèm `detail` tiếng Việt |
| `GET /staff/refunds` | yêu cầu hoàn tiền chờ duyệt |
| `POST /staff/refunds/{id}/decision` | `{"approve": bool, "note": "..."}` |
| `POST /staff/orders/{code}/status` | `{"status": "shipped" \| "delivered"}`; giao xong thì đơn COD ghi nhận đã thu tiền |

API nhân viên cần header `X-Staff-Key: $STAFF_API_KEY` (để trống = tắt, trả 503). UI nhân viên ở `/nhan-vien` trên frontend.

## Dữ liệu và vận hành

Migration `0004`: `carts`, `orders`, `order_items`, `refund_requests` và 3 đơn mẫu của SĐT `0900000001` (`SM000100` đã giao 2 ngày trước, `SM000101` đang giao, `SM000102` COD đang xử lý). Đơn mới có mã `SM001000` trở đi.

Chạy local: đặt `MCP_API_KEY`, `STAFF_API_KEY` trong `.env` rồi `docker compose up -d --build`. Test DB: `TEST_DATABASE_URL="host=... port=... user=... password=... dbname=postgres"` (Postgres có pgvector và quyền tạo database); không đặt thì các test cần DB bị bỏ qua.

## Chống dò tìm và lạm dụng

- Tra cứu đơn (tra, huỷ, thanh toán, kiểm tra/gửi hoàn tiền) sai mã đơn hoặc SĐT: ghi vào `lookup_failures`. Quá `LOOKUP_MAX_FAILURES_PER_CODE` (5) lần theo một mã đơn hoặc `LOOKUP_MAX_FAILURES_PER_PHONE` (10) lần theo một SĐT trong `LOOKUP_WINDOW_MINUTES` (15) phút thì khoá tạm, kể cả khi nhập đúng. Đổi lại người thật nhập sai nhiều lần cũng bị khoá vài phút; thông báo hướng dẫn liên hệ nhân viên. Lần tra đúng không bị tính.
- Mỗi phiên tối đa `MAX_ORDERS_PER_SESSION_PER_HOUR` (5) đơn mỗi giờ, tránh spam đơn giữ chỗ tồn kho.
- Chat có giới hạn tần suất và lọc tin rác riêng (xem `chat-agent.md`).

## Giới hạn hiện tại

- Thanh toán là giả lập (luôn thành công); thay bằng cổng thật bằng cách cài đặt `PaymentGateway` trong `app/shop/payments.py`.
- Giới hạn tần suất chat nằm trong bộ nhớ một tiến trình, không chia sẻ giữa nhiều replica.
- Hành vi gọi tool phụ thuộc model: có lúc model bỏ qua việc gọi lại `lookup_order` và trả lời theo kết quả cũ (đã siết prompt nhưng chưa loại trừ hoàn toàn).
- Tên các tool có thể bị model tiết lộ khi bị hỏi; an toàn dựa trên kiểm tra phía server, không dựa vào việc giấu prompt.
