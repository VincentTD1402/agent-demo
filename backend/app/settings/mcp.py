"""Cấu hình của tiến trình MCP server (kết nối bằng role `mcp`, quyền tối thiểu)."""
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.settings.fixed_embedding_dims import require_fixed_embedding_dims


class McpSettings(BaseSettings):
    # hide_input_in_errors: DSN (có mật khẩu) bị từ chối không bị in lại trong ValidationError/log
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str
    mcp_host: str = "127.0.0.1"
    mcp_port: int = Field(default=8001, ge=1, le=65535)
    log_level: str = "INFO"
    db_pool_max: int = Field(default=5, ge=1)
    # Hạn hoàn tiền (ngày, tính từ delivered_at): cùng nguồn cấu hình với API
    refund_window_days: int = Field(default=7, ge=1)
    # Chỉ để phát hiện cấu hình lệch: schema cố định 1024 chiều
    embedding_dims: int = 1024

    @field_validator("embedding_dims")
    @classmethod
    def _fixed_embedding_dims(cls, v: int) -> int:
        return require_fixed_embedding_dims(v)

    @property
    def max_connections(self) -> int:
        return self.db_pool_max


@lru_cache
def get_mcp_settings() -> McpSettings:
    return McpSettings()  # type: ignore[call-arg]
