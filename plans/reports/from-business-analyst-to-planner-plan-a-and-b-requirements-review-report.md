# BA review: chất lượng requirements Plan A + Plan B (ShopMobile)

Vai: Senior BA. Advisory, không sửa plan/code. Ngày 2026-10-23.
Phạm vi: business rules, process, role, data, acceptance. Không bàn lịch/delivery (PM khác) và capability matrix chatbot (PM khác).

Viết tắt: **A**=`plans/261023-1010-backend-alembic-and-langgraph-agent`, **B**=`plans/261023-1100-checkout-staff-console-frontend`, **RT**=`plans/reports/from-red-team-to-planner-plan-b-findings-summary-report.md` (chưa duyệt), **AS-IS**=code hiện tại. `A-p5` = phase 5 của A.
Trạng thái rule: **D**=defined, **AM**=ambiguous, **MS**=missing, **CF**=conflicting.

## Kết luận nhanh

1. Plan mạnh về kỹ thuật/an toàn (idempotency, FOR UPDATE, RBAC từ DB), **yếu về business rules**: chính sách hoàn tiền (thời hạn, công thức số tiền, ship, COD chưa thu) chưa có số liệu; A chỉ nói "server tính" nhưng không ai định nghĩa công thức.
2. 3 máy trạng thái (order/payment/refund) nằm ở 3 file khác nhau, chưa ai gộp; có >=8 transition thiếu/sai (mục 3.5). Lớn nhất: đơn đã trả tiền rồi huỷ (không có đường hoàn), COD giao thất bại (kẹt ở `shipped`), COD chưa thu vẫn hoàn được.
3. **Ticket (handoff) không có màn hình xử lý** cho nhân viên và khách không xem được trạng thái: agent tạo ticket xong là "vào hố đen" (mục 5).
4. Refund chỉ tạo được qua chat agent (không có REST/UI cho khách) và không thu thông tin nhận tiền hoàn: payout thủ công không biết chuyển đi đâu.
5. Role `admin` tồn tại trong CHECK nhưng **không có quyền riêng**; không ai quản lý được sản phẩm/tồn/KB/nhân viên ngoài CLI/seed.
6. Privacy: có xem/xoá memory và TTL 180d, nhưng chưa có thông báo/đồng ý, chưa có retention cho audit/checkpoint ("N ngày"), chưa có quy trình xoá tài khoản.
7. Traceability: 10 story chính -> 5 có phủ đủ, 5 phủ một phần/không phủ (mục 6.2).

---

## 1. Stakeholders & RBAC

### 1.1 Actor

| Actor | Định nghĩa trong plan | Ghi chú BA |
|-------|----------------------|-----------|
| Guest | Chỉ catalog + `/health` công khai (A-p4); giỏ ở localStorage (B-p1); chat cần đăng nhập (B-p1) | Guest **không tư vấn qua chat** (AS-IS cho phép). Checkout guest không nêu, ngầm định cấm |
| Customer | `role=customer`, tự đăng ký (A-p4) | Không có email xác minh, không quên mật khẩu (A "Không làm") |
| Staff | tạo bằng CLI `create_staff` (A-p4) | Làm tất cả: xác nhận CK, giao hàng, thu COD, duyệt/chi hoàn tiền (B-p5, A-p7) |
| Admin | có trong CHECK role, `staff|admin` cùng quyền | **Không có quyền/ màn hình riêng**; RT hỏi "có cần tách?" |
| Agent (ShopBot) | 7 tool, token ký theo lời gọi, role DB `mcp` | Chỉ đọc + `request_refund` + `create_support_ticket`; không huỷ đơn, không đổi địa chỉ |
| System/worker | job hết hạn đơn, dọn checkpoint/token (A-p9, B-p6) | Actor trong event log cần định danh (`system`) |
| Shipper | **không có** | Staff tự nhập hãng + mã vận đơn và tự bấm "đã giao" (B-p5); không bằng chứng giao hàng |
| Operator/DevOps | CLI, Phoenix, migrate | Tạo staff/admin, reindex KB, seed: **không phải người dùng app** nhưng là kênh duy nhất cho nhiều việc |

### 1.2 Ma trận quyền (Y=được, own=chỉ của mình, —=không, ?=plan không nói rõ)

| Hành động | Guest | Customer | Staff | Admin | Agent | Nguồn / lưu ý |
|-----------|:----:|:--------:|:-----:|:-----:|:-----:|---------------|
| Xem catalog | Y | Y | Y | Y | Y | A-p4 |
| Đăng ký / đăng nhập | Y | - | - | - | - | A-p4; chỉ tạo `customer` |
| Chat tư vấn / FAQ | — | Y | ? | ? | - | B-p1; staff có chat không? không nêu |
| Tạo đơn / thanh toán | — | own | ? | ? | — | Staff mua hàng được không? RT7 muốn cấm tự thao tác đơn của mình |
| Xem đơn | — | own | tất cả (tìm mã/email/SĐT) | tất cả | own (token) | B-p5, A-p5 |
| Huỷ đơn chưa `shipped` | — | own | Y (đi tiến + huỷ) | Y | **—** | B-p6; khách nhờ chat huỷ = không tool -> ticket |
| Huỷ đơn đã `paid` | — | own? | ? | ? | — | **MS** -> RT3 |
| "Tôi đã chuyển khoản" | — | own | — | — | — | B-p4 |
| Xác nhận/từ chối chuyển khoản | — | — | Y | Y | — | B-p4/5; chặn đơn của chính mình chỉ ở RT7 |
| Đánh dấu COD đã thu | — | — | Y | Y | — | B-p4/5 |
| Đổi trạng thái giao hàng | — | — | Y | Y | — | B-p5; không có shipper |
| Tạo yêu cầu hoàn tiền | — | own, **chỉ qua chat agent** | — | — | Y (sau khách xác nhận) | A-p6/7; không REST/UI -> LLM sập = không hoàn tiền được |
| Huỷ yêu cầu hoàn tiền (`pending_staff`) | — | own | — | — | — | A-p7 |
| Duyệt/từ chối hoàn tiền | — | — | Y, trừ yêu cầu của chính mình | Y | — | A-p7; admin có ngoại lệ? không nêu |
| Chi trả hoàn tiền (`payout_reference`) | — | — | Y | Y | — | A-p7; không bắt khác người duyệt |
| Xem hàng đợi hoàn tiền | — | — | Y | Y | — | |
| Xem hội thoại | — | own (list/xoá) | **chỉ trích đoạn gắn yêu cầu** | ? | — | B-p5; endpoint trích đoạn **không có** trong A-p7 (xem 4.4) |
| Xem/xoá memory | — | own | — | — | — | A-p7 |
| Tạo/xử lý ticket | — | ? | **MS (không màn hình/API)** | MS | tạo | A-p5, B-p5 |
| Quản lý sản phẩm/tồn/giá | — | — | **MS** | **MS** | — | catalog chỉ seed; KB chỉ `reindex` CLI |
| Quản lý KB/chính sách | — | — | MS | MS | đọc | nội dung song ngữ vi/en ai viết/duyệt? |
| Tạo staff/admin, đổi role | — | — | — | **MS trong app** | — | chỉ CLI (A-p4 "không admin API") |
| Vô hiệu hoá nhân viên | — | — | — | MS | — | success criteria A-p4 yêu cầu hành vi này nhưng **không có cơ chế** |
| Xem audit/event log | — | — | timeline từng yêu cầu | ? | ghi | A-p3, B-p5 |

