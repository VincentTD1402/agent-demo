"""Schema không chứa khái niệm trùng với phần thanh toán/nhân viên: địa chỉ chỉ nằm trong orders.shipping_address,
trạng thái thanh toán suy ra từ `payments`, sự kiện chỉ ở `status_events`, dòng hàng chỉ ở `order_items`."""
import re
from pathlib import Path

import psycopg

from app.settings.migrate import ROLE_MIGRATOR
from tests.db.conftest import role_url

BACKEND_DIR = Path(__file__).resolve().parents[2]
FORBIDDEN_TABLES = {"addresses", "refund_events", "payment_events", "order_events", "payments"}
FORBIDDEN_NAMES = re.compile(r"payment_status|refund_events|payment_events|order_events|\baddresses\b")


def test_database_has_no_forbidden_tables_or_columns(shared_bootstrapped_db):
    with psycopg.connect(role_url(shared_bootstrapped_db, ROLE_MIGRATOR)) as conn:
        tables = {r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
        columns = conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public'"
        ).fetchall()
    assert not FORBIDDEN_TABLES & tables  # `payments` thuộc plan thanh toán, chưa có ở đây
    assert ("orders", "items") not in columns and ("orders", "payment_status") not in columns
    assert not [c for c in columns if c[1] in {"payment_status", "items"}]


def test_sources_do_not_mention_forbidden_names():
    paths = [*(BACKEND_DIR / "app").rglob("*.py"), *(BACKEND_DIR / "migrations" / "versions").glob("*.py")]
    offenders = [
        f"{p.relative_to(BACKEND_DIR)}: {m.group(0)}"
        for p in paths
        for m in FORBIDDEN_NAMES.finditer(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, offenders
