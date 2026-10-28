"""Client reranker Qwen3-Reranker (vLLM): `POST {base_url}/rerank` -> điểm liên quan 0..1 cho từng đoạn."""

from typing import Protocol

import httpx

# Qwen3-Reranker là mô hình sinh "yes"/"no": phải bọc query/document đúng template, nếu không điểm không phân biệt được
_PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct "
    'provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
)
_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
_INSTRUCTION = (
    "Given a customer question about an electronics store, retrieve passages from the store's policies "
    "and product catalog that answer it"
)


class RerankError(Exception):
    """Endpoint lỗi, hết thời gian hoặc trả dữ liệu sai hình dạng. Thông báo không chứa URL/khoá API."""


class Reranker(Protocol):
    def score(self, query: str, documents: list[str]) -> list[float]: ...


class HttpReranker:
    def __init__(self, base_url: str, model: str, timeout_s: float):
        url = base_url.rstrip("/")
        self._url = url if url.endswith("/rerank") else url + "/rerank"
        self._model = model
        self._http = httpx.Client(timeout=httpx.Timeout(timeout_s))

    def close(self) -> None:
        self._http.close()

    def score(self, query: str, documents: list[str]) -> list[float]:
        """Điểm theo đúng thứ tự `documents`."""
        if not documents:
            return []
        body = {
            "model": self._model,
            "query": f"{_PREFIX}<Instruct>: {_INSTRUCTION}\n<Query>: {query}\n",
            "documents": [f"<Document>: {doc}{_SUFFIX}" for doc in documents],
        }
        try:
            response = self._http.post(self._url, json=body)
            response.raise_for_status()
            by_index = {item["index"]: float(item["relevance_score"]) for item in response.json()["results"]}
            scores = [by_index[i] for i in range(len(documents))]
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            raise RerankError(f"Gọi endpoint rerank thất bại ({type(exc).__name__})") from None
        return scores
