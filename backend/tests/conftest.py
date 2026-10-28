"""Fixture Postgres thật cho test nghiệp vụ cửa hàng (tồn kho, giao dịch, đồng thời).

Cần biến môi trường TEST_DATABASE_URL: DSN dạng key=value của một Postgres có pgvector và quyền tạo database, ví dụ
  host=localhost port=6025 user=langchain password=... dbname=postgres
Không đặt thì các test cần DB bị bỏ qua. Mỗi test nhận một database mới tạo từ template đã chạy `alembic upgrade head`.
"""

import os
import uuid
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg_pool import ConnectionPool

from app.shop.services import build_shop_services
from settings_factory import make_settings

_BACKEND = Path(__file__).resolve().parents[1]


def _admin_dsn() -> str:
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL chưa đặt: bỏ qua test cần Postgres")
    return dsn


def _migrate(dsn: str) -> None:
    info = conninfo_to_dict(dsn)
    os.environ.update(
        POSTGRES_USER=info["user"], POSTGRES_PASSWORD=info.get("password", ""), POSTGRES_DB=info["dbname"],
        POSTGRES_HOST=info.get("host", "localhost"), POSTGRES_PORT=str(info.get("port", 5432)),
    )
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def template_db():
    admin = _admin_dsn()
    name = f"tpl_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    try:
        _migrate(make_conninfo(admin, dbname=name))
        yield admin, name
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def db_pool(template_db):
    admin, template = template_db
    name = f"t_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template}"')
    pool = ConnectionPool(make_conninfo(admin, dbname=name), min_size=1, max_size=8, open=True)
    try:
        yield pool
    finally:
        pool.close()
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def shop(db_pool):
    return build_shop_services(make_settings(), db_pool)
