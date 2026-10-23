"""Kiểm tra secret lúc khởi động: thiếu hoặc yếu thì tiến trình không được chạy."""
import re

from cryptography.fernet import Fernet

MIN_SECRET_LENGTH = 12
# Giá trị mẫu trong .env.example; dùng nguyên văn là chưa đổi secret
_PLACEHOLDER_PREFIXES = ("change", "changeme", "password", "secret")
# Mật khẩu được nhúng thẳng vào URL kết nối (docker-compose, không mã hoá %): chỉ chữ-số
_DSN_SAFE_PASSWORD = re.compile(rf"[A-Za-z0-9]{{{MIN_SECRET_LENGTH},}}")
_DSN_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9_]+")


def require_strong_secret(value: str, name: str) -> str:
    """Thông báo lỗi không bao giờ chứa giá trị gốc (secret không được lọt vào log)."""
    if len(value) < MIN_SECRET_LENGTH:
        raise ValueError(f"{name} quá ngắn (tối thiểu {MIN_SECRET_LENGTH} ký tự)")
    if value.lower().startswith(_PLACEHOLDER_PREFIXES):
        raise ValueError(f"{name} vẫn là giá trị mẫu, hãy đặt secret ngẫu nhiên")
    return value


def require_dsn_safe_password(value: str, name: str) -> str:
    """Mật khẩu role DB: >= 12 ký tự và chỉ chữ-số, để ghép vào URL không cần mã hoá."""
    require_strong_secret(value, name)
    if not _DSN_SAFE_PASSWORD.fullmatch(value):
        raise ValueError(f"{name} chỉ được gồm chữ và số (A-Z, a-z, 0-9), vì được nhúng vào URL kết nối")
    return value


def require_dsn_safe_identifier(value: str, name: str) -> str:
    if not _DSN_SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} chỉ được gồm chữ, số và dấu gạch dưới, vì được nhúng vào URL kết nối")
    return value


def require_fernet_key(value: str, name: str) -> str:
    """Khoá Fernet hợp lệ = 32 byte base64 url-safe (sinh bằng Fernet.generate_key())."""
    try:
        Fernet(value.encode())
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} không phải khoá Fernet hợp lệ") from exc
    return value
