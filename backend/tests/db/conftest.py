"""Fixture cho test cần Postgres thật.

Đặt TEST_DATABASE_URL = DSN superuser của một Postgres có pgvector, ví dụ:
  docker run -d --rm --name p2-pg -p 55435:5432 -e POSTGRES_PASSWORD=SuperuserPass0123 pgvector/pgvector:pg17
  TEST_DATABASE_URL=postgresql://postgres:SuperuserPass0123@localhost:55435/postgres
(mật khẩu superuser phải khác 3 mật khẩu role bên dưới)
Mỗi test chạy trên một database tạm riêng (role là đối tượng toàn cluster nên được dùng chung và đặt lại mật khẩu).
Không có TEST_DATABASE_URL hoặc không kết nối được thì các test này được bỏ qua kèm lý do.
"""
import os
import uuid

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.engine import make_url

from app.db import bootstrap
from app.db.event_loop import run_async
from app.mcp_server import db as mcp_db
from app.settings.mcp import get_mcp_settings
from app.settings.migrate import ROLE_APP, ROLE_MCP, ROLE_MIGRATOR, MigrateSettings

MIGRATOR_PASSWORD = "MigratorTestPass1"
APP_PASSWORD = "AppTestPass123456"
MCP_PASSWORD = "McpTestPass123456"


@pytest.fixture(scope="session")
def admin_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL chưa đặt: cần Postgres có pgvector (xem tests/db/conftest.py)")
    try:
        with psycopg.connect(url, connect_timeout=5):
            pass
    except psycopg.OperationalError as exc:
        pytest.skip(f"Không kết nối được TEST_DATABASE_URL (Docker/Postgres chưa chạy?): {exc}")
    return url


def _make_database(admin_url: str):
    """Tạo database tạm trống; trả (tên, MigrateSettings trỏ tới nó)."""
    name = f"t_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    bootstrap_url = make_url(admin_url).set(database=name).render_as_string(hide_password=False)
    settings = MigrateSettings(
        _env_file=None,  # không đọc file .env thật
        bootstrap_database_url=bootstrap_url,
        migrator_db_password=MIGRATOR_PASSWORD,
        app_db_password=APP_PASSWORD,
        mcp_db_password=MCP_PASSWORD,
        seed_demo_data=True,
        env="dev",  # khách demo và đơn mẫu chỉ được seed ở ENV=dev
    )
    return name, settings


def _drop_database(admin_url: str, name: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def fresh_db(admin_url):
    """Database tạm trống + MigrateSettings trỏ tới nó. Xoá database sau test."""
    name, settings = _make_database(admin_url)
    yield settings
    _drop_database(admin_url, name)


@pytest.fixture
def bootstrapped_db(fresh_db):
    bootstrap.run(fresh_db)
    return fresh_db


@pytest.fixture(scope="module")
def shared_bootstrapped_db(admin_url):
    """Một database đã bootstrap + seed dùng chung cho cả module test chỉ đọc hoặc tự rollback (nhanh hơn)."""
    name, settings = _make_database(admin_url)
    bootstrap.run(settings)
    yield settings
    _drop_database(admin_url, name)


@pytest.fixture
def connect_as(shared_bootstrapped_db):
    """Mở kết nối theo role trên DB dùng chung; mọi thay đổi được rollback khi test kết thúc.
    Câu lệnh được kỳ vọng lỗi phải chạy trong `expect_error` (savepoint) để transaction còn dùng tiếp."""
    opened: list[psycopg.Connection] = []

    def _connect(role: str) -> psycopg.Connection:
        conn = psycopg.connect(role_url(shared_bootstrapped_db, role))
        opened.append(conn)
        return conn

    yield _connect
    for conn in opened:
        conn.rollback()
        conn.close()


def expect_error(conn: psycopg.Connection, exc: type[Exception], query: str, params=()) -> None:
    """Câu lệnh phải ném `exc`; savepoint giữ transaction ngoài còn dùng được."""
    with pytest.raises(exc):
        with conn.transaction():
            conn.execute(query, params)


def role_url(settings: MigrateSettings, role: str) -> str:
    password = {ROLE_MIGRATOR: MIGRATOR_PASSWORD, ROLE_APP: APP_PASSWORD, ROLE_MCP: MCP_PASSWORD}[role]
    return make_url(settings.bootstrap_database_url).set(username=role, password=password).render_as_string(
        hide_password=False
    )


async def open_pool(url: str) -> AsyncConnectionPool:
    pool = AsyncConnectionPool(url, min_size=1, max_size=2, open=False, kwargs={"row_factory": dict_row, "autocommit": True})
    await pool.open()
    return pool


@pytest.fixture
def run_with_mcp(bootstrapped_db, monkeypatch):
    """Chạy `scenario(server)` với module server MCP thật nối vào DB tạm bằng role mcp.
    Dùng event loop kiểu Selector (psycopg async không chạy trên Proactor của Windows) nên test là hàm đồng bộ."""
    url = role_url(bootstrapped_db, ROLE_MCP)
    monkeypatch.setenv("DATABASE_URL", url)
    get_mcp_settings.cache_clear()
    from app.mcp_server import server

    def run(scenario):
        async def main():
            pool = await open_pool(url)
            monkeypatch.setattr(mcp_db, "_pool", pool)
            try:
                await scenario(server)
            finally:
                await pool.close()

        run_async(main())

    yield run
    get_mcp_settings.cache_clear()
