"""Dữ liệu mẫu để chạy thử cửa hàng (tên sản phẩm/giá chỉ mang tính minh hoạ)."""


# Ảnh thật (Wikimedia Commons, trang chính hãng, CellphoneS...) nằm ở frontend/public/products; sản phẩm không có ảnh
# thì frontend vẽ ảnh SVG dự phòng. Nguồn từng ảnh: frontend/public/products/CREDITS.txt
IMAGES = {
    "galaxy-tab-s9-fe": "/products/galaxy-tab-s9-fe.jpg",
    "sony-wh-1000xm5": "/products/sony-wh-1000xm5.png",
    "dell-inspiron-14-5440-i5": "/products/dell-inspiron-14-5440-i5.png",
    "samsung-galaxy-s25-256gb": "/products/samsung-galaxy-s25-256gb.jpg",
    "oppo-reno13-5g": "/products/oppo-reno13-5g.jpg",
    "macbook-air-m3-13": "/products/macbook-air-m3-13.png",
    "lenovo-loq-15-rtx4050": "/products/lenovo-loq-15-rtx4050.png",
    "xiaomi-smart-band-9": "/products/xiaomi-smart-band-9.png",
    "anker-sac-20w": "/products/anker-sac-20w.png",
    "iphone-16-128gb": "/products/iphone-16-128gb.jpg",
    "xiaomi-redmi-note-14-pro": "/products/xiaomi-redmi-note-14-pro.jpg",
    "asus-vivobook-15-i5": "/products/asus-vivobook-15-i5.jpg",
    "ipad-gen-10-64gb": "/products/ipad-gen-10-64gb.jpg",
    "apple-watch-se-2": "/products/apple-watch-se-2.jpg",
    "airpods-pro-2-usb-c": "/products/airpods-pro-2-usb-c.jpg",
    "pin-du-phong-anker-10000": "/products/pin-du-phong-anker-10000.jpg",
}


def _p(slug, name, category, brand, price, old, rating, stock, specs, description):
    return {
        "slug": slug, "name": name, "category": category, "brand": brand,
        "price_vnd": price, "old_price_vnd": old, "rating": rating, "stock": stock,
        "specs": specs, "description": description,
        "image_url": IMAGES.get(slug),
    }


