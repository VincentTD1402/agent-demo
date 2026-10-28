# Product catalog API

Danh mục sản phẩm cho storefront (frontend gọi qua `/api/v1/products`). Công khai, chỉ đọc, không cần `X-API-Key`.

| Endpoint | Mô tả |
|---|---|
| `GET /v1/products?q=&category=&limit=` | Danh sách theo thứ tự thêm vào. `q` tìm không phân biệt hoa thường trong tên, thương hiệu, mô tả; `category`: `dien-thoai`, `laptop`, `may-tinh-bang`, `dong-ho`, `phu-kien`; `limit` 1-100 (mặc định 50) |
| `GET /v1/products/{slug}` | Chi tiết một sản phẩm; 404 nếu không có |

Mỗi sản phẩm: `slug, name, category, brand, price_vnd, old_price_vnd (hoặc null), rating, stock, specs{}, description, image_url`.

Bảng `products` tạo ở migration `0003`, kèm 16 sản phẩm mẫu (giá và tên chỉ mang tính minh hoạ; ảnh ở `frontend/public/products`). Tài liệu cho chatbot trong `documents/products/` được viết khớp dữ liệu này; đổi giá/tồn kho ở DB thì cập nhật cả tài liệu rồi nạp lại.

Code: `backend/app/products/` (`repository.py`, `router.py`); test: `backend/tests/test_products_api.py`.
