# Luồng vận hành: khách hàng và chủ shop

Tài liệu cho người dùng cuối và chủ shop. Chi tiết kỹ thuật: `docs/deployment-guide.md`, `docs/api/`.

## 1. Chạy hệ thống

Cần: Docker, và các endpoint mô hình (LLM, embedding, reranker) truy cập được từ máy chạy (mặc định `https://your-api-model-host/...` trong `.env.example`).

```
scripts/init-env.sh              # Windows PowerShell: powershell -File scripts\init-env.ps1
docker compose up -d --build
```

Script đầu tạo `.env` từ `.env.example` với khoá ngẫu nhiên (mật khẩu DB, khoá MCP, khoá nhân viên) và in ra **khoá nhân viên**; không ghi đè `.env` đã có. Lệnh thứ hai dựng và chạy tất cả theo thứ tự: DB -> tạo bảng và dữ liệu mẫu -> (MCP server, nạp tài liệu) -> API -> giao diện. Lần đầu mất vài phút để build.

| Địa chỉ | Dùng cho |
|---|---|
| http://localhost:3000 | cửa hàng + trợ lý AI (khách) |
| http://localhost:3000/nhan-vien | khu vực nhân viên (chủ shop) |
| http://localhost:8000/docs | tài liệu API (dành cho lập trình viên) |

Dừng: `docker compose down` (giữ dữ liệu). Xoá sạch dữ liệu để làm lại từ đầu: `docker compose down -v`.

```
Khách ──> Giao diện (nginx) ──> API ──> Trợ lý AI (LangGraph) ──> MCP server ──> Postgres
Chủ shop ─> /nhan-vien ──────────┘            │ tra chính sách (RAG)        (giỏ, đơn, hoàn tiền)
                                              └─> LLM / embedding / reranker (bên ngoài)
```

## 2. Luồng của khách hàng

Khách **không cần đăng nhập**. Trình duyệt giữ một mã phiên ngẫu nhiên: giỏ hàng gắn với mã này và dùng chung giữa trang web với trợ lý AI. Muốn xem hoặc xử lý một đơn đã đặt thì khách cung cấp **mã đơn + số điện thoại đặt hàng**.

1. **Xem hàng**: trang chủ, danh mục, tìm kiếm, trang chi tiết (giá, giảm giá, tồn kho, thông số).
2. **Hỏi trợ lý** (nút "Trợ lý AI" góc phải): tư vấn chọn máy, so sánh, giá và tồn kho thật, khuyến mãi, chính sách giao hàng, bảo hành, đổi trả, hoàn tiền. Trợ lý xưng "em", gọi khách "anh/chị", chỉ hỗ trợ việc của shop; câu ngoài lề được từ chối nhẹ nhàng.
3. **Thêm vào giỏ**: bấm nút trên trang, hoặc nhắn "thêm 2 củ sạc Anker vào giỏ". Số trên biểu tượng giỏ cập nhật ngay; tải lại trang giỏ vẫn còn. Tồn kho được kiểm tra, mỗi sản phẩm tối đa 10.
4. **Đặt hàng**: vào trang giỏ, bấm "Đặt hàng với trợ lý AI" (hoặc nhắn "mình muốn đặt hàng"). Trợ lý hỏi họ tên người nhận, số điện thoại, địa chỉ đầy đủ và cách thanh toán, rồi **tóm tắt đơn để khách xác nhận**. Chỉ sau khi khách nhắn xác nhận, đơn mới được tạo:
   - **COD**: trả tiền khi nhận hàng.
   - **Online**: thanh toán ngay trong chat (hiện là cổng **mô phỏng**, không trừ tiền thật).
   - Phí ship 30.000₫, miễn phí từ 500.000₫. Khách nhận **mã đơn** dạng `SM001000`.
