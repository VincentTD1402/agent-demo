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

    # LLM tự host (API tương thích OpenAI): gọi POST {llm_api_url}/chat/completions
    llm_api_url: str
    llm_model_name: str
    llm_api_key: str = "not-needed"
    llm_max_tokens: int = Field(default=1024, ge=64)
    llm_timeout: float = 60.0

    # Reranker (Qwen3-Reranker): gọi POST {reranker_api_url}/rerank
    reranker_api_url: str
    reranker_model_name: str
    reranker_timeout_s: float = 30.0

    # RAG: lấy rag_top_k đoạn gần nhất bằng vector, rerank rồi giữ tối đa rag_top_n đoạn có điểm >= rag_min_score
    rag_top_k: int = Field(default=10, ge=1)
    rag_top_n: int = Field(default=4, ge=1)
    rag_min_score: float = Field(default=0.3, ge=0, le=1)
    # Câu trả lời dựa trên tài liệu nên để nhiệt độ thấp (LLM_TEMPERATURE chung dành cho chat tự do)
    rag_answer_temperature: float = Field(default=0.2, ge=0, le=2)
    # Quá ngưỡng này thì tóm tắt phần cũ của hội thoại, chỉ giữ rag_keep_messages tin nhắn gần nhất
    rag_summarize_after: int = Field(default=12, ge=4)
    rag_keep_messages: int = Field(default=6, ge=2)

    # Chính sách cửa hàng (phải khớp tài liệu trong documents/policies và nội dung hiển thị trên UI)
    shipping_fee_vnd: int = Field(default=30000, ge=0)
    free_shipping_from_vnd: int = Field(default=500000, ge=0)
    refund_window_days: int = Field(default=7, ge=1)  # tính từ ngày giao hàng
    max_qty_per_line: int = Field(default=10, ge=1, le=10)  # cột carts.qty có CHECK <= 10

    # Chống dò tìm/lạm dụng: tra cứu đơn sai quá số lần theo mã đơn hoặc SĐT thì khoá tạm; giới hạn số đơn mỗi phiên
    lookup_max_failures_per_code: int = Field(default=5, ge=1)
    lookup_max_failures_per_phone: int = Field(default=10, ge=1)
    lookup_window_minutes: int = Field(default=15, ge=1)
    max_orders_per_session_per_hour: int = Field(default=5, ge=1)

    # Giới hạn tần suất chat (theo phiên và theo IP) để chống spam; tin lặp lại quá chat_duplicate_limit lần/phút bị chặn
    chat_rate_per_minute: int = Field(default=10, ge=1)
    chat_rate_per_hour: int = Field(default=120, ge=1)
    chat_rate_per_ip_per_minute: int = Field(default=30, ge=1)
    chat_duplicate_limit: int = Field(default=3, ge=1)

    # MCP server (tool giỏ hàng/đơn/hoàn tiền): agent gọi qua HTTP nội bộ với Bearer key.
    # Key rỗng thì MCP server từ chối khởi động và agent tắt nhánh tool.
    mcp_server_url: str = "http://mcp-server:8001/mcp"
    mcp_api_key: str = ""
    mcp_port: int = 8001

    # Khoá cho API nhân viên (duyệt hoàn tiền, cập nhật trạng thái đơn); để trống = tắt các endpoint này
    staff_api_key: str = ""

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
