"""Engine và session SQLAlchemy async (psycopg) của tiến trình API."""
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.settings.api import ApiSettings


def to_sqlalchemy_url(dsn: str) -> str:
    """`postgresql://` -> `postgresql+psycopg://` (driver psycopg 3)."""
    return make_url(dsn).set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def create_engine_from_settings(s: ApiSettings) -> AsyncEngine:
    return create_async_engine(
        to_sqlalchemy_url(s.database_url),
        pool_size=s.sa_pool_size,
        max_overflow=s.sa_max_overflow,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
