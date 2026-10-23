"""Bootstrap chạy một lần (service `migrate`): role -> Alembic upgrade -> bảng LangGraph -> GRANT -> seed.

Chạy: `python -m app.db.bootstrap`. Thoát mã khác 0 nếu có lỗi nên các service phụ thuộc không khởi động.
Một khoá advisory giữ suốt quá trình nên nhiều tiến trình migrate chạy song song sẽ xếp hàng, không đạp nhau.
"""
import logging
import sys
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config

from app.db.langgraph_setup import setup_langgraph_tables
from app.db.legacy_order_guard import with_allow_destroy_flag
from app.db.locks import acquire_migrate_lock
from app.db.roles import apply_grants, prepare_cluster
from app.settings.migrate import MigrateSettings
from app.shop.seed import seed_demo_data

log = logging.getLogger("bootstrap")
# alembic.ini nằm cạnh package `app` (backend/ khi chạy local, /srv trong image)
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def alembic_config(dsn: str, allow_destroy_legacy_orders: bool = False) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["url"] = dsn
    return with_allow_destroy_flag(cfg, allow_destroy_legacy_orders)


def run(settings: MigrateSettings | None = None) -> None:
    s = settings or MigrateSettings()  # type: ignore[call-arg]
    # Kết nối superuser chỉ làm bước đầu và giữ khoá; mọi DDL còn lại chạy bằng role migrator
    with psycopg.connect(s.bootstrap_database_url, autocommit=True) as lock_conn:
        acquire_migrate_lock(lock_conn)
        log.info("Tạo extension vector, role và quyền database")
        prepare_cluster(lock_conn, s)
        log.info("alembic upgrade head")
        command.upgrade(alembic_config(s.migrator_database_url, s.allow_destroy_legacy_orders), "head")
        log.info("Tạo bảng LangGraph")
        setup_langgraph_tables(s.migrator_database_url, s.embedding_dims)
        with psycopg.connect(s.migrator_database_url, autocommit=True) as conn:
            log.info("Cấp quyền cho role app/mcp")
            apply_grants(conn)
            if s.seed_demo_data:
                log.info("Nạp dữ liệu mẫu")
                seed_demo_data(conn, s)
    log.info("Bootstrap xong")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        run()
    except Exception:
        log.exception("Bootstrap thất bại")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
