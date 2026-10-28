"""Lưu/xoá ảnh sản phẩm tải lên: nhận diện theo chữ ký file, tên ngẫu nhiên, chỉ xoá trong thư mục tải lên. Không cần DB."""

import pytest

from app.products import images
from app.shop.common import ShopError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 8


@pytest.mark.parametrize(("data", "ext"), [(PNG, "png"), (JPG, "jpg"), (WEBP, "webp")])
def test_detects_supported_formats_by_signature(data, ext):
    assert images.detect_extension(data) == ext


@pytest.mark.parametrize("data", [b"", b"GIF89a....", b"<svg onload=alert(1)>", b"%PDF-1.4", b"MZ\x90\x00", b"RIFF\x00\x00\x00\x00WAVE"])
def test_rejects_non_images_even_if_named_like_one(data):
    assert images.detect_extension(data) is None
    with pytest.raises(ShopError, match="PNG, JPG"):
        images.save_image(__import__("pathlib").Path("unused"), "x", data)


def test_save_returns_public_url_with_random_name_and_leaves_no_temp_file(tmp_path):
    first = images.save_image(tmp_path / "products", "iphone-16", PNG)
    second = images.save_image(tmp_path / "products", "iphone-16", PNG)
    assert first.startswith("/uploads/products/iphone-16-") and first.endswith(".png") and first != second
    names = sorted(p.name for p in (tmp_path / "products").iterdir())
    assert names == sorted([first.rsplit("/", 1)[1], second.rsplit("/", 1)[1]])  # không còn file .tmp


def test_delete_only_removes_files_inside_the_upload_directory(tmp_path):
    directory = tmp_path / "products"
    url = images.save_image(directory, "a", JPG)
    outside = tmp_path / "keep.txt"
    outside.write_text("giữ")
    images.delete_uploaded(directory, "/uploads/products/../../keep.txt")  # cố thoát khỏi thư mục
    images.delete_uploaded(directory, "/products/iphone-16-128gb.jpg")  # ảnh có sẵn của frontend: không động tới
    images.delete_uploaded(directory, "https://cdn.example.com/x.jpg")
    images.delete_uploaded(directory, None)
    assert outside.exists() and len(list(directory.iterdir())) == 1
    images.delete_uploaded(directory, url)
    assert list(directory.iterdir()) == []
