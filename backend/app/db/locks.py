"""Khoá advisory của Postgres. Mỗi nhóm dùng một namespace (classid) riêng để không đụng nhau."""
import time

import psycopg

# Namespace cho khoá của bước migrate/bootstrap; khoá theo thread hội thoại phải dùng namespace khác
ADVISORY_NS_MIGRATE = 7101
_MIGRATE_OBJECT_ID = 1
_POLL_INTERVAL_S = 0.5


def acquire_migrate_lock(conn: psycopg.Connection, timeout_s: float = 300.0) -> None:
    """Giữ khoá bootstrap cho tới khi đóng kết nối (kể cả khi tiến trình chết).

    Cố ý thăm dò bằng pg_try_advisory_lock thay vì pg_advisory_lock chặn: một câu lệnh đang chờ khoá
    được tính là giao dịch đang mở, và `CREATE INDEX CONCURRENTLY` (LangGraph setup) của tiến trình
    đang giữ khoá sẽ chờ nó -> hai bên chờ nhau vô hạn.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        row = conn.execute("SELECT pg_try_advisory_lock(%s, %s)", (ADVISORY_NS_MIGRATE, _MIGRATE_OBJECT_ID)).fetchone()
        if row[0]:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Không lấy được khoá bootstrap sau {timeout_s:.0f}s (tiến trình migrate khác bị kẹt?)")
        time.sleep(_POLL_INTERVAL_S)
