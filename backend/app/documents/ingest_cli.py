"""Nạp toàn bộ tài liệu trong DOCUMENTS_DIR vào pgvector: `python -m app.documents.ingest_cli [--language vi]`.

Dùng cho service `ingest` trong docker-compose (chạy một lần mỗi lần `up`) và để nạp lại sau khi sửa tài liệu:
  docker compose run --rm ingest
Idempotent: file không đổi thì bỏ qua, file đã đổi thì thay toàn bộ chunk. Thoát mã 1 nếu có file lỗi (vd endpoint embedding chưa lên).
"""

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

from app.documents.ingestion_service import IngestionConfig, IngestionService
from app.documents.store import PgDocumentStore, create_pool
from app.embedding_client import HttpEmbedder
from app.settings import EMBEDDING_DIMS, get_settings

logger = logging.getLogger("ingest")


def main() -> int:
    parser = argparse.ArgumentParser(description="Nạp tài liệu trong DOCUMENTS_DIR vào pgvector")
    parser.add_argument("--language", choices=["vi", "ko"], default="vi", help="ngôn ngữ của tài liệu (metadata)")
    parser.add_argument("--subfolder", default="", help="chỉ nạp thư mục con của DOCUMENTS_DIR")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    settings = get_settings()
    root = Path(settings.documents_dir).resolve()
    folder = (root / args.subfolder).resolve()
    if not folder.is_relative_to(root) or not folder.is_dir():
        logger.error("Không tìm thấy thư mục tài liệu: %s", folder)
        return 1

    pool = create_pool(settings)
    pool.open(wait=True, timeout=60)  # đợi DB sẵn sàng (compose đã chờ migrate, đây chỉ là lớp an toàn)
    embedder = HttpEmbedder(
        base_url=settings.embedding_api_url, model=settings.embedding_model_name, dims=EMBEDDING_DIMS,
        batch_size=settings.embedding_batch_size, timeout_s=settings.embedding_timeout_s, api_key=settings.embedding_api_key,
    )
    config = IngestionConfig(settings.embedding_chunk_size, settings.embedding_chunk_overlap, settings.max_upload_bytes)
    try:
        results = IngestionService(PgDocumentStore(pool), embedder, config).ingest_folder(root, folder, True, args.language)
    finally:
        embedder.close()
        pool.close()

    for result in results:
        logger.info("%-9s %s%s", result.status, result.source, f" ({result.detail})" if result.detail else "")
    totals = Counter(result.status for result in results)
    logger.info("Xong: %s", ", ".join(f"{count} {status}" for status, count in sorted(totals.items())) or "không có tài liệu nào")
    return 1 if totals["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
