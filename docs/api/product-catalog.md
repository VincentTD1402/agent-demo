# Product catalog API

Danh mục sản phẩm cho storefront (frontend gọi qua `/api/v1/products`). Công khai, chỉ đọc, không cần `X-API-Key`.

| Endpoint | Mô tả |
|---|---|
| `GET /v1/products?q=&category=&limit=` | Danh sách theo thứ tự thêm vào. `q` tìm không phân biệt hoa thường trong tên, thương hiệu, mô tả; `category`: `dien-thoai`, `laptop`, `may-tinh-bang`, `dong-ho`, `phu-kien`; `limit` 1-100 (mặc định 50) |
| `GET /v1/products/{slug}` | Chi tiết một sản phẩm; 404 nếu không có |

Mỗi sản phẩm: `slug, name, category, brand, price_vnd, old_price_vnd (hoặc null), rating, stock, specs{}, description, image_url`.

## API quản trị (nhân viên, header `X-Staff-Key`)

| Endpoint | Mô tả |
|---|---|
| `GET /staff/products?q=&category=` | tất cả sản phẩm (kể cả hết hàng), tối đa 200 |
| `POST /staff/products` | thêm: `slug` (chữ thường/số/gạch ngang, không đổi được) + các trường bên dưới |
| `PUT /staff/products/{slug}` | ghi đè toàn bộ trường chỉnh sửa được |
| `DELETE /staff/products/{slug}` | xoá nếu chưa nằm trong đơn nào (giỏ hàng chứa nó được dọn); xoá cả ảnh tải lên |
| `POST /staff/products/{slug}/image` | multipart `file`: PNG/JPG/WEBP, tối đa `MAX_PRODUCT_IMAGE_MB` (2) |

Trường: `name, category, brand, price_vnd (0..1 tỷ), old_price_vnd (null hoặc > giá bán), stock (0..100000), rating (0..5), specs{} (<=30 dòng), description (<=5000), image_url (null, đường dẫn bắt đầu bằng / hoặc https://)`. Sai đầu vào trả 422, xung đột nghiệp vụ (trùng slug, xoá sản phẩm đã có đơn, ảnh không hợp lệ) trả 400 kèm `detail` tiếng Việt. Giá/tồn kho sửa ở đây có hiệu lực ngay với website, giỏ hàng và trợ lý (cùng đọc bảng `products`).

Ảnh tải lên lưu vào volume `product-images` (api ghi, nginx phục vụ ở `/uploads/products/<slug>-<ngẫu nhiên>.<png|jpg|webp>`); loại file xác định theo chữ ký nội dung, tên file do server đặt.

Bảng `products` tạo ở migration `0003`, kèm 16 sản phẩm mẫu (giá và tên chỉ mang tính minh hoạ; ảnh ở `frontend/public/products`). Tài liệu cho chatbot trong `documents/products/` được viết khớp dữ liệu này; đổi giá/tồn kho ở DB thì cập nhật cả tài liệu rồi nạp lại.

Code: `backend/app/products/` (`repository.py`, `router.py`, `admin.py`, `admin_router.py`, `images.py`); test: `test_products_api.py`, `test_product_admin_db.py`, `test_product_images.py`.
