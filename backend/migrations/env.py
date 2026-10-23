"""Môi trường Alembic: kết nối bằng role migrator và so model với database."""
import os

from alembic import context
from sqlalchemy import create_engine

from app.db.base import Base
from app.db.langgraph_setup import LANGGRAPH_TABLES
from app.db.session import to_sqlalchemy_url
from app.shop import models  # noqa: F401  (đăng ký model vào Base.metadata)

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    """Thứ tự: URL do bootstrap truyền vào > ALEMBIC_DATABASE_URL (chạy `alembic check` tay) > MigrateSettings."""
    url = config.attributes.get("url") or os.environ.get("ALEMBIC_DATABASE_URL")
    if not url:
        from app.settings.migrate import MigrateSettings

        url = MigrateSettings().migrator_database_url  # type: ignore[call-arg]
    return to_sqlalchemy_url(url)


def include_name(name, type_, parent_names) -> bool:
    """Không reflect bảng LangGraph (cũng tránh cảnh báo kiểu `vector` mà SQLAlchemy chưa nhận ra)."""
    if type_ == "table":
        return name not in LANGGRAPH_TABLES
    return True


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Bảng của LangGraph do `setup()` quản lý: loại khỏi autogenerate để không bị đề xuất DROP."""
    if type_ == "table":
        return name not in LANGGRAPH_TABLES
    if type_ == "index":
        return obj.table.name not in LANGGRAPH_TABLES
    return True


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_name=include_name,
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
    )


def run_migrations_online() -> None:
    engine = create_engine(_database_url())
    try:
        with engine.connect() as connection:
            _configure(connection)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Chế độ offline (--sql) không được hỗ trợ: revision gọi trực tiếp vào Postgres")
run_migrations_online()
