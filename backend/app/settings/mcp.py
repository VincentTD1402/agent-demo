"""Cấu hình của tiến trình MCP server (kết nối bằng role `mcp`, quyền tối thiểu)."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class McpSettings(BaseSettings):
    # hide_input_in_errors: DSN (có mật khẩu) bị từ chối không bị in lại trong ValidationError/log
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str
    mcp_host: str = "127.0.0.1"
    mcp_port: int = Field(default=8001, ge=1, le=65535)
    log_level: str = "INFO"
    db_pool_max: int = Field(default=5, ge=1)

    @property
    def max_connections(self) -> int:
        return self.db_pool_max


@lru_cache
def get_mcp_settings() -> McpSettings:
    return McpSettings()  # type: ignore[call-arg]