PRODUCTS = [
    _p("iphone-16-128gb", "iPhone 16 128GB", "dien-thoai", "Apple", 22990000, 24990000, 4.8, 25,
       {"Màn hình": "6.1 inch OLED", "Chip": "A18", "RAM": "8GB", "Bộ nhớ": "128GB", "Pin": "3561 mAh"},
       "Chip A18 mạnh mẽ, camera 48MP, nút Camera Control mới."),
    _p("samsung-galaxy-s25-256gb", "Samsung Galaxy S25 256GB", "dien-thoai", "Samsung", 20990000, 22990000, 4.7, 18,
       {"Màn hình": "6.2 inch AMOLED 120Hz", "Chip": "Snapdragon 8 Elite", "RAM": "12GB", "Bộ nhớ": "256GB", "Pin": "4000 mAh"},
       "Flagship nhỏ gọn với Galaxy AI, camera 50MP chống rung quang học."),
    _p("xiaomi-redmi-note-14-pro", "Xiaomi Redmi Note 14 Pro 8GB/256GB", "dien-thoai", "Xiaomi", 8490000, 9490000, 4.5, 40,
       {"Màn hình": "6.67 inch AMOLED 120Hz", "Chip": "Helio G100-Ultra", "RAM": "8GB", "Bộ nhớ": "256GB", "Pin": "5500 mAh"},
       "Camera 200MP, sạc nhanh 45W, pin trâu cả ngày."),
    _p("oppo-reno13-5g", "OPPO Reno13 5G 12GB/256GB", "dien-thoai", "OPPO", 12990000, None, 4.4, 22,
       {"Màn hình": "6.59 inch AMOLED 120Hz", "Chip": "Dimensity 8350", "RAM": "12GB", "Bộ nhớ": "256GB", "Pin": "5600 mAh"},
       "Thiết kế mỏng nhẹ, camera chân dung AI, sạc 80W."),
    _p("macbook-air-m3-13", "MacBook Air 13 inch M3 8GB/256GB", "laptop", "Apple", 24990000, 27990000, 4.9, 12,
       {"Màn hình": "13.6 inch Liquid Retina", "Chip": "Apple M3", "RAM": "8GB", "SSD": "256GB", "Pin": "Đến 18 giờ"},
       "Mỏng nhẹ không quạt, hiệu năng M3 cho học tập và làm việc."),
    _p("asus-vivobook-15-i5", "ASUS Vivobook 15 Core i5 13420H", "laptop", "ASUS", 15490000, 16990000, 4.3, 15,
       {"Màn hình": "15.6 inch FHD", "CPU": "Intel Core i5-13420H", "RAM": "16GB", "SSD": "512GB", "Pin": "42 Wh"},
       "Laptop văn phòng hiệu năng tốt, bàn phím full-size."),
    _p("lenovo-loq-15-rtx4050", "Lenovo LOQ 15 RTX 4050", "laptop", "Lenovo", 23990000, 25990000, 4.6, 8,
       {"Màn hình": "15.6 inch FHD 144Hz", "CPU": "Intel Core i5-12450HX", "GPU": "RTX 4050 6GB", "RAM": "16GB", "SSD": "512GB"},
       "Laptop gaming tản nhiệt tốt, chơi mượt các tựa game phổ biến."),
    _p("dell-inspiron-14-5440-i5", "Dell Inspiron 14 5440 Core i5-1334U 24GB/512GB", "laptop", "Dell", 19990000, None, 4.4, 10,
       {"Màn hình": "14 inch Full HD", "CPU": "Intel Core i5-1334U", "RAM": "24GB DDR5", "SSD": "512GB", "Đồ hoạ": "Intel UMA"},
       "Vỏ kim loại, RAM 24GB đa nhiệm tốt, phù hợp dân văn phòng."),
    _p("ipad-gen-10-64gb", "iPad Gen 10 Wi-Fi 64GB", "may-tinh-bang", "Apple", 9490000, 10990000, 4.7, 30,
       {"Màn hình": "10.9 inch Liquid Retina", "Chip": "A14 Bionic", "Bộ nhớ": "64GB", "Camera": "12MP"},
       "Thiết kế phẳng, nhiều màu, hỗ trợ Apple Pencil."),
    _p("galaxy-tab-s9-fe", "Samsung Galaxy Tab S9 FE 5G", "may-tinh-bang", "Samsung", 11990000, 13990000, 4.5, 14,
       {"Màn hình": "10.9 inch 90Hz", "Chip": "Exynos 1380", "RAM": "6GB", "Bộ nhớ": "128GB", "Chống nước": "IP68"},
       "Kèm bút S Pen, chống nước IP68, pin 8000 mAh."),
    _p("apple-watch-se-2", "Apple Watch SE 2 GPS 40mm", "dong-ho", "Apple", 6290000, 6990000, 4.6, 20,
       {"Kích thước": "40mm", "Kết nối": "GPS", "Chống nước": "50m", "Pin": "Đến 18 giờ"},
       "Theo dõi sức khoẻ, phát hiện va chạm, thông báo thông minh."),
    _p("xiaomi-smart-band-9", "Xiaomi Smart Band 9", "dong-ho", "Xiaomi", 1090000, 1290000, 4.4, 80,
       {"Màn hình": "1.62 inch AMOLED", "Pin": "Đến 21 ngày", "Chống nước": "5ATM"},
       "Vòng đeo tay giá rẻ, theo dõi nhịp tim, SpO2 và giấc ngủ."),
    _p("airpods-pro-2-usb-c", "Tai nghe AirPods Pro 2 USB-C", "phu-kien", "Apple", 5490000, 6190000, 4.8, 35,
       {"Chống ồn": "ANC chủ động", "Chip": "H2", "Pin": "6 giờ (30 giờ cùng hộp)", "Sạc": "USB-C / MagSafe"},
       "Chống ồn chủ động, âm thanh không gian, hộp sạc USB-C."),
    _p("sony-wh-1000xm5", "Tai nghe chụp tai Sony WH-1000XM5", "phu-kien", "Sony", 7490000, 8990000, 4.7, 9,
       {"Chống ồn": "ANC", "Pin": "30 giờ (ANC bật) / 40 giờ", "Kết nối": "Bluetooth 5.2", "Sạc": "USB-C"},
       "Chống ồn hàng đầu, đàm thoại rõ, đeo êm cả ngày."),
    _p("anker-sac-20w", "Củ sạc nhanh Anker 20W USB-C", "phu-kien", "Anker", 290000, 390000, 4.6, 150,
       {"Công suất": "20W", "Cổng": "USB-C", "Bảo hành": "18 tháng"},
       "Sạc nhanh iPhone và Android, nhỏ gọn, bảo vệ quá nhiệt."),
    _p("pin-du-phong-anker-10000", "Pin dự phòng Anker 10000mAh", "phu-kien", "Anker", 690000, 790000, 4.5, 60,
       {"Dung lượng": "10000 mAh", "Công suất": "22.5W", "Cổng": "USB-C + USB-A"},
       "Pin dự phòng mỏng nhẹ, sạc nhanh 22.5W."),
]

