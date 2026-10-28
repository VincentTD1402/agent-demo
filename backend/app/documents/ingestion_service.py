"""Quy trình nạp tài liệu: trích văn bản -> chia chunk -> embedding -> ghi DB. Dùng chung cho upload và folder."""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from app.documents.store import DocumentStore
from app.documents.text_extraction import (
    UnsupportedDocumentError,
    extract_text,
    is_markdown_like,
    is_supported,
    split_into_chunks,
)
from app.embedding_client import Embedder, EmbeddingError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestResult:
    source: str
    status: str  # indexed | unchanged | skipped | failed
    chunks: int = 0
    detail: str | None = None


@dataclass(frozen=True)
class IngestionConfig:
    chunk_size: int
    chunk_overlap: int
    max_bytes: int


class IngestionService:
    def __init__(self, store: DocumentStore, embedder: Embedder, config: IngestionConfig):
        self._store = store
        self._embedder = embedder
        self._config = config

    def ingest_bytes(self, source: str, data: bytes, language: str | None = None) -> IngestResult:
        """Không ném lỗi theo từng file: mọi lỗi trả về dưới dạng status skipped/failed để batch chạy tiếp."""
        if not is_supported(source):
            return IngestResult(source, "skipped", detail="Định dạng không hỗ trợ (chỉ nhận .txt, .md, .pdf, .docx)")
        if len(data) > self._config.max_bytes:
            return IngestResult(source, "skipped", detail=f"File lớn hơn {self._config.max_bytes // (1024 * 1024)} MB")
        # Đổi language cũng phải nạp lại nên language nằm trong hash
        content_hash = hashlib.sha256(f"{language or ''}|".encode() + data).hexdigest()
        try:
            if self._store.get_content_hash(source) == content_hash:
                return IngestResult(source, "unchanged")  # nội dung không đổi: khỏi tốn lượt gọi embedding
            text = extract_text(source, data)
            chunks = split_into_chunks(
                text, self._config.chunk_size, self._config.chunk_overlap, markdown=is_markdown_like(source)
            )
            if not chunks:
                return IngestResult(source, "skipped", detail="Không có văn bản để embedding (PDF scan?)")
            vectors = self._embedder.embed(chunks)
            self._store.replace_document(source, language, content_hash, chunks, vectors)
        except UnsupportedDocumentError as exc:
            return IngestResult(source, "skipped", detail=str(exc))
        except EmbeddingError as exc:
            return IngestResult(source, "failed", detail=str(exc))
        except Exception:
            logger.exception("Nạp tài liệu thất bại: %s", source)
            return IngestResult(source, "failed", detail="Lỗi nội bộ khi lưu tài liệu")
        return IngestResult(source, "indexed", chunks=len(chunks))

    def ingest_folder(
        self, root: Path, folder: Path, recursive: bool, language: str | None = None
    ) -> list[IngestResult]:
        """Nạp mọi file hỗ trợ trong `folder` (đã được kiểm tra nằm trong `root`). `source` = đường dẫn tương đối so với root."""
        results: list[IngestResult] = []
        for path in sorted(folder.rglob("*") if recursive else folder.glob("*")):
            if not path.is_file() or not is_supported(path.name):
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(root):  # symlink trỏ ra ngoài thư mục gốc
                results.append(IngestResult(path.name, "skipped", detail="Symlink trỏ ra ngoài thư mục tài liệu"))
                continue
            source = resolved.relative_to(root).as_posix()
            if resolved.stat().st_size > self._config.max_bytes:  # kiểm tra trước khi đọc vào RAM
                results.append(IngestResult(source, "skipped", detail="File vượt giới hạn dung lượng"))
                continue
            try:
                data = resolved.read_bytes()
            except OSError:
                results.append(IngestResult(source, "failed", detail="Không đọc được file"))
                continue
            results.append(self.ingest_bytes(source, data, language))
        return results
