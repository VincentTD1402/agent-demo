"""Cấu hình theo tiến trình: thiếu hoặc secret yếu thì không khởi động (không cần Postgres)."""
import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.settings.api import ApiSettings
from app.settings.mcp import McpSettings
from app.settings.migrate import ROLE_MIGRATOR, MigrateSettings

API_KWARGS = dict(
    _env_file=None, llm_base_url="http://x/v1", llm_model="m", embedding_model="e",
    database_url="postgresql://u:p@h/d",
)


def _migrate(**over):
    base = dict(
        _env_file=None, bootstrap_database_url="postgresql://postgres:s@db:5432/shop",
        migrator_db_password="MigratorStrong1", app_db_password="AppStrong123456", mcp_db_password="McpStrong123456",
    )
    return MigrateSettings(**{**base, **over})


def _secret_not_leaked(exc: ValidationError, secret: str) -> None:
    assert secret not in str(exc)
    # .errors() mặc định vẫn trả `input` cho code gọi trực tiếp; log/traceback dùng str(exc) nên mới là bề mặt rò rỉ
    assert secret not in repr(exc.errors(include_input=False))


def test_api_requires_valid_payout_key():
    with pytest.raises(ValidationError):
        ApiSettings(**API_KWARGS)  # thiếu khoá
    with pytest.raises(ValidationError):
        ApiSettings(**API_KWARGS, payout_encryption_key="not-a-fernet-key")
    s = ApiSettings(**API_KWARGS, payout_encryption_key=Fernet.generate_key().decode())
    assert (s.shipping_fee_vnd, s.free_shipping_from_vnd, s.refund_window_days) == (30000, 500000, 7)
    assert s.max_connections == 5 + 5 + 2 + 5


@pytest.mark.parametrize(
    "password",
    ["short", "change-me-migrator-password", "Password12345678", "ab/cd#ef1234567", "has space 123456", "dash-in-pass-1234", "$ecretpass123456"],
)
def test_migrate_rejects_weak_placeholder_or_non_alphanumeric_passwords(password):
    with pytest.raises(ValidationError) as exc:
        _migrate(app_db_password=password)
    _secret_not_leaked(exc.value, password)


def test_migrate_rejects_duplicate_role_passwords_and_superuser_reuse():
    with pytest.raises(ValidationError, match="trùng"):
        _migrate(mcp_db_password="AppStrong123456")
    with pytest.raises(ValidationError, match="trùng") as exc:
        _migrate(bootstrap_database_url="postgresql://postgres:McpStrong123456@db:5432/shop")
    _secret_not_leaked(exc.value, "McpStrong123456")


def test_migrate_validates_components_forwarded_by_compose():
    _migrate(postgres_user="shopbot", postgres_password="SuperuserPass0123", postgres_db="shop_db")
    for bad in ({"postgres_password": "abc/def#ghi12345"}, {"postgres_user": "a:b"}, {"postgres_db": "x/y"}):
        with pytest.raises(ValidationError) as exc:
            _migrate(**bad)
        _secret_not_leaked(exc.value, next(iter(bad.values())))


def test_migrate_seed_is_off_by_default():
    assert _migrate().seed_demo_data is False


def test_rejected_api_secret_is_not_echoed():
    bad_key = "typo-fernet-key-SENSITIVE"
    with pytest.raises(ValidationError) as exc:
        ApiSettings(**API_KWARGS, payout_encryption_key=bad_key)
    _secret_not_leaked(exc.value, bad_key)


def test_rejected_value_never_reaches_bootstrap_log(monkeypatch, tmp_path, caplog):
    """bootstrap.main() ghi log.exception khi cấu hình sai: secret bị từ chối không được nằm trong log."""
    from app.db import bootstrap

    secret = "sh0rtSECRET"
    monkeypatch.chdir(tmp_path)  # không để pydantic đọc .env thật của repo
    for key, value in {
        "BOOTSTRAP_DATABASE_URL": "postgresql://postgres:SuperuserPass0123@db:5432/shop",
        "MIGRATOR_DB_PASSWORD": "MigratorStrong1",
        "APP_DB_PASSWORD": secret,
        "MCP_DB_PASSWORD": "McpStrong123456",
    }.items():
        monkeypatch.setenv(key, value)
    with caplog.at_level("DEBUG"):
        assert bootstrap.main() == 1
    assert "APP_DB_PASSWORD" in caplog.text, "lỗi phải nêu tên biến để operator sửa"
    assert secret not in caplog.text


def test_migrate_derives_role_dsn_and_database_name():
    s = _migrate()
    assert s.database_name == "shop"
    assert s.migrator_database_url.startswith(f"postgresql://{ROLE_MIGRATOR}:MigratorStrong1@db:5432/shop")


def test_mcp_requires_database_url():
    with pytest.raises(ValidationError):
        McpSettings(_env_file=None)
