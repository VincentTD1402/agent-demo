"""Client embedding tới endpoint tương thích OpenAI (`POST {base_url}/embeddings`) có timeout rõ ràng.

Tài liệu/sản phẩm được embed nguyên văn; truy vấn tìm kiếm của Qwen3-Embedding phải có tiền tố
`Instruct: ...\\nQuery: ...` (thuộc phần truy vấn ở API, không dùng ở đây).
"""
from typing import Protocol

import httpx


class EmbeddingError(Exception):
    """Endpoint lỗi, hết thời gian hoặc trả dữ liệu sai hình dạng. Thông báo không chứa khoá API."""


class EmbeddingClient(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HttpEmbeddingClient:
    def __init__(
        self, base_url: str, model: str, dims: int, timeout_s: float, api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,  # chỉ để test thay lớp mạng; mặc định dùng HTTP thật
    ):
        self._url = base_url.rstrip("/") + "/embeddings"
        self._model = model
        self._dims = dims
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(timeout=httpx.Timeout(timeout_s), transport=transport)

    def close(self) -> None:
        self._http.close()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._http.post(
                self._url, json={"model": self._model, "input": texts}, headers=self._headers
            )
            response.raise_for_status()
            data = response.json()["data"]
            vectors = [item["embedding"] for item in sorted(data, key=lambda item: item["index"])]
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            # Chỉ nêu loại lỗi: URL/header có thể chứa thông tin nhạy cảm
            raise EmbeddingError(f"Gọi endpoint embedding thất bại ({type(exc).__name__})") from None
        if len(vectors) != len(texts) or any(len(v) != self._dims for v in vectors):
            raise EmbeddingError(f"Endpoint embedding trả số vector/số chiều không khớp (cần {self._dims} chiều)")
        return vectors
