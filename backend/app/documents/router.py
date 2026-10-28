"""API nạp tài liệu: upload file qua multipart hoặc quét một thư mục trên server."""

import hmac
import threading
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Literal

from fastapi import APIRouter, Body, Depends, Form, Header, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from app.documents.ingestion_service import IngestionConfig, IngestionService
from app.settings import Settings, get_settings

router = APIRouter(prefix="/documents", tags=["documents"])

Language = Literal["vi", "ko"]


class FolderIngestRequest(BaseModel):
    subfolder: str = Field(default="", description="Thư mục con của DOCUMENTS_DIR; để trống = cả thư mục gốc")
    recursive: bool = True
    language: Language | None = Field(default=None, description="Ngôn ngữ của tài liệu (metadata để lọc khi truy vấn)")


class IngestResultOut(BaseModel):
    source: str
    status: str = Field(description="indexed | unchanged | skipped | failed")
    chunks: int = 0
    detail: str | None = None


class IngestResponse(BaseModel):
    results: list[IngestResultOut]


def require_api_key(x_api_key: str | None = Header(default=None), settings: Settings = Depends(get_settings)) -> None:
    if settings.api_key and not hmac.compare_digest(x_api_key or "", settings.api_key):
        raise HTTPException(status_code=401, detail="Thiếu hoặc sai X-API-Key")


@lru_cache
def _upload_gate(limit: int) -> threading.BoundedSemaphore:
    return threading.BoundedSemaphore(limit)


def limit_concurrency(settings: Settings = Depends(get_settings)):
    """Giới hạn số lần nạp chạy cùng lúc (mỗi lần tốn RAM + gọi embedding); quá giới hạn trả 429 thay vì xếp hàng."""
    gate = _upload_gate(settings.max_concurrent_uploads)
    if not gate.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Đang có quá nhiều lượt nạp tài liệu, thử lại sau")
    try:
        yield
    finally:
        gate.release()


def get_ingestion_service(request: Request, settings: Settings = Depends(get_settings)) -> IngestionService:
    # store/embedder do lifespan tạo trong app/main.py
    return IngestionService(
        request.app.state.document_store,
        request.app.state.embedder,
        IngestionConfig(settings.embedding_chunk_size, settings.embedding_chunk_overlap, settings.max_upload_bytes),
    )


def _safe_filename(raw: str | None) -> str:
    # Chỉ lấy tên file, bỏ mọi thành phần đường dẫn do client gửi
    return PurePosixPath((raw or "").replace("\\", "/")).name


def _resolve_folder(settings: Settings, subfolder: str) -> tuple[Path, Path]:
    root = Path(settings.documents_dir).resolve()
    folder = (root / subfolder).resolve()
    if not folder.is_relative_to(root):
        raise HTTPException(status_code=400, detail="subfolder phải nằm trong thư mục tài liệu")
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Không tìm thấy thư mục")
    return root, folder


@router.post("/upload", response_model=IngestResponse, dependencies=[Depends(require_api_key), Depends(limit_concurrency)])
def upload_documents(files: list[UploadFile], language: Language | None = Form(default=None),
                     service: IngestionService = Depends(get_ingestion_service),
                     settings: Settings = Depends(get_settings)) -> IngestResponse:
    results = []
    for upload in files:
        name = _safe_filename(upload.filename)
        if not name:
            results.append(IngestResultOut(source="", status="skipped", detail="File không có tên"))
            continue
        # Đọc tối đa max+1 byte: đủ để phát hiện file quá lớn mà không nạp cả file vào RAM
        data = upload.file.read(settings.max_upload_bytes + 1)
        results.append(IngestResultOut(**vars(service.ingest_bytes(name, data, language))))
    return IngestResponse(results=results)


@router.post("/ingest-folder", response_model=IngestResponse, dependencies=[Depends(require_api_key), Depends(limit_concurrency)])
def ingest_folder(body: FolderIngestRequest = Body(default_factory=FolderIngestRequest),
                  service: IngestionService = Depends(get_ingestion_service),
                  settings: Settings = Depends(get_settings)) -> IngestResponse:
    root, folder = _resolve_folder(settings, body.subfolder)
    results = service.ingest_folder(root, folder, body.recursive, body.language)
    return IngestResponse(results=[IngestResultOut(**vars(r)) for r in results])


@router.delete("", dependencies=[Depends(require_api_key)])
def delete_document(request: Request,
                    source: str = Query(description="Tên file (upload) hoặc đường dẫn tương đối (folder)")) -> dict[str, str]:
    if not request.app.state.document_store.delete_document(source):
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    return {"deleted": source}
