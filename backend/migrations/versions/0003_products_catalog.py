"""products: danh mục sản phẩm cho storefront + dữ liệu mẫu 16 sản phẩm

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# Dữ liệu mẫu (tên/giá chỉ mang tính minh hoạ). Ảnh nằm ở frontend/public/products.
SEED_PRODUCTS = json.loads(r'''
[
 {
  "slug": "iphone-16-128gb",
  "name": "iPhone 16 128GB",
  "category": "dien-thoai",
  "brand": "Apple",
  "price_vnd": 22990000,
  "old_price_vnd": 24990000,
  "rating": 4.8,
  "stock": 25,
  "specs": {
   "Màn hình": "6.1 inch OLED",
   "Chip": "A18",
   "RAM": "8GB",
   "Bộ nhớ": "128GB",
   "Pin": "3561 mAh"
  },
  "description": "Chip A18 mạnh mẽ, camera 48MP, nút Camera Control mới.",
  "image_url": "/products/iphone-16-128gb.jpg"
 },
 {
  "slug": "samsung-galaxy-s25-256gb",
  "name": "Samsung Galaxy S25 256GB",
  "category": "dien-thoai",
  "brand": "Samsung",
  "price_vnd": 20990000,
  "old_price_vnd": 22990000,
  "rating": 4.7,
  "stock": 18,
  "specs": {
   "Màn hình": "6.2 inch AMOLED 120Hz",
   "Chip": "Snapdragon 8 Elite",
   "RAM": "12GB",
   "Bộ nhớ": "256GB",
   "Pin": "4000 mAh"
  },
  "description": "Flagship nhỏ gọn với Galaxy AI, camera 50MP chống rung quang học.",
  "image_url": "/products/samsung-galaxy-s25-256gb.jpg"
 },
 {
  "slug": "xiaomi-redmi-note-14-pro",
  "name": "Xiaomi Redmi Note 14 Pro 8GB/256GB",
  "category": "dien-thoai",
  "brand": "Xiaomi",
  "price_vnd": 8490000,
  "old_price_vnd": 9490000,
  "rating": 4.5,
  "stock": 40,
  "specs": {
   "Màn hình": "6.67 inch AMOLED 120Hz",
   "Chip": "Helio G100-Ultra",
   "RAM": "8GB",
   "Bộ nhớ": "256GB",
   "Pin": "5500 mAh"
  },
  "description": "Camera 200MP, sạc nhanh 45W, pin trâu cả ngày.",
  "image_url": "/products/xiaomi-redmi-note-14-pro.jpg"
 },
 {
  "slug": "oppo-reno13-5g",
  "name": "OPPO Reno13 5G 12GB/256GB",
  "category": "dien-thoai",
  "brand": "OPPO",
  "price_vnd": 12990000,
  "old_price_vnd": null,
  "rating": 4.4,
  "stock": 22,
  "specs": {
   "Màn hình": "6.59 inch AMOLED 120Hz",
   "Chip": "Dimensity 8350",
   "RAM": "12GB",
   "Bộ nhớ": "256GB",
   "Pin": "5600 mAh"
  },
  "description": "Thiết kế mỏng nhẹ, camera chân dung AI, sạc 80W.",
  "image_url": "/products/oppo-reno13-5g.jpg"
 },
 {
  "slug": "macbook-air-m3-13",
  "name": "MacBook Air 13 inch M3 8GB/256GB",
  "category": "laptop",
  "brand": "Apple",
  "price_vnd": 24990000,
  "old_price_vnd": 27990000,
  "rating": 4.9,
  "stock": 12,
  "specs": {
   "Màn hình": "13.6 inch Liquid Retina",
   "Chip": "Apple M3",
   "RAM": "8GB",
   "SSD": "256GB",
   "Pin": "Đến 18 giờ"
  },
  "description": "Mỏng nhẹ không quạt, hiệu năng M3 cho học tập và làm việc.",
  "image_url": "/products/macbook-air-m3-13.png"
 },
 {
  "slug": "asus-vivobook-15-i5",
  "name": "ASUS Vivobook 15 Core i5 13420H",
  "category": "laptop",
  "brand": "ASUS",
  "price_vnd": 15490000,
  "old_price_vnd": 16990000,
  "rating": 4.3,
  "stock": 15,
  "specs": {
   "Màn hình": "15.6 inch FHD",
   "CPU": "Intel Core i5-13420H",
   "RAM": "16GB",
   "SSD": "512GB",
   "Pin": "42 Wh"
  },
  "description": "Laptop văn phòng hiệu năng tốt, bàn phím full-size.",
  "image_url": "/products/asus-vivobook-15-i5.jpg"
 },
 {
  "slug": "lenovo-loq-15-rtx4050",
  "name": "Lenovo LOQ 15 RTX 4050",
  "category": "laptop",
  "brand": "Lenovo",
  "price_vnd": 23990000,
  "old_price_vnd": 25990000,
  "rating": 4.6,
  "stock": 8,
  "specs": {
   "Màn hình": "15.6 inch FHD 144Hz",
   "CPU": "Intel Core i5-12450HX",
   "GPU": "RTX 4050 6GB",
   "RAM": "16GB",
   "SSD": "512GB"
  },
  "description": "Laptop gaming tản nhiệt tốt, chơi mượt các tựa game phổ biến.",
  "image_url": "/products/lenovo-loq-15-rtx4050.png"
 },
 {
  "slug": "dell-inspiron-14-5440-i5",
  "name": "Dell Inspiron 14 5440 Core i5-1334U 24GB/512GB",
  "category": "laptop",
  "brand": "Dell",
  "price_vnd": 19990000,
  "old_price_vnd": null,
  "rating": 4.4,
  "stock": 10,
  "specs": {
   "Màn hình": "14 inch Full HD",
   "CPU": "Intel Core i5-1334U",
   "RAM": "24GB DDR5",
   "SSD": "512GB",
   "Đồ hoạ": "Intel UMA"
  },
  "description": "Vỏ kim loại, RAM 24GB đa nhiệm tốt, phù hợp dân văn phòng.",
  "image_url": "/products/dell-inspiron-14-5440-i5.png"
 },
 {
  "slug": "ipad-gen-10-64gb",
  "name": "iPad Gen 10 Wi-Fi 64GB",
  "category": "may-tinh-bang",
  "brand": "Apple",
  "price_vnd": 9490000,
  "old_price_vnd": 10990000,
  "rating": 4.7,
  "stock": 30,
  "specs": {
   "Màn hình": "10.9 inch Liquid Retina",
   "Chip": "A14 Bionic",
   "Bộ nhớ": "64GB",
   "Camera": "12MP"
  },
  "description": "Thiết kế phẳng, nhiều màu, hỗ trợ Apple Pencil.",
  "image_url": "/products/ipad-gen-10-64gb.jpg"
 },
 {
  "slug": "galaxy-tab-s9-fe",
  "name": "Samsung Galaxy Tab S9 FE 5G",
  "category": "may-tinh-bang",
  "brand": "Samsung",
  "price_vnd": 11990000,
  "old_price_vnd": 13990000,
  "rating": 4.5,
  "stock": 14,
  "specs": {
   "Màn hình": "10.9 inch 90Hz",
   "Chip": "Exynos 1380",
   "RAM": "6GB",
   "Bộ nhớ": "128GB",
   "Chống nước": "IP68"
  },
  "description": "Kèm bút S Pen, chống nước IP68, pin 8000 mAh.",
  "image_url": "/products/galaxy-tab-s9-fe.jpg"
 },
 {
  "slug": "apple-watch-se-2",
  "name": "Apple Watch SE 2 GPS 40mm",
  "category": "dong-ho",
  "brand": "Apple",
  "price_vnd": 6290000,
  "old_price_vnd": 6990000,
  "rating": 4.6,
  "stock": 20,
  "specs": {
   "Kích thước": "40mm",
   "Kết nối": "GPS",
   "Chống nước": "50m",
   "Pin": "Đến 18 giờ"
  },
  "description": "Theo dõi sức khoẻ, phát hiện va chạm, thông báo thông minh.",
  "image_url": "/products/apple-watch-se-2.jpg"
 },
 {
  "slug": "xiaomi-smart-band-9",
  "name": "Xiaomi Smart Band 9",
  "category": "dong-ho",
  "brand": "Xiaomi",
  "price_vnd": 1090000,
  "old_price_vnd": 1290000,
  "rating": 4.4,
  "stock": 80,
  "specs": {
   "Màn hình": "1.62 inch AMOLED",
   "Pin": "Đến 21 ngày",
   "Chống nước": "5ATM"
  },
  "description": "Vòng đeo tay giá rẻ, theo dõi nhịp tim, SpO2 và giấc ngủ.",
  "image_url": "/products/xiaomi-smart-band-9.png"
 },
 {
  "slug": "airpods-pro-2-usb-c",
  "name": "Tai nghe AirPods Pro 2 USB-C",
  "category": "phu-kien",
  "brand": "Apple",
  "price_vnd": 5490000,
  "old_price_vnd": 6190000,
  "rating": 4.8,
  "stock": 35,
  "specs": {
   "Chống ồn": "ANC chủ động",
   "Chip": "H2",
   "Pin": "6 giờ (30 giờ cùng hộp)",
   "Sạc": "USB-C / MagSafe"
  },
  "description": "Chống ồn chủ động, âm thanh không gian, hộp sạc USB-C.",
  "image_url": "/products/airpods-pro-2-usb-c.jpg"
 },
 {
  "slug": "sony-wh-1000xm5",
  "name": "Tai nghe chụp tai Sony WH-1000XM5",
  "category": "phu-kien",
  "brand": "Sony",
  "price_vnd": 7490000,
  "old_price_vnd": 8990000,
  "rating": 4.7,
  "stock": 9,
  "specs": {
   "Chống ồn": "ANC",
   "Pin": "30 giờ (ANC bật) / 40 giờ",
   "Kết nối": "Bluetooth 5.2",
   "Sạc": "USB-C"
  },
  "description": "Chống ồn hàng đầu, đàm thoại rõ, đeo êm cả ngày.",
  "image_url": "/products/sony-wh-1000xm5.png"
 },
 {
  "slug": "anker-sac-20w",
  "name": "Củ sạc nhanh Anker 20W USB-C",
  "category": "phu-kien",
  "brand": "Anker",
  "price_vnd": 290000,
  "old_price_vnd": 390000,
  "rating": 4.6,
  "stock": 150,
  "specs": {
   "Công suất": "20W",
   "Cổng": "USB-C",
   "Bảo hành": "18 tháng"
  },
  "description": "Sạc nhanh iPhone và Android, nhỏ gọn, bảo vệ quá nhiệt.",
  "image_url": "/products/anker-sac-20w.png"
 },
 {
  "slug": "pin-du-phong-anker-10000",
  "name": "Pin dự phòng Anker 10000mAh",
  "category": "phu-kien",
  "brand": "Anker",
  "price_vnd": 690000,
  "old_price_vnd": 790000,
  "rating": 4.5,
  "stock": 60,
  "specs": {
   "Dung lượng": "10000 mAh",
   "Công suất": "22.5W",
   "Cổng": "USB-C + USB-A"
  },
  "description": "Pin dự phòng mỏng nhẹ, sạc nhanh 22.5W.",
  "image_url": "/products/pin-du-phong-anker-10000.jpg"
 }
]
''')


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE products (
            id            bigserial PRIMARY KEY,
            slug          text NOT NULL UNIQUE,
            name          text NOT NULL,
            category      text NOT NULL,
            brand         text NOT NULL,
            price_vnd     bigint NOT NULL CHECK (price_vnd >= 0),
            old_price_vnd bigint CHECK (old_price_vnd IS NULL OR old_price_vnd >= 0),
            rating        numeric(2, 1) NOT NULL DEFAULT 0 CHECK (rating BETWEEN 0 AND 5),
            stock         integer NOT NULL DEFAULT 0 CHECK (stock >= 0),
            specs         jsonb NOT NULL DEFAULT '{}'::jsonb,
            description   text NOT NULL DEFAULT '',
            image_url     text,
            created_at    timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX products_category_idx ON products (category)")
    insert = sa.text(
        """
        INSERT INTO products (slug, name, category, brand, price_vnd, old_price_vnd, rating, stock, specs, description, image_url)
        VALUES (:slug, :name, :category, :brand, :price_vnd, :old_price_vnd, :rating, :stock,
                CAST(:specs AS jsonb), :description, :image_url)
        ON CONFLICT (slug) DO NOTHING
        """
    )
    op.get_bind().execute(insert, [{**p, "specs": json.dumps(p["specs"], ensure_ascii=False)} for p in SEED_PRODUCTS])


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS products")
