"""Mã hoá thông tin nhận tiền: round-trip, không lộ plaintext, sai khoá/dữ liệu hỏng thì lỗi không chứa dữ liệu."""
import pytest
from cryptography.fernet import Fernet

from app.security.payout_encryption import PayoutDecryptionError, decrypt_payout_info, encrypt_payout_info

PAYOUT = "Vietcombank | 0123456789 | NGUYEN VAN A"


def test_round_trip_preserves_unicode():
    key = Fernet.generate_key().decode()
    text = PAYOUT + " (Nguyễn Văn Á)"
    assert decrypt_payout_info(key, encrypt_payout_info(key, text)) == text


def test_ciphertext_is_bytes_without_plaintext_and_differs_per_call():
    key = Fernet.generate_key().decode()
    first, second = encrypt_payout_info(key, PAYOUT), encrypt_payout_info(key, PAYOUT)
    assert isinstance(first, bytes) and b"0123456789" not in first and PAYOUT.encode() not in first
    assert first != second  # IV ngẫu nhiên: cùng đầu vào không cho cùng bản mã


def test_wrong_key_fails_without_leaking_data():
    token = encrypt_payout_info(Fernet.generate_key().decode(), PAYOUT)
    with pytest.raises(PayoutDecryptionError) as exc:
        decrypt_payout_info(Fernet.generate_key().decode(), token)
    assert "0123456789" not in str(exc.value)


def test_tampered_token_fails():
    key = Fernet.generate_key().decode()
    token = bytearray(encrypt_payout_info(key, PAYOUT))
    token[20] ^= 0x01
    with pytest.raises(PayoutDecryptionError):
        decrypt_payout_info(key, bytes(token))


def test_memoryview_from_database_driver_is_accepted():
    key = Fernet.generate_key().decode()
    token = encrypt_payout_info(key, PAYOUT)
    assert decrypt_payout_info(key, memoryview(token)) == PAYOUT  # psycopg trả bytea có thể là memoryview


def test_invalid_key_is_rejected():
    with pytest.raises(ValueError):
        encrypt_payout_info("not-a-fernet-key", PAYOUT)
