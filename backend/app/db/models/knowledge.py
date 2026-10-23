"""Knowledge base song ngữ: tài liệu chính sách và các đoạn (chunk) có vector + tsvector."""
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Computed, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.catalog import EMBEDDING_DIMS


class KbDocument(Base):
    __tablename__ = "kb_documents"
    __table_args__ = (
        CheckConstraint("lang IN ('vi', 'en')", name="lang_valid"),
        UniqueConstraint("slug", "lang", name="uq_kb_documents_slug_lang"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KbChunk(Base):
    __tablename__ = "kb_chunks"
    __table_args__ = (
        Index(
            "ix_kb_chunks_embedding_hnsw", "embedding",
            postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_kb_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    document_id: Mapped[int] = mapped_column(Integer, ForeignKey("kb_documents.id", ondelete="CASCADE"), primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    # sha256(model + nội dung) của lần embed gần nhất; NULL embedding = chưa chạy reindex
    content_hash: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMS))
    # Tìm toàn văn bỏ dấu, cấu hình `simple` vì tiếng Việt không có stemmer sẵn
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', immutable_unaccent(content))", persisted=True)
    )