### 1.3 Mâu thuẫn / thiếu giữa 2 plan

- **Self-dealing:** A-p7 chỉ cấm "duyệt yêu cầu của chính mình"; RT7 mở rộng mọi thao tác tiền/trạng thái, B chưa có. Quyết định chung cần 1 câu.
- **Admin vs staff:** A-p7 `staff|admin` cùng quyền; RT hỏi tách; không ai định nghĩa admin làm gì khác. Hiện admin = nhãn thừa.
- **Maker-checker:** duyệt và chi trả có thể cùng 1 người, không ngưỡng (D2 "không ngưỡng tự động" là quyết định của user: không đảo, chỉ hỏi thêm về người thứ hai).
- **Ai thấy đơn đã huỷ nhưng đã thanh toán?** (RT open Q) chưa có queue đối soát.
- **Quyền MCP:** A-p3 cấp `mcp` SELECT `orders`; nếu địa chỉ nằm trong `orders.shipping_address` (A) thì agent đọc được địa chỉ, trái RT9 ("mcp không đọc addresses").
- Staff xem "trích đoạn hội thoại" (B-p5) nhưng role `mcp` không đọc `conversations` và A-p7 không có endpoint trích đoạn; dữ liệu nằm trong checkpoint LangGraph -> chưa rõ nguồn.

---

## 2. Business rules catalog

