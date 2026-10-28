"""Cấu hình đọc từ biến môi trường (cùng tên với .env.example)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Cột chunks.embedding là vector(1024) (Qwen3-Embedding-0.6B); đổi số chiều cần migration riêng.
EMBEDDING_DIMS = 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_pool_size: int = Field(default=5, ge=1)

    # Endpoint tương thích OpenAI: client gọi POST {embedding_api_url}/embeddings
    embedding_api_url: str
    embedding_model_name: str
    embedding_api_key: str = ""
    embedding_chunk_size: int = Field(default=1000, ge=100)
    embedding_chunk_overlap: int = Field(default=200, ge=0)
    embedding_batch_size: int = Field(default=10, ge=1)
    embedding_timeout_s: float = 60.0

    # Thư mục gốc được phép nạp theo folder; request không thể trỏ ra ngoài thư mục này
    documents_dir: str = "documents"
    max_upload_mb: int = Field(default=20, ge=1)
    max_concurrent_uploads: int = Field(default=3, ge=1)

    # Để trống = không kiểm tra (chạy local). Có giá trị thì mọi request nạp tài liệu phải gửi X-API-Key.
    api_key: str = ""

    @property
    def database_dsn(self) -> str:
        # conninfo dạng key=value: psycopg tự xử lý ký tự đặc biệt trong mật khẩu khi được trích dấu nháy
        password = self.postgres_password.replace("\\", "\\\\").replace("'", "\\'")
        return (
            f"host={self.postgres_host} port={self.postgres_port} dbname={self.postgres_db} "
            f"user={self.postgres_user} password='{password}'"
        )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
