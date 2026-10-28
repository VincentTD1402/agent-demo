"""Client embedding tới endpoint tương thích OpenAI (`POST .../embeddings`), gửi theo batch."""

from typing import Protocol

import httpx


class EmbeddingError(Exception):
    """Endpoint lỗi, hết thời gian hoặc trả dữ liệu sai hình dạng. Thông báo không chứa URL/khoá API."""


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HttpEmbedder:
    def __init__(
        self, base_url: str, model: str, dims: int, batch_size: int, timeout_s: float, api_key: str = ""
    ):
        # .env.example có cả dạng base (.../v1) lẫn dạng đầy đủ (.../v1/embeddings)
        url = base_url.rstrip("/")
        self._url = url if url.endswith("/embeddings") else url + "/embeddings"
        self._model = model
        self._dims = dims
        self._batch_size = batch_size
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(timeout=httpx.Timeout(timeout_s))

    def close(self) -> None:
        self._http.close()

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(self._embed_batch(texts[start : start + self._batch_size]))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        try:
            response = self._http.post(
                self._url, json={"model": self._model, "input": batch}, headers=self._headers
            )
            response.raise_for_status()
            data = sorted(response.json()["data"], key=lambda item: item["index"])
            vectors = [item["embedding"] for item in data]
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            # Chỉ nêu loại lỗi: URL/header có thể chứa thông tin nhạy cảm
            raise EmbeddingError(f"Gọi endpoint embedding thất bại ({type(exc).__name__})") from None
        if len(vectors) != len(batch) or any(len(v) != self._dims for v in vectors):
            raise EmbeddingError(f"Endpoint embedding trả số vector/số chiều không khớp (cần {self._dims} chiều)")
        return vectors