5. **Theo dõi đơn**: nhắn "đơn SM001000 SĐT 09xxxxxxxx đến đâu rồi". Trạng thái: đang xử lý, đang giao, đã giao, đã hủy.
6. **Hủy đơn**: được khi đơn "đang xử lý" và chưa thanh toán online (đơn đã trả tiền cần nhân viên hỗ trợ).
7. **Yêu cầu hoàn tiền**: nhắn mã đơn, SĐT và lý do. Trợ lý kiểm tra điều kiện (đơn đã giao, trong 7 ngày kể từ ngày giao, lý do: không đúng mô tả, lỗi, giao sai/thiếu, hư hỏng khi vận chuyển; đổi ý không được hoàn), nêu số tiền, hỏi xác nhận rồi gửi yêu cầu. **Tiền chưa được hoàn ở bước này**: yêu cầu chờ nhân viên duyệt, nhân viên gọi vào số điện thoại đặt hàng để xác nhận cách nhận tiền. Khách hỏi lại "đã duyệt chưa" bất cứ lúc nào để xem kết quả.

Ví dụ:

> Khách: Thêm 1 củ sạc Anker 20W vào giỏ giúp mình
> Trợ lý: Dạ em đã thêm vào giỏ ạ. Giỏ hiện có 1 củ sạc, phí ship 30.000₫, tổng 320.000₫...
> Khách: Mình muốn đặt hàng, người nhận Trần Thị B, 0912345678, 25 Lê Lợi, P. Bến Thành, Q.1, TP.HCM, thanh toán online
> Trợ lý: (tóm tắt đơn) Anh/chị xác nhận đặt hàng giúp em nhé?
> Khách: Xác nhận
> Trợ lý: Đơn SM001000 đã đặt và thanh toán thành công ạ...

Giới hạn để chống spam: nhắn quá nhanh (10 tin/phút) sẽ được nhắc chờ; gửi lặp cùng nội dung bị chặn; tra đơn sai nhiều lần bị khoá tạm vài phút; mỗi phiên tối đa 5 đơn mỗi giờ.

## 3. Luồng của chủ shop

### Duyệt hoàn tiền và cập nhật đơn (tab "Hoàn tiền và đơn hàng")
1. Mở `/nhan-vien`, nhập **khoá nhân viên** (`STAFF_API_KEY` trong `.env`; `init-env` đã in ra). Khoá chỉ lưu trong tab hiện tại.
2. Mục **Yêu cầu hoàn tiền chờ duyệt** liệt kê: mã yêu cầu, đơn, khách và SĐT, cách thanh toán, lý do và mô tả, số tiền hoàn. Gọi điện cho khách theo SĐT để xác nhận và thoả thuận cách trả tiền, rồi bấm **Duyệt hoàn tiền** hoặc **Từ chối** (có thể ghi chú). Hoàn toàn bộ đơn thì đơn chuyển sang "đã hoàn tiền". Việc chuyển tiền thật làm ngoài hệ thống.
3. Mục **Cập nhật trạng thái đơn**: nhập mã đơn, bấm "Đang giao" rồi "Đã giao". Với đơn COD, bấm "Đã giao" nghĩa là đã thu tiền. Hoàn tiền chỉ mở khi đơn đã ở trạng thái "đã giao".

### Cập nhật kiến thức cho trợ lý (chính sách, mô tả sản phẩm)
Các file markdown trong thư mục `documents/` (`policies/`, `products/`; cũng nhận `.txt`, `.pdf`, `.docx`). Sửa hoặc thêm file rồi chạy:

```
docker compose run --rm ingest
```

File không đổi thì bỏ qua, file đổi thì thay toàn bộ nội dung cũ. (Cách khác: gọi API `POST /documents/upload`, xem `docs/api/document-ingestion.md`.) Tài liệu **không ghi giá và tồn kho** vì các số này luôn được tra trực tiếp từ hệ thống; số liệu chính sách (phí ship, hạn hoàn tiền) phải khớp với `.env`.

### Quản lý sản phẩm (giá, tồn kho, thêm, sửa, xoá)
Vào `/nhan-vien`, đăng nhập rồi chọn tab **Sản phẩm** (mở sẵn). Danh sách hiện mọi sản phẩm, kể cả hết hàng, kèm ảnh, giá (giá gốc gạch ngang nếu đang giảm) và nhãn tồn kho (xanh: còn hàng, vàng: sắp hết, đỏ: hết). Có ô tìm kiếm và lọc theo danh mục.

