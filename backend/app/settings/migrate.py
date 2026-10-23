"""Cấu hình của bước migrate/bootstrap (chạy một lần, là tiến trình duy nhất có quyền DDL)."""
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.settings.secret_checks import require_dsn_safe_identifier, require_dsn_safe_password

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

    # Kích thước vector của bảng store LangGraph
    embedding_dims: int = Field(default=1024, ge=1)
    # Nạp sản phẩm/đơn mẫu khi bảng còn trống: chỉ cho dev, mặc định tắt
    seed_demo_data: bool = False
    log_level: str = "INFO"

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