# ---- Fixture cố định cho demo/e2e: id không đổi giữa các lần seed để test và frontend tham chiếu được ----
DEMO_CUSTOMER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_CUSTOMER_ID = "22222222-2222-4222-8222-222222222222"
STAFF_DEMO_ID = "33333333-3333-4333-8333-333333333333"
STAFF_DEMO_EMAIL = "staff@shopbot.local"

# Khách mẫu chưa có mật khẩu (password_hash NULL): chưa đăng nhập được cho tới khi có luồng đặt mật khẩu
CUSTOMERS = [
    {"id": DEMO_CUSTOMER_ID, "email": "demo@shopbot.local", "full_name": "Khách Demo", "phone": "0900000001"},
    {"id": OTHER_CUSTOMER_ID, "email": "other@shopbot.local", "full_name": "Khách Khác", "phone": "0900000002"},
]

SHIPPING_ADDRESS = {
    "name": "Khách Demo", "phone": "0900000001", "line1": "12 Nguyễn Huệ", "ward": "Bến Nghé",
    "district": "Quận 1", "city": "TP. Hồ Chí Minh",
}

ORDER_REFUND_ELIGIBLE_ID = "A100"  # đã giao 2 ngày trước: còn trong hạn hoàn tiền
ORDER_SHIPPED_ID = "A101"  # đang giao
ORDER_COD_ID = "A102"  # thanh toán khi nhận hàng, đang xử lý
ORDER_OTHER_CUSTOMER_ID = "B200"  # của khách khác: kiểm tra khách không xem được đơn người khác

# items: (slug sản phẩm, số lượng). Tiền hàng lấy từ giá hiện tại của sản phẩm mẫu; phí ship tính theo cấu hình
# (SHIPPING_FEE_VND, FREE_SHIPPING_FROM_VND). days_ago tính từ lúc seed.
ORDERS = [
    {"id": ORDER_REFUND_ELIGIBLE_ID, "user_id": DEMO_CUSTOMER_ID, "status": "delivered",
     "items": [("airpods-pro-2-usb-c", 1)], "created_days_ago": 5, "delivered_days_ago": 2,
     "carrier": "GHN", "tracking_code": "GHN100000001"},
    {"id": ORDER_SHIPPED_ID, "user_id": DEMO_CUSTOMER_ID, "status": "shipped",
     "items": [("anker-sac-20w", 2), ("pin-du-phong-anker-10000", 1)], "created_days_ago": 1,
     "delivered_days_ago": None, "carrier": "GHN", "tracking_code": "GHN100000002"},
    {"id": ORDER_COD_ID, "user_id": DEMO_CUSTOMER_ID, "status": "processing",
     "items": [("anker-sac-20w", 1)], "created_days_ago": 0, "delivered_days_ago": None,
     "carrier": None, "tracking_code": None},
    {"id": ORDER_OTHER_CUSTOMER_ID, "user_id": OTHER_CUSTOMER_ID, "status": "delivered",
     "items": [("sony-wh-1000xm5", 1)], "created_days_ago": 6, "delivered_days_ago": 3,
     "carrier": "GHN", "tracking_code": "GHN100000003"},
]

