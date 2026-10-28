"""API quản trị sản phẩm cho nhân viên (header X-Staff-Key): xem tất cả, thêm, sửa, xoá, tải ảnh."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, UploadFile
from pydantic import BaseModel, Field, field_validator, model_validator

from app.api_key_auth import require_staff
from app.products import images
from app.products.admin import CATEGORIES, ProductAdminService
from app.products.router import ProductOut
from app.settings import Settings, get_settings
from app.shop.common import ShopError

router = APIRouter(prefix="/staff/products", tags=["staff-products"], dependencies=[Depends(require_staff)])

Category = Literal[CATEGORIES]  # type: ignore[valid-type]


class ProductIn(BaseModel):
    """Các trường chủ shop chỉnh được (giá trị đầy đủ, không cập nhật từng phần)."""

    name: str = Field(min_length=2, max_length=200)
    category: Category
    brand: str = Field(min_length=1, max_length=80)
    price_vnd: int = Field(ge=0, le=1_000_000_000)
    old_price_vnd: int | None = Field(default=None, ge=0, le=1_000_000_000, description="Giá gốc gạch ngang; để trống nếu không giảm giá")
    stock: int = Field(ge=0, le=100_000)
    rating: float = Field(default=0, ge=0, le=5)
    specs: dict[str, str] = Field(default_factory=dict)
    description: str = Field(default="", max_length=5000)
    image_url: str | None = Field(default=None, max_length=500)

    @field_validator("specs")
    @classmethod
    def _specs_limits(cls, specs: dict[str, str]) -> dict[str, str]:
        if len(specs) > 30 or any(not 1 <= len(k) <= 60 or not 1 <= len(v) <= 200 for k, v in specs.items()):
            raise ValueError("Thông số tối đa 30 dòng; tên 1-60 ký tự, giá trị 1-200 ký tự")
        return specs

    @field_validator("image_url")
    @classmethod
    def _image_url_safe(cls, url: str | None) -> str | None:
        # Chỉ nhận đường dẫn nội bộ (ảnh tải lên hoặc có sẵn) hoặc https; chặn javascript:, data:, //host
        if url and not ((url.startswith("/") and not url.startswith("//")) or url.startswith("https://")):
            raise ValueError("image_url phải là đường dẫn bắt đầu bằng / hoặc https://")
        return url or None

    @model_validator(mode="after")
    def _old_price_above_price(self) -> "ProductIn":
        if self.old_price_vnd is not None and self.old_price_vnd <= self.price_vnd:
            raise ValueError("Giá gốc phải lớn hơn giá bán (hoặc để trống nếu không giảm giá)")
        return self


class ProductCreateIn(ProductIn):
    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80, description="Mã dùng trong đường dẫn, không đổi được sau khi tạo")


def get_admin(request: Request) -> ProductAdminService:
    return request.app.state.product_admin


def _images_dir(settings: Settings) -> Path:
    return Path(settings.product_images_dir)


@router.get("", response_model=list[ProductOut])
def list_all(request: Request, q: str | None = Query(default=None, max_length=100), category: str | None = Query(default=None, max_length=50)) -> list[dict]:
    return request.app.state.product_repo.search(q, category, 200)  # kể cả sản phẩm hết hàng


@router.post("", response_model=ProductOut, status_code=201)
def create_product(body: ProductCreateIn, admin: ProductAdminService = Depends(get_admin)) -> dict:
    data = body.model_dump(exclude={"slug"})
    return admin.create(body.slug, data)


@router.put("/{slug}", response_model=ProductOut)
def update_product(slug: str, body: ProductIn, admin: ProductAdminService = Depends(get_admin)) -> dict:
    return admin.update(slug, body.model_dump())


@router.delete("/{slug}")
def delete_product(slug: str, admin: ProductAdminService = Depends(get_admin), settings: Settings = Depends(get_settings)) -> dict[str, str]:
    images.delete_uploaded(_images_dir(settings), admin.delete(slug))
    return {"deleted": slug}


@router.post("/{slug}/image", response_model=ProductOut)
def upload_image(
    slug: str, file: UploadFile, admin: ProductAdminService = Depends(get_admin), settings: Settings = Depends(get_settings)
) -> dict:
    # Đọc tối đa max+1 byte: đủ để phát hiện file quá lớn mà không nạp cả file vào RAM
    data = file.file.read(settings.max_product_image_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_product_image_mb * 1024 * 1024:
        raise ShopError(f"Ảnh lớn hơn {settings.max_product_image_mb} MB")
    directory = _images_dir(settings)
    url = images.save_image(directory, slug, data)
    try:
        product, old_url = admin.set_image(slug, url)
    except ShopError:
        images.delete_uploaded(directory, url)  # sản phẩm không tồn tại: không để file mồ côi
        raise
    images.delete_uploaded(directory, old_url)
    return product
