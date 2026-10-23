"""Mã hoá cấp ứng dụng cho `refunds.payout_info_enc` (Fernet, khoá `PAYOUT_ENCRYPTION_KEY`).

Chưa có nơi nào giải mã: chỉ luồng chi trả của staff/admin được gọi `decrypt_payout_info`. Không log/trace
plaintext hay token.
"""
from cryptography.fernet import Fernet, InvalidToken


class PayoutDecryptionError(Exception):
    """Token sai khoá hoặc bị sửa. Thông báo cố ý không chứa dữ liệu."""


def encrypt_payout_info(key: str, plaintext: str) -> bytes:
    return Fernet(key.encode()).encrypt(plaintext.encode("utf-8"))


def decrypt_payout_info(key: str, token: bytes) -> str:
    try:
        return Fernet(key.encode()).decrypt(bytes(token)).decode("utf-8")
    except InvalidToken:
        raise PayoutDecryptionError("payout_info_enc không giải mã được (sai khoá hoặc dữ liệu hỏng)") from None
