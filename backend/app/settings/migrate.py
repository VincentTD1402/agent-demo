"""Cấu hình của bước migrate/bootstrap (chạy một lần, là tiến trình duy nhất có quyền DDL)."""
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.settings.fixed_embedding_dims import require_fixed_embedding_dims
from app.settings.secret_checks import (
    require_dsn_safe_identifier, require_dsn_safe_password, require_strong_secret,
)

ROLE_MIGRATOR = "shopbot_migrator"
ROLE_APP = "shopbot_app"
ROLE_MCP = "shopbot_mcp"


class MigrateSettings(BaseSettings):
    # hide_input_in_errors: ValidationError không in lại giá trị bị từ chối (secret không lọt vào log)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    # DSN superuser: chỉ dùng ở bước đầu của bootstrap (CREATE EXTENSION vector, tạo role)
    bootstrap_database_url: str
    migrator_db_password: SecretStr
    app_db_password: SecretStr
    mcp_db_password: SecretStr

    # Các thành phần docker-compose ghép vào BOOTSTRAP_DATABASE_URL; compose chuyển tiếp để kiểm tra ký tự
    # (không mã hoá %, nên ký tự đặc biệt làm URL sai). Bỏ trống khi chạy ngoài compose.
    postgres_user: str | None = None
    postgres_password: SecretStr | None = None
    postgres_db: str | None = None

    # Kích thước vector của bảng store LangGraph và cột embedding
    embedding_dims: int = 1024
    # Cho phép revision 0004/0005 xoá đơn/hoàn tiền cũ (dữ liệu dạng trước Alembic); mặc định từ chối nếu có dòng.
    # Bootstrap chuyển thành `alembic -x allow_destroy_legacy_orders=true`. Chỉ bật có chủ đích trên DB dev.
    allow_destroy_legacy_orders: bool = False
    # Nạp sản phẩm/đơn/KB mẫu khi bảng còn trống: chỉ cho dev, mặc định tắt
    seed_demo_data: bool = False
    # Tài khoản staff demo chỉ được tạo khi ENV=dev và có mật khẩu (không có mật khẩu mặc định)
    env: str = "production"
    staff_demo_password: SecretStr | None = None
    # Số liệu chính sách ghi vào KB mẫu: cùng nguồn cấu hình với API
    shipping_fee_vnd: int = Field(default=30000, ge=0)
    free_shipping_from_vnd: int = Field(default=500000, ge=0)
    refund_window_days: int = Field(default=7, ge=1)
    # `python -m app.kb.reindex` (chạy riêng, không thuộc cổng migrate); base_url trống thì reindex báo lỗi rõ ràng
    embedding_model: str = ""
    embedding_base_url: str = ""
    embedding_api_key: SecretStr | None = None
    embedding_timeout_s: float = Field(default=30.0, gt=0)
    log_level: str = "INFO"

    @field_validator("embedding_dims")
    @classmethod
    def _fixed_embedding_dims(cls, v: int) -> int:
        return require_fixed_embedding_dims(v)

    @field_validator("staff_demo_password", mode="before")
    @classmethod
    def _blank_staff_demo_password_is_unset(cls, v):
        """compose chuyển biến trống thành chuỗi rỗng: coi như chưa đặt."""
        return v or None

    @field_validator("staff_demo_password")
    @classmethod
    def _strong_staff_demo_password(cls, v: SecretStr | None) -> SecretStr | None:
        if v is not None:
            require_strong_secret(v.get_secret_value(), "STAFF_DEMO_PASSWORD")
        return v

    @field_validator("migrator_db_password", "app_db_password", "mcp_db_password", "postgres_password")
    @classmethod
    def _dsn_safe_password(cls, v: SecretStr | None, info) -> SecretStr | None:
        if v is not None:
            require_dsn_safe_password(v.get_secret_value(), info.field_name.upper())
        return v

    @field_validator("postgres_user", "postgres_db")
    @classmethod
    def _dsn_safe_identifier(cls, v: str | None, info) -> str | None:
        if v is not None:
            require_dsn_safe_identifier(v, info.field_name.upper())
        return v

    @model_validator(mode="after")
    def _passwords_distinct(self) -> "MigrateSettings":
        """Ba role dùng chung mật khẩu (hoặc trùng superuser mà migrate nhìn thấy) làm mất phân quyền tối thiểu."""
        passwords = {
            "MIGRATOR_DB_PASSWORD": self.migrator_db_password.get_secret_value(),
            "APP_DB_PASSWORD": self.app_db_password.get_secret_value(),
            "MCP_DB_PASSWORD": self.mcp_db_password.get_secret_value(),
        }
        superuser = make_url(self.bootstrap_database_url).password
        if superuser:
            passwords["mật khẩu superuser (POSTGRES_PASSWORD/BOOTSTRAP_DATABASE_URL)"] = superuser
        seen: dict[str, str] = {}
        for name, value in passwords.items():
            if value in seen:
                raise ValueError(f"{name} trùng với {seen[value]}: mỗi role phải có mật khẩu riêng")
            seen[value] = name
        return self

    def _url_for(self, role: str, password: SecretStr) -> str:
        url = make_url(self.bootstrap_database_url).set(username=role, password=password.get_secret_value())
        return url.render_as_string(hide_password=False)

    @property
    def migrator_database_url(self) -> str:
        return self._url_for(ROLE_MIGRATOR, self.migrator_db_password)

    @property
    def database_name(self) -> str:
        name = make_url(self.bootstrap_database_url).database
        if not name:
            raise ValueError("BOOTSTRAP_DATABASE_URL phải chỉ rõ tên database")
        return name
