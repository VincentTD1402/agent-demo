"""Cấu hình ứng dụng đọc từ biến môi trường / file .env."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

    database_url: str
    mcp_server_url: str = "http://mcp-server:8001/mcp"

    api_key: str = ""
    cors_origins: str = "http://localhost:3000"
    agent_max_steps: int = Field(default=12, ge=2, le=50)
    log_level: str = "INFO"
    # Nạp sản phẩm/đơn mẫu khi bảng còn trống (tắt ở production)
    seed_demo_data: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