| ID | Rule | Nguồn | TT | Vấn đề / đề xuất |
|----|------|-------|:--:|------------------|
| **Hoàn tiền** |
| BR-01 | Chỉ hoàn cho đơn `delivered` | AS-IS `mcp_server/server.py:19,72`; A-p5 `lookup_order` "điều kiện do server tính" | D | Đơn đã trả tiền rồi huỷ thì sao? (BR-08) |
| BR-02 | **Thời hạn hoàn tiền** tính từ `delivered_at` | B-p6 (chỉ nêu "mốc") | **MS** | Không có số ngày ở bất kỳ file nào. Đề xuất mặc định 7 ngày (chủ shop xác nhận) |
| BR-03 | Số tiền tối đa = `max_refundable` server tính | A-p5, A-p6 payload `max_refundable` | **AM** | AS-IS = `total_vnd`. Có gồm phí ship? trừ phần đã hoàn? trừ COD chưa thu? Đề xuất: = tổng tiền hàng đã **thực thu**, trừ phí ship (trừ khi lỗi shop), trừ tổng đã hoàn |
| BR-04 | Hoàn một phần: `requested_amount_vnd` <= trần; staff có `approved_amount_vnd` riêng | A-p3 rev0005 | **AM** | Staff được duyệt khác số khách xin (cao hơn? thấp hơn?) chưa nói; khách thấy số nào |
| BR-05 | Giới hạn mỗi đơn | AS-IS: PK `order_id` = 1 lần (`schema.py` refunds). A: unique một phần `(order_id) WHERE status IN (pending_staff, approved)` | **CF** | Index không gồm `paid_out` -> sau khi chi trả, tạo được yêu cầu mới (hoàn kép) nếu `max_refundable` không trừ phần đã hoàn. RT3 đề xuất `sum(refunds)<=payment.amount` nhưng chưa duyệt. Chốt: 1 lần/đơn hay nhiều lần cộng dồn <= số thực thu |
| BR-06 | Bị từ chối/huỷ thì gửi lại được | A-p3, A-p5 | D (AM giới hạn) | Không giới hạn số lần, không cooldown, không bắt thêm thông tin -> spam queue |
| BR-07 | Đơn COD chưa thu tiền / đơn chưa `paid` | RT3 | **CF** | A-p5 eligibility chỉ dựa order; B-p4 COD `pending` tới khi nhân viên thu. Có thể hoàn tiền chưa từng nhận |
| BR-08 | Đơn đã `paid` rồi bị huỷ -> hoàn | RT3 | **MS** | AS-IS policy: đơn huỷ "không đủ điều kiện hoàn" (`server.py:20`) -> khách trả tiền mà không được hoàn. Phải có đường hệ thống tự tạo refund |
| BR-09 | Khách xác nhận trong chat trước khi tạo yêu cầu | A-p6 `confirm` | D | |
| BR-10 | Mọi hoàn tiền cần nhân viên duyệt, không tự duyệt | A plan D2, A-p7 | D | |
| BR-11 | Từ chối phải có ghi chú, khách được thông báo | B-p5 (ghi chú bắt buộc), A-p7 | D / MS nội dung | Mẫu nội dung thông báo chưa có (5.3) |
| BR-12 | Chi trả thủ công, ghi `payout_reference`, số tiền = `approved_amount` | A-p7, B plan | D | **Không có nơi nhận tiền**: khách không cung cấp STK/ví; hoàn COD về đâu? **MS** |
| BR-13 | Trả hàng/kiểm hàng trước hoàn tiền | - | **MS** | KB có tài liệu "đổi trả" (A-p3) nhưng không có bước nhận hàng trả, không restock |
| BR-14 | SLA duyệt/chi trả hoàn tiền | - | **MS** | Khách chờ bao lâu? Không có quá hạn, không nhắc |
| **Giá / ship / tồn** |
| BR-15 | Ship 30.000đ, miễn phí từ 500.000đ | AS-IS `cart-page.tsx:8-9`; B-p3 "ngưỡng cấu hình" | **AM** | Phí 30k không nêu trong B; RT5 báo hard-code client. Ngưỡng trên tạm tính hay sau giảm giá (không có giảm giá). Phí ship có hoàn khi huỷ/hoàn tiền không? |
| BR-16 | Giá/tổng do server tính, chụp giá vào `order_items` | B-p3, A-p3 | D | |
| BR-17 | Giới hạn qty/đơn, số đơn chưa thanh toán/user, trần tồn giữ | RT8 | **MS** (chờ duyệt) | |
| BR-18 | Giá đã gồm VAT? Xuất hoá đơn? | - | **MS** | mục 7 |
| BR-19 | Trừ tồn lúc tạo đơn; trả tồn khi huỷ/hết hạn | B-p3, B-p6 | D | Backorder, tồn âm = bị chặn (CHECK stock>=0) OK |
| BR-20 | Giữ tồn 24h cho chuyển khoản, hết hạn tự huỷ | B-p4, B-p6 | D | COD không hết hạn (MS, RT). "Tôi đã chuyển" có gia hạn không (**AM**, RT open). Nhân viên nghỉ cuối tuần > 24h -> đơn đã chuyển tiền bị huỷ (RT2) |
| **Thanh toán** |
| BR-21 | CK thủ công: khách báo "đã chuyển" -> staff đối chiếu -> `paid` -> đơn `processing` | B-p4 | D | Số tiền khác (thiếu/thừa), trùng mã giao dịch, chuyển sai nội dung: **MS** (RT5, RT7) |
| BR-22 | Từ chối chuyển khoản -> `failed` | B-p4 (status có `failed`) | **AM** | Khách thử lại được không? Đơn còn sống tới hết 24h? Thông báo gì? |
| BR-23 | COD: payment `pending` tới `delivered`, staff đánh dấu `paid` | B-p4 | D | Trạng thái đơn khi tạo COD: **AM** (RT open Q); phí COD/giới hạn giá trị COD **MS** |
| BR-24 | CK: không giao khi chưa `paid` | B-p4 risk text | **AM** | Không nằm trong bảng chuyển trạng thái (RT4) |
| **Huỷ / giao** |
| BR-25 | Khách huỷ khi chưa `shipped`; staff đi tiến + huỷ; không đi lùi | B-p6 | D | Bắt lý do huỷ? Staff huỷ sau `shipped` (khách từ chối nhận)? |
| BR-26 | Giao thất bại / khách không nhận / trả hàng | - | **MS** | Không có state; huỷ từ `shipped` không được phép -> kẹt |
| BR-27 | `delivered` chỉ từ `shipped` | RT4 | AM (chờ duyệt) | Nhảy cóc mở thời hạn hoàn tiền |
| **Thông báo** |
| BR-28 | Thông báo in-app, poll 30s | A-p7, B-p2 | D | Không email/SMS (B "Không làm"). Khách ngoài site không biết kết quả hoàn tiền |
| BR-29 | Phạm vi sự kiện có thông báo | B-p6 "mỗi bước"; RT15 "chỉ hoàn tiền/xác nhận TT"; A-p5 "thông báo cho nhân viên" | **CF** | Chốt danh sách sự kiện + người nhận (staff nhận thế nào? `notifications.user_id` của ai?) |
| **Dữ liệu / riêng tư** |
| BR-30 | Memory chỉ 4 field liệt kê trước (`preferred_category/brand`, `language`, `issue_type`), tối đa 3 mục/lượt, không PII | A-p6 | D | |
| BR-31 | Memory TTL 180 ngày, `refresh_on_read=False`, sweep | A-p6 | D | Rationale 180d chưa nêu; khớp "xem/sửa/xoá" slide |
| BR-32 | Khách xem/xoá memory và hội thoại; xoá = soft delete + xoá checkpoint + memory liên quan | A-p7 | D | |
| BR-33 | Thông báo/đồng ý khi lưu memory & lịch sử chat | - | **MS** | Không có consent, không có banner/điều khoản |
| BR-34 | Dọn checkpoint hội thoại đóng quá **N ngày**, hội thoại soft-delete, refresh token hết hạn | A-p9 | **AM** | N không có giá trị; thời gian purge hội thoại đã soft-delete không có |
| BR-35 | Retention audit (`refund_events`, `tool_audit_log`, payment/order events) | A-p3 (append-only) | **MS** | Append-only xung đột quyền xoá/ẩn danh dữ liệu cá nhân khi khách yêu cầu |
| BR-36 | Xoá tài khoản / xuất dữ liệu | - | **MS** | |
| **Ngôn ngữ** |
| BR-37 | Agent trả lời theo ngôn ngữ khách (vi/en); KB+prompt+eval song ngữ; UI tiếng Việt | A D6, A-p6/8 | D | Thông báo (JSONB payload), nhãn trạng thái, ticket summary, console nhân viên: ngôn ngữ nào? Khách chat EN thấy toast VN |
| BR-38 | Ngôn ngữ KB chọn theo `lang` câu hỏi | A-p5 | D | Nội dung KB EN/VN phải **cùng nghĩa**: ai kiểm duyệt bản dịch? |
| **Handoff / hỗ trợ** |
| BR-39 | Handoff khi khách yêu cầu hoặc lặp lại thất bại; tạo ticket, trả mã | A-p6 | D | Priority do ai/cái gì đặt (`create_support_ticket(summary, priority)`)? Xử lý ticket: **MS** |
| **Truy cập** |
| BR-40 | Chỉ khách tự đăng ký; staff/admin bằng CLI; mật khẩu >=10 ký tự; không reset | A-p4 | D / MS reset | Khách quên mật khẩu = mất tài khoản vĩnh viễn |
| BR-41 | Chat bắt buộc đăng nhập | B-p1 | D | Mất khách tư vấn trước mua (quyết định user #7) |
| BR-42 | Rate limit chat 20/phút/người; đăng nhập sai làm chậm | A-p4/7 | D | |
| **Chung** |
| BR-43 | Múi giờ (24h hết hạn, ngày hoàn tiền, báo cáo) | - | **MS** | Chốt Asia/Ho_Chi_Minh |
| BR-44 | Mã đơn hiển thị | B-p3 (tiền tố+ngày+chuỗi ngắn); AS-IS `A100` | **AM** | A-p3 seed dùng UUID cho user, id đơn không nói; agent nhận `order_id` khách gõ ("A101") -> phải map mã hiển thị, chuẩn hoá hoa/thường |
| BR-45 | Nguồn chính sách duy nhất | A-p3 KB docs (hoàn tiền, bảo hành, vận chuyển, trả góp, đổi trả) vs hằng `REFUND_POLICY`/server eligibility | **CF** | 2 nguồn: văn bản KB (agent trích dẫn) và code (server tính). Phải sinh từ cùng tham số, hoặc KB ghi đúng số liệu config |

---

## 3. Quy trình end-to-end

### 3.1 Đặt hàng -> thanh toán -> giao (hiện trong plan, chú thích chỗ thiếu)

**COD**
1. Customer: giỏ -> `/thanh-toan` -> quote (B-p3) -> `POST /v1/orders` (Idempotency-Key). Server: khoá product theo id, trừ tồn, chụp giá, tạo order + payment(`cod`,`pending`).
2. Order bắt đầu: `pending_payment` hay `processing`? **AM** (đề xuất `processing`, `expires_at` NULL).
3. Staff: đóng gói -> nhập hãng + mã vận đơn -> `shipped` (không có kiểm tra gọi xác nhận đơn COD, không giới hạn COD).
4. Staff: `delivered` -> ghi `delivered_at` (mở thời hạn hoàn tiền).
5. Staff: đánh dấu COD `paid` (đã thu). *Giao thất bại: MS.* *Ai nhận tiền COD từ shipper: MS (không có shipper).*

**Chuyển khoản**
1. Customer tạo đơn: order `pending_payment`, payment(`bank_transfer`,`pending`), `expires_at=+24h`.
2. Màn hướng dẫn: STK từ env + nội dung = `reference_code`.
3. Customer bấm "Tôi đã chuyển" (+mã GD tuỳ chọn) -> payment `awaiting_confirmation`. (gia hạn `expires_at`? **AM**)
4. Staff đối chiếu sao kê -> Xác nhận: payment `paid`, order `processing`; hoặc Từ chối: payment `failed` (**hậu quả MS**).
5. Hết 24h còn `pending` -> worker huỷ order, trả tồn (race với bước 4: RT2).
6. `processing -> shipped -> delivered` như COD.

### 3.2 Huỷ đơn

- **Trước thanh toán** (`pending_payment`): khách/staff huỷ -> order `cancelled`, payment `cancelled`, trả tồn, thông báo. Defined (B-p6).
- **Sau thanh toán, chưa giao** (`processing`, payment `paid`): B-p6 cho huỷ -> `cancelled` + trả tồn nhưng **payment vẫn `paid`, không refund** (RT3). Đề xuất: huỷ -> hệ thống tạo refund `pending_staff` (nguồn=`system`, số tiền = số thực thu) vào queue; staff chi trả như thường; không cần khách xác nhận trong chat.
- **Sau `shipped`**: khách không huỷ (B-p6); staff cũng không (B-p6 chỉ huỷ từ `pending_payment|processing`). Khách từ chối nhận/giao thất bại -> **kẹt**.
- Qua chat: không có tool huỷ -> agent tạo ticket (xem 3.4).

### 3.3 Hoàn tiền (agent-assisted)

1. Khách (đã login) nhắn "hoàn tiền đơn A101" -> router intent=refund (dính qua các lượt).
2. Agent `lookup_order` -> server trả điều kiện + `max_refundable`. Không đủ điều kiện: giải thích lý do, **không** tạo.
3. Agent hỏi lý do (+ số tiền). Khách xác nhận bằng thẻ `confirm_required` (interrupt). Có thể huỷ `cancel-pending`.
4. `request_refund` (server kiểm lại, FOR UPDATE, idempotency `thread_id:tool_call_id`) -> refund `pending_staff`, ghi event, thông báo staff.
5. Agent: "đã gửi, nhân viên sẽ duyệt" (guard_output chặn câu "đã hoàn tiền").
6. Staff mở queue -> chi tiết (đơn, lý do, kết quả kiểm điều kiện, trích đoạn chat) -> Duyệt (`approved_amount`) hoặc Từ chối (ghi chú bắt buộc). Không duyệt yêu cầu của chính mình; người đến sau nhận 409.
7. Duyệt -> thông báo khách "đã duyệt" -> staff chuyển tiền ngoài hệ thống -> nhập `payout_reference` -> `paid_out` -> payment `refunded` (B-p4) -> thông báo "đã hoàn".
8. Từ chối -> thông báo + lý do -> khách có thể gửi lại (BR-06) hoặc hỏi `get_refund_status`.
9. Khách huỷ yêu cầu khi còn `pending_staff` (`POST /v1/refunds/{id}/cancel`).

Thiếu: nhận thông tin tài khoản nhận tiền; kiểm hàng trả; SLA; nhắc staff khi quá hạn; khách xem danh sách yêu cầu hoàn tiền (chỉ qua chat/notification); fallback khi LLM down.

### 3.4 Handoff / ticket

1. Khách yêu cầu gặp người, hoặc router thất bại lặp lại -> node `handoff` gọi `create_support_ticket` -> trả mã ticket; `conversations.status=handoff`.
2. **Hết.** Không có: màn hình staff xem ticket, nhận/gán, trạng thái xử lý, trả lời, đóng, thông báo khách, SLA, kênh liên hệ (SĐT/email khách đã có ở `users` nhưng không ai dùng). Khách tiếp tục chat -> `conversations.status` handoff nhưng hành vi bot sau handoff không nêu.
3. Đề xuất tối thiểu: màn "Ticket" staff (list lọc status/priority, xem summary + liên kết đơn/hội thoại, ghi chú, đổi `open|in_progress|resolved`), thông báo khách khi `resolved`; bot sau handoff chỉ trả "đã chuyển nhân viên, mã X" và không xử lý hành động tiền.

### 3.5 Bảng trạng thái hợp nhất Order x Payment x Refund

Trạng thái: Order = `pending_payment, processing, shipped, delivered, cancelled`; Payment = `pending, awaiting_confirmation, paid, failed, cancelled, refunded`; Refund = `pending_staff, approved, rejected, paid_out, cancelled`.
Cột TT: OK = định nghĩa đủ; AM = mơ hồ; MS = thiếu; ILL = cho phép sai (hoặc không chặn).

| # | Thực thể | Từ | Đến | Actor | Điều kiện / tác dụng phụ | TT |
|---|----------|----|-----|-------|--------------------------|:--:|
| T1 | Order+Pay | (tạo) CK | O:`pending_payment`, P:`pending` | Customer | trừ tồn, `expires_at`=+24h | OK |
| T2 | Order+Pay | (tạo) COD | O:`processing` hoặc `pending_payment`, P:`pending` | Customer | `expires_at` NULL | **AM** |
| T3 | Pay | `pending` | `awaiting_confirmation` | Customer | "tôi đã chuyển"; gia hạn expiry? | AM |
| T4 | Pay | `awaiting_confirmation` | `paid` | Staff | `received_amount` = đơn? ghi mã GD; O: `pending_payment->processing` | OK (thiếu received_amount) |
| T5 | Pay | `awaiting_confirmation` | `failed` | Staff | ghi chú; O giữ `pending_payment`; khách thử lại? | **AM** |
| T6 | Pay | `failed` | ? (`awaiting_confirmation`/`cancelled`) | ? | | **MS** |
| T7 | Order+Pay | `pending_payment`/P:`pending` | `cancelled`/`cancelled` | Customer, Staff, System(expiry) | trả tồn 1 lần | OK |
| T8 | Order+Pay | `pending_payment`/P:`awaiting_confirmation` | `cancelled` | System (expiry) | **nên chặn** (đã báo chuyển); RT2 | **ILL** |
| T9 | Pay | `paid` (CK) trên đơn `cancelled` | ? | Staff | xác nhận trễ sau khi hết hạn: 409 + đối soát | **MS** |
| T10 | Order | `processing` | `shipped` | Staff | CK phải `paid`; carrier+tracking | AM (RT4) |
| T11 | Order | `processing` | `delivered` | Staff | không được nhảy cóc | **ILL** (chưa chặn) |
| T12 | Order | `shipped` | `delivered` | Staff | ghi `delivered_at`; COD: P vẫn `pending` | OK |
| T13 | Pay | `pending` (COD) | `paid` | Staff | chỉ sau `delivered`; nên chặn tự thu | OK/AM |
| T14 | Order | `shipped` | ? giao thất bại/khách từ chối | Staff | trả tồn? COD tiền? | **MS** |
| T15 | Order+Pay | `processing`+`paid` | `cancelled`+`paid` | Customer/Staff | **không có refund** | **ILL/MS** (BR-08) |
| T16 | Order | `delivered` | (terminal) | - | không có `completed`/`returned`/`refunded` | MS |
| T17 | Refund | (tạo qua chat) | `pending_staff` | Agent (sau khách xác nhận) | kiểm: `delivered`, trong hạn, **P=`paid`** (thiếu), amount<=trần, không có refund sống | AM |
| T18 | Refund | (tạo hệ thống khi huỷ đơn đã trả) | `pending_staff` | System | | **MS** |
| T19 | Refund | `pending_staff` | `approved` | Staff != owner | `approved_amount`; thông báo | OK |
| T20 | Refund | `pending_staff` | `rejected` | Staff != owner | ghi chú bắt buộc; thông báo | OK |
| T21 | Refund | `pending_staff` | `cancelled` | Customer | | OK |
| T22 | Refund | `approved` | `paid_out` | Staff | `payout_reference`, amount=approved | OK (có thể cùng người duyệt) |
| T23 | Pay | `paid` | `refunded` | System (khi T22) | hoàn một phần thì sao? thiếu `partially_refunded` | **AM** |
| T24 | Refund | `approved` | ? (chi trả lỗi / khách từ chối / hết hạn) | - | không có `failed`/`cancelled` sau approved | **MS** |
| T25 | Refund | `rejected`/`cancelled` | (yêu cầu mới) | Customer | partial unique cho phép | OK (AM giới hạn) |
| T26 | Refund | `paid_out` | (yêu cầu mới) | Customer | partial unique **không chặn** | **ILL** (BR-05) |
| T27 | Order | bất kỳ | refund song song khi đơn chưa `delivered` | - | chặn bởi eligibility; nếu đơn bị đổi sau khi tạo refund? | AM |
| T28 | Order | `delivered` | huỷ/ hoàn hàng & restock | - | tồn không được cộng lại sau hoàn | **MS** |
| T29 | Pay | `cancelled` -> `paid` | | | không được; cần 409 | cùng T9 |

**Bất biến cần ghi vào spec:**
(a) `shipped` yêu cầu: CK => P=`paid`; COD => bất kỳ. (b) `delivered` chỉ từ `shipped`. (c) Refund chỉ khi tiền đã thực thu (P=`paid`); với COD là sau T13. (d) Tổng refund `paid_out`+`approved`+`pending_staff` <= số thực thu. (e) Order `cancelled` + P=`paid` luôn kèm refund hệ thống. (f) Expiry chỉ động vào P=`pending`.

---

## 4. Dữ liệu & thuật ngữ

### 4.1 Thực thể và sở hữu

| Thực thể | Plan định nghĩa | Plan mở rộng | Vấn đề |
|----------|-----------------|--------------|--------|
| users, refresh_tokens | A-p3 rev0002 | - | OK; `phone` trong users và trong addresses (B) trùng |
| products, product_embeddings | A-p3 rev0003 | - | Không có vòng đời quản trị (MS) |
| **orders** | A-p3 rev0004: `id,user_id,status,total_vnd,shipping_address jsonb,carrier,tracking_code,delivered_at,created_at` | B-p3 thêm `subtotal_vnd, shipping_fee_vnd, payment_status, note, expires_at`, số đơn dễ đọc; RT thêm `idempotency_key`, `request_hash`, `stock_released_at`, `received_amount` | **Trùng sở hữu 2 plan**; `shipping_address jsonb`(A) vs bảng `addresses`(B); `orders.payment_status` trùng `payments.status` (RT9); AS-IS có `items jsonb` (`schema.py`) cần di chuyển; mã đơn chưa chốt |
| order_items | A-p3 | - | snapshot tên/giá OK |
| payments, payment_events | B-p4 | - | Thiếu `received_amount`; `refunded` không phản ánh hoàn 1 phần |
| refunds, refund_events | A-p3 rev0005 | B cần ràng buộc với payments | Không có `source` (customer/system), không có nơi nhận tiền, không có `reason_code` |
| order_events | B-p6 | - | 3 bảng event riêng (payment/order/refund) -> RT15 gộp `status_events` |
| conversations | A-p3 rev0006 | - | `thread_id` UUID server sinh; soft delete vs bằng chứng cho refund |
| support_tickets | A-p3 rev0006 | - | Chỉ `user_id,thread_id,summary,priority,status`; không assignee/notes/timestamps xử lý; **không API đọc** |
| notifications | A-p3 rev0006 | B-p6 ghi theo mỗi bước | `type` + `payload jsonb`, danh sách type chưa có; người nhận staff? |
| kb_documents, kb_chunks | A-p3 rev0007 | - | Chủ nội dung chưa rõ; chỉ cập nhật qua CLI |
| memory (LangGraph store) | A-p6 | - | không thuộc schema nghiệp vụ; xoá theo `(user_id,"memory")` |
| checkpoints | LangGraph | - | chứa toàn bộ hội thoại (PII tự do); chính sách xoá N ngày chưa rõ |
| addresses | B-p3 | RT10 đề xuất bỏ | PII; mcp không được đọc |
| tool_audit_log | A-p3 | - | args "redacted" -> chưa định nghĩa trường nào |

Thuật ngữ cần chốt (glossary): "đã duyệt" (`approved`) != "đã hoàn tiền" (`paid_out`): guard_output (A-p6) chặn câu "đã hoàn/đã duyệt/đã chi" khi tool chưa trả trạng thái tương ứng -> nhãn tiếng Việt/Anh phải ánh xạ 1-1 với trạng thái (xem 5.3). "Đơn" (order) vs "yêu cầu hoàn tiền" (refund) vs "ticket"; "thanh toán" (payment) != "trạng thái đơn".

### 4.2 PII inventory

| Dữ liệu PII | Lưu ở | Ai đọc được | Rủi ro / ghi chú |
|-------------|-------|-------------|-------------------|
| email, họ tên, SĐT | `users` | app role (API), staff qua tìm đơn (email/SĐT); **mcp không** | OK theo D11 |
| địa chỉ, SĐT nhận hàng | `orders.shipping_address` / `addresses` | customer own; staff; **mcp nếu cột trong `orders`** (A-p3 cấp SELECT orders) | Xung đột RT9 |
| mật khẩu hash, refresh hash | users, refresh_tokens | chỉ auth service | OK |
| nội dung chat (tự do, có thể có SĐT/CCCD/STK) | LangGraph checkpoints, `conversations.title` | customer own; staff chỉ trích đoạn gắn refund (cơ chế chưa có); Phoenix trace (đã che) | guard_input chỉ che số thẻ/CCCD "cho log" -> nội dung vẫn lưu nguyên |
| lý do hoàn tiền, ghi chú, summary ticket | refunds, tickets | staff (render text), admin | Văn bản tự do có thể chứa PII; XSS đã xử lý |
| memory (4 field) | LangGraph store | customer own; agent (đưa vào prompt) | Ngôn ngữ/ý định: mức nhạy cảm thấp |
| mã giao dịch ngân hàng, `reference_code` | payments | staff, customer own | |
| STK nhận hoàn tiền (nếu bổ sung) | chưa có | staff | cần mã hoá/ hạn chế log |
| `tool_audit_log`, log JSON, trace | DB, log, Phoenix | ops | hash user_id có salt; OK |

### 4.3 Trùng lặp/xung đột chính

1. `orders` định nghĩa ở A rev0004 nhưng B sửa bằng migration riêng (RT10 đề xuất gộp vào rev0004 vì chưa viết).
2. Địa chỉ: jsonb snapshot (A) vs bảng `addresses` (B); RT10 đề xuất bỏ bảng.
3. `pending_payment` có trong CHECK của A nhưng A không có khái niệm thanh toán: trạng thái mồ côi tới khi B ship. Release A đứng riêng: dữ liệu seed + refund eligibility của A không biết payment.
4. `worker`: A-p9 sở hữu, B-p6 thêm job -> B phụ thuộc A-p9 (đã ghi nhưng là ràng buộc nghiệp vụ: nếu worker chưa có thì giữ tồn vô hạn).
5. Seed hiện tại: `A100 delivered` không có `delivered_at`, không có payment -> `lookup_order` tính thời hạn hoàn tiền không được; cần backfill (RT10).

### 4.4 Quyền đọc hội thoại của staff

B-p5 hứa "trích đoạn hội thoại gắn với yêu cầu"; A-p7 `GET /v1/staff/refunds/{id}` liệt kê "đơn, lý do, trần hoàn, lịch sử sự kiện" **không có hội thoại**. Đề xuất đơn giản và ít PII nhất: lưu vào `refunds` các trường `reason` + `customer_statement` (câu khách xác nhận) tại lúc `request_refund`; staff không bao giờ đọc checkpoint.

---

## 5. Gaps & ambiguities (ưu tiên)

### 5.1 MUST

| ID | Gap | Đề xuất xử lý |
|----|-----|---------------|
| M1 | Tham số chính sách hoàn tiền: thời hạn, công thức `max_refundable`, ship, 1 lần vs cộng dồn, bắt buộc P=`paid` (BR-02..07) | Chủ shop chốt bảng tham số (user decision #1); đặt vào config; KB dùng chung giá trị |
| M2 | Huỷ đơn đã thanh toán không có đường hoàn (BR-08, T15) | Accept RT3: auto-refund hệ thống vào queue; chặn expiry với `awaiting_confirmation`; định nghĩa xác nhận trễ trên đơn đã huỷ |
| M3 | Vòng đời COD + giao thất bại (BR-23, 26, T2, T14) | COD vào `processing`; thêm `delivery_failed -> cancelled` (restock) hoặc cho staff huỷ từ `shipped` có lý do; COD chưa thu không hoàn được |
| M4 | Ticket không có xử lý (BR-39) | Thêm màn Ticket tối thiểu vào B-p5 + thông báo khi đóng; hoặc ghi rõ "ticket = email/Slack ngoài hệ thống" và gửi thật |
| M5 | Nơi nhận tiền hoàn + kiểm hàng trả (BR-12, 13) | Form "thông tin nhận hoàn tiền" (tên TK, STK, ngân hàng) trong bước xác nhận (thẻ UI, **không** gõ trong chat); staff checklist "đã nhận hàng trả/đã xác minh" trước `paid_out` |
| M6 | Bảng trạng thái hợp nhất và bất biến (mục 3.5), nhãn khách thấy (5.3) | Một file spec `state-machines` do A/B cùng tham chiếu; gộp events |
| M7 | Quyền/phân công role: admin làm gì, ai quản lý staff/catalog/KB/ticket, self-dealing, deactivate staff | Chốt ma trận mục 1.2; tối thiểu: admin = tạo/vô hiệu staff (CLI hoặc 1 API) |
| M8 | Consent + retention + xoá tài khoản (BR-33..36) | Thông báo ngắn lúc đăng ký + dòng trong chat widget; bảng retention (mục 8 #10); xoá tài khoản = quy trình thủ công qua CLI có tài liệu |
| M9 | Nguồn chính sách duy nhất + chủ nội dung KB (BR-45) | Chủ shop cung cấp 5 tài liệu vi/en; server config là nguồn, KB tham chiếu; version `kb_documents.version` |
| M10 | Dữ liệu seed/legacy thiếu `delivered_at`, payment, `items jsonb` (4.3.5) | Seed mới đầy đủ; test eval dùng bộ đơn tường minh (delivered có/không trong hạn, COD chưa thu...) |

### 5.2 SHOULD

| ID | Gap | Đề xuất |
|----|-----|---------|
| S1 | Refund chỉ qua chat | Nút "Yêu cầu hoàn tiền" ở chi tiết đơn gọi cùng service (chat không phải điểm đơn lẻ) |
| S2 | SLA & giờ làm việc (xác nhận CK, duyệt hoàn tiền, ticket); hết hạn 24h lúc nhân viên nghỉ | Hiển thị "xử lý trong giờ hành chính"; "đã chuyển" gia hạn tới 48h một lần |
| S3 | Chuyển khoản thiếu/thừa/trùng mã giao dịch/nhầm nội dung | `received_amount_vnd`; sai lệch -> ghi chú + từ chối hoặc cho thanh toán bổ sung (chọn 1) |
| S4 | Danh sách sự kiện thông báo + ngôn ngữ + người nhận staff | Bảng (5.3); khách nhận in-app + nhãn VN; staff thấy badge số việc |
| S5 | Giới hạn lạm dụng: qty/đơn, đơn chưa thanh toán, spam hoàn tiền sau từ chối | RT8; hoàn tiền lại tối đa 2 lần/đơn |
| S6 | Khách không đổi/huỷ qua chat | Tool `cancel_order` hoặc handoff có kịch bản rõ (liên quan PM capability matrix) |
| S7 | Khách xem lịch sử yêu cầu hoàn tiền/ticket | Mục trong chi tiết đơn |
| S8 | Quên mật khẩu/khoá tài khoản | Quy trình staff hỗ trợ bằng CLI + tài liệu; SMTP để sau |
| S9 | Hoá đơn/biên nhận (mục 7) | Trang biên nhận in được; VAT theo yêu cầu thủ công |
| S10 | Staff tìm đơn theo email/SĐT -> PII rộng | Log truy cập PII (đã có ở B-p5 risk); giới hạn mask SĐT trong danh sách |
| S11 | Chat guest tư vấn | Cho tư vấn catalog/KB (không tool đơn, không memory) |
| S12 | Restock khi trả hàng | Staff checkbox cộng tồn khi nhận hàng |

### 5.3 COULD

Shipper + proof of delivery; email/SMS; địa chỉ đã lưu + danh mục hành chính; mã giảm giá; RMA đầy đủ; đa kho; đánh giá sản phẩm; báo cáo doanh thu; trang quản trị catalog.

### 5.4 Thông điệp trạng thái hướng khách (đề xuất, chủ shop duyệt câu chữ)

Chat EN dùng cột EN; UI/toast dùng VN. Guard của agent phải dùng đúng từ tương ứng.

| Trạng thái | VN (UI) | EN (chat) | Việc tiếp theo cho khách |
|-----------|---------|-----------|--------------------------|
| O `pending_payment` + P `pending` (CK) | Chờ thanh toán (giữ hàng đến hh:mm) | Awaiting payment (stock held until ...) | Chuyển khoản theo hướng dẫn |
| P `awaiting_confirmation` | Đã ghi nhận chuyển khoản, chờ cửa hàng xác nhận | Transfer reported, awaiting confirmation | Chờ; giờ xử lý |
| P `failed` | Chưa xác nhận được khoản chuyển (lý do) | Transfer could not be verified (reason) | Chuyển lại/liên hệ |
| O `processing` | Đang chuẩn bị hàng | Preparing your order | - |
| O `shipped` | Đang giao (hãng, mã vận đơn) | Shipped (carrier, tracking) | Theo dõi vận đơn |
| O `delivered` | Đã giao (ngày) | Delivered (date) | Hoàn tiền được đến [ngày hạn] |
| O `cancelled` | Đã huỷ (+ "đang hoàn tiền" nếu đã trả) | Cancelled (refund in progress if paid) | |
| R `pending_staff` | Đã gửi yêu cầu, chờ nhân viên duyệt | Request submitted, pending staff review | **Chưa** phải đã hoàn tiền |
| R `approved` | Đã duyệt `X`đ, đang chuyển tiền | Approved, payout in progress | Chưa phải đã nhận tiền |
| R `paid_out` | Đã hoàn `X`đ (mã tham chiếu) | Refunded (reference) | |
| R `rejected` | Yêu cầu bị từ chối: lý do | Request rejected: reason | Gửi lại được (nếu cho phép) |
| R `cancelled` | Bạn đã huỷ yêu cầu | You cancelled the request | |
| Ticket tạo | Đã chuyển nhân viên, mã TK-xxxx | Handed off, ticket TK-xxxx | Khung thời gian phản hồi (cần SLA) |

Lỗi hệ thống (LLM/MCP timeout): thông điệp an toàn, không nói "đã/đang" khi chưa chắc (đã có guard_output; cần mẫu chung vi/en).

---

## 6. Acceptance criteria

### 6.1 Top 10 user story (Given/When/Then)

**US1 - Guest/khách tìm sản phẩm qua chat (vi/en)**
- Given khách đã đăng nhập, When hỏi "laptop dưới 20 triệu cho sinh viên" / "any phone under 10M VND?", Then bot trả lời đúng ngôn ngữ, giá và tồn khớp DB, không nêu sản phẩm ngoài catalog.
- Given chưa đăng nhập, When mở chat, Then thấy lời mời đăng nhập (hành vi hiện tại B-p1; xem decision #7).

**US2 - Đăng ký/đăng nhập giữ phiên**
- Given email chưa dùng, When đăng ký, Then tạo `customer` (không nhận `role`), đăng nhập, giữ giỏ.
- Given đã đăng nhập, When tải lại trang/mở 2 tab, Then phiên còn, không bị đăng xuất. Given sai mật khẩu 5 lần, Then bị làm chậm, thông báo không lộ email tồn tại hay không.

**US3 - Đặt hàng COD**
- Given giỏ hợp lệ và tồn đủ, When Đặt hàng (COD), Then tạo đúng 1 đơn dù bấm đúp (Idempotency-Key), tổng = tạm tính + ship (30k nếu <500k) do server tính, tồn giảm, đơn hiện trong "Đơn hàng của tôi" với trạng thái "Đang chuẩn bị".
- Given sản phẩm cuối cùng, When 2 người cùng đặt, Then đúng 1 thành công, người còn lại nhận thông báo hết hàng.

**US4 - Đặt hàng chuyển khoản + xác nhận**
- Given đơn CK `pending_payment`, When khách bấm "Tôi đã chuyển", Then payment `awaiting_confirmation`, đơn không bị hết hạn trong khi chờ (theo rule gia hạn).
- When staff xác nhận (đúng số tiền), Then payment `paid`, đơn `processing`, khách nhận thông báo; khi quá 24h không báo chuyển thì đơn huỷ và tồn trả đúng 1 lần.

**US5 - Khách huỷ đơn**
- Given đơn chưa `shipped`, When khách huỷ, Then đơn `cancelled`, tồn trả đúng 1 lần, thông báo; nếu payment `paid` thì refund hệ thống xuất hiện trong queue (nếu M2 được chấp nhận).
- Given đơn `shipped`, Then nút huỷ không có và API trả lỗi chuẩn.

**US6 - Hỏi tình trạng đơn qua chat (vi/en)**
- Given khách có đơn A101, When hỏi "đơn A101 đến đâu rồi" / "where is order A101", Then trả trạng thái, hãng + mã vận đơn, trạng thái thanh toán theo ngôn ngữ khách; hỏi đơn của người khác -> từ chối lịch sự, không lộ tồn tại.

**US7 - Yêu cầu hoàn tiền qua chat -> duyệt -> chi trả**
- Given đơn `delivered` trong hạn (và đã thu), When khách xin hoàn "đơn A100 lỗi", Then agent hiển thị thẻ xác nhận (đơn, số tiền <= trần, lý do); chỉ sau khi khách xác nhận mới có refund `pending_staff`; bot nói "chờ nhân viên duyệt" và **không** nói đã hoàn.
- When staff duyệt rồi nhập `payout_reference`, Then refund `paid_out`, payment `refunded`, khách thấy thông báo <= 30s; số chi = số duyệt.
- Given đơn không đủ điều kiện (chưa giao/quá hạn/COD chưa thu), Then bot giải thích lý do bằng ngôn ngữ khách và không gọi `request_refund`.

**US8 - Từ chối hoàn tiền và gửi lại**
- Given refund `pending_staff`, When staff từ chối không ghi chú, Then bị chặn; có ghi chú -> `rejected`, khách thấy lý do.
- When khách xin lại (trong giới hạn lần), Then yêu cầu mới được tạo; khi đang có yêu cầu sống thì bị chặn; staff không duyệt yêu cầu của chính mình; hai staff cùng quyết: người sau nhận 409.

**US9 - Chuyển người hỗ trợ (ticket)**
- Given khách yêu cầu gặp nhân viên, When bot handoff, Then ticket tạo với mã, bot trả mã + thời gian phản hồi dự kiến; staff thấy ticket trong hàng đợi, đổi trạng thái, khách nhận thông báo khi xử lý xong. *(Hai vế sau hiện không có plan nào phủ.)*

**US10 - Quản lý dữ liệu cá nhân trong chat**
- Given khách có memory, When xem "Bộ nhớ của tôi", Then thấy đúng các mục đã lưu; xoá một mục -> bot không dùng nữa ở lượt sau; xoá hội thoại -> không còn trong danh sách và checkpoint bị xoá.
- Given khách lần đầu chat, Then thấy thông báo dữ liệu chat/memory được lưu bao lâu (BR-31/33).

### 6.2 Traceability

| Story | Plan phase | Test/eval chứng minh | Phủ |
|-------|-----------|----------------------|:---:|
| US1 | A-p5 `search_products`, A-p6 router/agent, B-p1 login prompt | A-p8 eval nhóm chức năng ("tư vấn sản phẩm giá khớp DB", vi/en) | Có (guest chat: không có story/test) |
| US2 | A-p4, B-p1 | A-p4 test auth (trùng email, refresh song song...), B-p1 Vitest, B-p7 e2e bước 1 | Có |
| US3 | B-p3, A-p3 | B-p3 test đua/idempotency, B-p7 e2e "COD" | Có một phần: e2e dừng ở "thấy đơn", **không** chạy giao/thu COD |
| US4 | B-p4, B-p6 | B-p4 test máy trạng thái, B-p7 e2e CK->xác nhận | Một phần: hết hạn/race với xác nhận (RT2) chưa có test; sai số tiền MS |
| US5 | B-p6 | B-p6 test trả tồn, huỷ đồng thời | Một phần: huỷ đơn đã trả tiền **không có phase/test** (RT3); không e2e |
| US6 | A-p5 `lookup_order`, B-p6 hiển thị mốc | A-p8 eval "tra đơn" vi/en; A-p5 test truy cập đơn người khác | Có (phí ship/payment/thông báo hiển thị: phụ thuộc B-p3/6) |
| US7 | A-p5/6/7, B-p5 | A-p6 test confirm/intent dính; A-p7 test máy trạng thái; A-p8 eval hoàn tiền (cứng); B-p7 e2e "chi trả" | Có; thiếu: COD chưa thu, hạn hoàn, chi trả sai số tiền kết hợp payment |
| US8 | A-p5, A-p7 | A-p5 test gửi lại sau từ chối; A-p7 test self-approve/409; A-p8 eval "bị từ chối -> gửi lại" | Có; thiếu e2e UI từ chối |
| US9 | A-p5 tool, A-p6 handoff | A-p8 eval "đòi gặp người" | **Chỉ vế tạo ticket**; không phase/test cho màn staff, thông báo khách, SLA |
| US10 | A-p6 remember/TTL, A-p7 `/me/memory`, `DELETE conversations` | A-p6 test TTL, A-p7 test xoá thật | Một phần: consent/notice **không có**; UI quản lý memory: B-p2 chỉ có danh sách hội thoại, **không** màn memory |

**Story không có phase/test phủ (cần bổ sung hoặc bỏ):**
1. Staff xử lý ticket + khách theo dõi ticket (US9).
2. Huỷ đơn đã trả tiền -> refund (US5/RT3).
3. COD end-to-end: giao, thu tiền, giao thất bại.
4. Khách hoàn tiền không qua chat / khi LLM sập.
5. Nhập thông tin nhận tiền hoàn + kiểm hàng trả.
6. Quản lý memory trên UI (API có, frontend không).
7. Consent/thông báo quyền riêng tư; xoá tài khoản; export dữ liệu.
8. Quản lý staff (tạo/vô hiệu), catalog, tồn, KB qua UI; deactivate staff được test ở A-p4 nhưng không có đường kích hoạt.
9. Nhận biết/chặn hoàn tiền COD chưa thu (eval/test).
10. Chat tiếng Anh cho luồng thông báo/ticket/staff (eval chỉ phủ trả lời bot).
11. Quên mật khẩu (workaround).
12. Hoá đơn/biên nhận.

---

## 7. Compliance / consumer-protection (chỉ để xác nhận với chủ shop, không phải tư vấn pháp lý)

1. **Hoá đơn/biên nhận:** shop có bán theo pháp nhân/hộ kinh doanh cần xuất hoá đơn (điện tử)? Giá niêm yết đã gồm VAT? Plan không có biên nhận/hoá đơn.
2. **Chính sách đổi trả/bảo hành/vận chuyển/thanh toán/bảo mật:** website TMĐT thường phải công bố; hiện chỉ nằm trong KB để bot trả lời, **chưa có trang công khai** cho khách đọc trước khi mua. Cần xác nhận nội dung và thời hạn (liên quan quyền đổi trả/ hủy đơn của người tiêu dùng khi mua từ xa).
3. **Dữ liệu cá nhân:** cần xác nhận cơ sở pháp lý/đồng ý thu thập (email, SĐT, địa chỉ, nội dung chat), mục đích, thời hạn lưu, quyền xem/sửa/xoá/rút lại, bên xử lý (LLM/embedding tự host: dữ liệu có ra ngoài không?). Plan có xem/xoá memory và hội thoại nhưng không có thông báo, không có điều khoản, không có quy trình tài khoản.
4. **Thông tin bắt buộc hiển thị** (tên/địa chỉ/liên hệ người bán, giá, phí ship, điều kiện thanh toán): chưa có trong storefront.
5. **Đăng ký/thông báo website TMĐT** với cơ quan quản lý nếu bán thật: xác nhận với chủ shop.
6. **Thanh toán chuyển khoản thủ công:** tài khoản nhận tiền thuộc chủ thể bán hàng? Đối soát/lưu chứng từ.
7. **Nội dung bot:** tư vấn/khẳng định về bảo hành/hoàn tiền phải khớp chính sách công bố (BR-45); cần tuyên bố "bot AI" cho khách.

---

## 8. Quyết định USER cần chốt (tối đa 12) + mặc định đề xuất

| # | Quyết định | Mặc định đề xuất |
|---|-----------|------------------|
| 1 | Tham số hoàn tiền: thời hạn, trần số tiền, ship có hoàn không, 1 lần hay cộng dồn | 7 ngày từ `delivered_at`; trần = tiền hàng thực thu - đã hoàn; không hoàn ship trừ lỗi shop/huỷ trước giao; cộng dồn <= số thực thu; yêu cầu P=`paid` |
| 2 | Đơn đã trả tiền rồi huỷ (RT3) | Tự tạo refund hệ thống trong queue staff; khách huỷ đến trước `shipped` |
| 3 | Vòng đời COD + giao thất bại | COD bắt đầu `processing`, không hết hạn; thêm `delivery_failed`/staff huỷ từ `shipped` -> restock; COD chưa thu không hoàn |
| 4 | Chuyển khoản: hết hạn & gia hạn | 24h; "đã chuyển" gia hạn thêm 24h một lần; expiry không động `awaiting_confirmation`; nhân viên xác nhận trễ -> hàng đợi đối soát |
| 5 | Nơi nhận tiền hoàn & trả hàng | Form thông tin nhận tiền trong bước xác nhận; staff checkbox "đã nhận hàng trả/xác minh" trước `paid_out` |
| 6 | Quyền staff vs admin & phân tách trách nhiệm | admin = staff + quản lý nhân viên (CLI/API nhỏ); không ai thao tác tiền/trạng thái trên đơn của chính mình; duyệt và chi trả khác người **không** bắt buộc (D2 giữ nguyên) |
| 7 | Chat cho guest | Giữ đăng nhập bắt buộc cho MVP; ghi nhận Could: guest hỏi catalog/KB không memory |
| 8 | Xử lý ticket | Thêm màn Ticket tối thiểu (list, trạng thái, ghi chú, thông báo khách) vào B-p5 |
| 9 | Kênh thông báo & ngôn ngữ | In-app (poll 30s) cho MVP, nhãn VN trên UI; bot trả lời theo ngôn ngữ chat; staff console + ticket + nội dung thông báo = tiếng Việt; email để sau (chấp nhận khách không thấy nếu không quay lại site) |
| 10 | Quyền riêng tư & lưu trữ | Thông báo khi đăng ký + trong chat; memory TTL 180d (giữ); checkpoint hội thoại đóng 90d; soft-delete purge 30d; audit/event 24 tháng; xoá tài khoản = quy trình thủ công có tài liệu |
| 11 | Chủ & nguồn chính sách/KB | Chủ shop viết 5 tài liệu vi/en; tham số chính sách ở config là nguồn thật; trang công khai chính sách + biên nhận in được; VAT theo yêu cầu |
| 12 | Phí ship & giới hạn mua | Giữ 30.000đ, miễn phí từ 500.000đ tạm tính (cấu hình, server tính); max qty/dòng 10, <=3 đơn chưa thanh toán/user (RT8) |

---

## Câu hỏi chưa giải quyết

1. `max_refundable` có gồm phí ship / chiết khấu COD / phí khác không? (phụ thuộc #1)
2. Hoàn tiền một phần có đổi payment sang `refunded` không (RT open Q) hay cần `partially_refunded`?
3. Staff có được đặt hàng bằng tài khoản staff không; có cần tài khoản khách riêng?
4. Hành vi bot sau handoff: tiếp tục trả lời hay im lặng?
5. Khách có thể huỷ đơn bằng chat (cần tool) hay chỉ qua UI?
6. Khi LLM host sập, khách có kênh nào hoàn tiền/hỗ trợ không? (S1)
7. Ngôn ngữ của staff console nếu khách chat EN (tóm tắt ticket/lý do hoàn tiền dịch hay giữ nguyên)?
8. Cổng 8000 / demo HTTP có hỗ trợ không (ảnh hưởng cookie `Secure`, RT open Q): nằm ngoài phạm vi BA nhưng ảnh hưởng "tải lại giữ phiên".
9. Hoàn thành đơn: có trạng thái `completed` sau hết thời hạn hoàn tiền không (để chặn hoàn muộn và báo cáo doanh thu)?
10. Báo cáo/đối soát cuối ngày cho chủ shop (tiền COD, CK, hoàn) có cần không (hiện dashboard B-p5 chỉ đếm việc cần làm; RT15 đề xuất cắt)?