- **Sửa**: bấm "Sửa" ở dòng sản phẩm, đổi tên, danh mục, thương hiệu, **giá bán**, **giá gốc** (để trống nếu không giảm giá), **tồn kho**, đánh giá, mô tả, thông số kỹ thuật, ảnh rồi "Lưu". Giá và tồn kho mới có hiệu lực **ngay**: website, giỏ hàng và trợ lý AI đều đọc số mới (khách hỏi giá thì trợ lý trả giá vừa sửa).
- **Thêm**: bấm "+ Thêm sản phẩm", nhập **mã sản phẩm (slug)** gồm chữ thường, số và dấu gạch ngang (vd `loa-jbl-flip-6`, không đổi được về sau), các thông tin còn lại và ảnh. Giá gốc phải lớn hơn giá bán.
- **Ảnh**: PNG, JPG hoặc WEBP, tối đa 2 MB (`MAX_PRODUCT_IMAGE_MB`); hệ thống kiểm tra nội dung file chứ không tin đuôi file. Ảnh mới thay ảnh cũ và ảnh cũ được xoá. Chưa có ảnh thì website hiện ảnh minh hoạ.
- **Xoá**: chỉ xoá được sản phẩm chưa từng nằm trong đơn hàng nào (giỏ hàng chứa nó được dọn theo). Sản phẩm đã có đơn thì **đặt tồn kho = 0** để ngừng bán.
- Mô tả chi tiết hơn để trợ lý **tư vấn** (người dùng phù hợp, so sánh) vẫn viết trong `documents/products/` rồi `docker compose run --rm ingest`; tài liệu đó không ghi giá và tồn kho.

### Chính sách cửa hàng
Số liệu trong `.env`: `SHIPPING_FEE_VND`, `FREE_SHIPPING_FROM_VND`, `REFUND_WINDOW_DAYS`, `MAX_QTY_PER_LINE`... Đổi xong chạy `docker compose up -d` và sửa `documents/policies/` cho khớp rồi `ingest` lại.

## 4. Dữ liệu mẫu và thử nhanh

Có 3 đơn mẫu của số điện thoại `0900000001`: `SM000100` (đã giao, thử hoàn tiền), `SM000101` (đang giao), `SM000102` (COD đang xử lý). Thử: nhắn "Tra đơn SM000100, SĐT 0900000001", rồi "Tôi muốn hoàn tiền đơn này vì tai nghe bị lỗi", rồi vào `/nhan-vien` duyệt.

## 5. Sự cố thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `docker compose up` báo lỗi ở `mcp-server` | `MCP_API_KEY` trong `.env` đang trống: chạy `scripts/init-env` (với `.env` mới) hoặc điền một chuỗi ngẫu nhiên |
| Trợ lý trả lời chậm hoặc lỗi 502 | LLM/embedding/reranker bên ngoài không truy cập được: kiểm tra các dòng `*_API_URL` trong `.env`, xem `docker compose logs api` |
| Trợ lý không biết chính sách | Nạp tài liệu chưa xong hoặc lỗi: `docker compose logs ingest`, chạy lại `docker compose run --rm ingest` |
| Trợ lý không thêm giỏ/đặt hàng được | `docker compose logs mcp-server`; MCP server chưa lên thì trợ lý chỉ trả lời kiến thức chung, tự thử lại sau 30 giây |
| Không đăng nhập được `/nhan-vien` | Sai `STAFF_API_KEY` (API nhân viên trả 503 nếu để trống) |
| Đổi mật khẩu DB trong `.env` mà DB không nhận | Mật khẩu chỉ áp dụng lúc tạo volume lần đầu: dùng `docker compose down -v` (mất dữ liệu) hoặc đổi mật khẩu trong Postgres |

## 6. Cần biết

- Thanh toán online là **mô phỏng**; chưa có cổng thanh toán thật.
- Mã phiên lưu trong trình duyệt: đổi trình duyệt hoặc xoá dữ liệu trang thì mất giỏ hàng (đơn đã đặt vẫn tra được bằng mã đơn + SĐT).
- Trợ lý là mô hình ngôn ngữ nên có thể nhầm; tiền và tồn kho luôn do hệ thống tính, và mọi hoàn tiền đều qua tay nhân viên.
