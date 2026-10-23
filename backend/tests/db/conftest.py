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
from sqlalchemy.engine import make_url

from app.db import bootstrap
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


@pytest.fixture
def fresh_db(admin_url):
    """Database tạm trống + MigrateSettings trỏ tới nó. Xoá database sau test."""
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
    )
    yield settings
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def bootstrapped_db(fresh_db):
    bootstrap.run(fresh_db)
    return fresh_db


def role_url(settings: MigrateSettings, role: str) -> str:
    password = {ROLE_MIGRATOR: MIGRATOR_PASSWORD, ROLE_APP: APP_PASSWORD, ROLE_MCP: MCP_PASSWORD}[role]
    return make_url(settings.bootstrap_database_url).set(username=role, password=password).render_as_string(
        hide_password=False
    )
