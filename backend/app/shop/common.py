"""Lỗi nghiệp vụ, chính sách cửa hàng và các hàm chuẩn hoá dùng chung cho giỏ hàng/đơn hàng/hoàn tiền."""

import re
from dataclasses import dataclass
from datetime import datetime

from app.settings import Settings


class ShopError(Exception):
    """Lỗi nghiệp vụ có thông điệp tiếng Việt an toàn để hiển thị cho khách (agent đọc và diễn đạt lại)."""


@dataclass(frozen=True)
class ShopPolicy:
    shipping_fee_vnd: int
    free_shipping_from_vnd: int
    refund_window_days: int
    max_qty_per_line: int

    @classmethod
    def from_settings(cls, s: Settings) -> "ShopPolicy":
        return cls(s.shipping_fee_vnd, s.free_shipping_from_vnd, s.refund_window_days, s.max_qty_per_line)

    def shipping_fee(self, subtotal_vnd: int) -> int:
        return 0 if subtotal_vnd >= self.free_shipping_from_vnd else self.shipping_fee_vnd


_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_PHONE = re.compile(r"^0\d{9}$")


def check_session_id(session_id: str) -> str:
    # session_id là khoá truy cập giỏ hàng: bắt buộc đủ dài để không đoán được
    if not _SESSION_ID.match(session_id or ""):
        raise ShopError("Phiên làm việc không hợp lệ")
    return session_id


def normalize_phone(raw: str) -> str:
    """'+84 912 345 678' / '84912345678' / '0912.345.678' -> '0912345678'; sai định dạng thì ShopError."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("84") and len(digits) == 11:
        digits = "0" + digits[2:]
    if not _PHONE.match(digits):
        raise ShopError("Số điện thoại không hợp lệ (cần 10 chữ số, bắt đầu bằng 0)")
    return digits


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
