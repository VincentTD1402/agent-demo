"""Lưu ảnh sản phẩm do nhân viên tải lên. nginx phục vụ thư mục này ở đường dẫn /uploads/products/."""

import logging
import os
import secrets
from pathlib import Path

from app.shop.common import ShopError

logger = logging.getLogger(__name__)
URL_PREFIX = "/uploads/products/"


def detect_extension(data: bytes) -> str | None:
    """Phần mở rộng theo chữ ký file (không tin tên file/Content-Type do client gửi); None nếu không phải ảnh hỗ trợ."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def save_image(directory: Path, slug: str, data: bytes) -> str:
    """Ghi ảnh với tên ngẫu nhiên và trả về URL công khai. `slug` đã được kiểm tra định dạng nên an toàn làm tên file."""
    extension = detect_extension(data)
    if extension is None:
        raise ShopError("Chỉ nhận ảnh PNG, JPG hoặc WEBP")
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{slug}-{secrets.token_hex(4)}.{extension}"
    temp = directory / f".{name}.tmp"
    temp.write_bytes(data)
    os.replace(temp, directory / name)  # ghi xong mới lộ ra: nginx không bao giờ trả file dở dang
    return URL_PREFIX + name


def delete_uploaded(directory: Path, url: str | None) -> None:
    """Xoá file ảnh cũ nếu URL trỏ vào thư mục tải lên (ảnh có sẵn trong frontend/public hay URL ngoài thì giữ nguyên)."""
    if not url or not url.startswith(URL_PREFIX):
        return
    path = directory / url[len(URL_PREFIX):]
    try:
        if path.resolve().parent == directory.resolve():
            path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Không xoá được ảnh cũ %s", path.name)
