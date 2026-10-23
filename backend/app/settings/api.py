"""Cấu hình của tiến trình API (kết nối bằng role `app`, không có quyền DDL)."""
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.settings.secret_checks import require_fernet_key


class ApiSettings(BaseSettings):
    # hide_input_in_errors: khoá Fernet gõ sai không bị in lại trong ValidationError/log
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    # Mô hình chat tự host (API tương thích OpenAI)
    llm_base_url: str
    llm_api_key: str = "not-needed"
    llm_model: str
    llm_temperature: float = 0.0
    llm_timeout_s: float = 60.0

    # Mô hình embedding tự host; để trống base_url/api_key thì dùng lại cấu hình LLM
    embedding_model: str
    embedding_dims: int = 1024
    embedding_base_url: str = ""
    embedding_api_key: str = ""

    # DSN của role `app` (DML, không DDL)
    database_url: str
    mcp_server_url: str = "http://mcp-server:8001/mcp"

    api_key: str = ""
    cors_origins: str = "http://localhost:3000"
    agent_max_steps: int = Field(default=12, ge=2, le=50)
    log_level: str = "INFO"

    # Khoá Fernet mã hoá thông tin nhận tiền hoàn; thiếu/sai thì API không khởi động
    payout_encryption_key: SecretStr
    shipping_fee_vnd: int = Field(default=30000, ge=0)
    free_shipping_from_vnd: int = Field(default=500000, ge=0)
    refund_window_days: int = Field(default=7, ge=1)

    # Kích thước pool (xem connection_budget): pool psycopg truy vấn thô, pool SQLAlchemy, pool LangGraph
    db_pool_max: int = Field(default=5, ge=1)
    sa_pool_size: int = Field(default=5, ge=1)
    sa_max_overflow: int = Field(default=2, ge=0)
    langgraph_pool_max: int = Field(default=5, ge=1)

    @field_validator("payout_encryption_key")
    @classmethod
    def _valid_payout_key(cls, v: SecretStr) -> SecretStr:
        require_fernet_key(v.get_secret_value(), "PAYOUT_ENCRYPTION_KEY")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_connections(self) -> int:
        """Số kết nối Postgres tối đa mà một replica API có thể giữ cùng lúc."""
        return self.db_pool_max + self.sa_pool_size + self.sa_max_overflow + self.langgraph_pool_max


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()  # type: ignore[call-arg]
