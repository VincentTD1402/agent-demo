"""Chặn revision xoá dữ liệu đơn/hoàn tiền khi bảng đang có dòng, trừ khi người vận hành cho phép tường minh.

Cho phép bằng `alembic -x allow_destroy_legacy_orders=true`. Bootstrap truyền cờ này từ
`MigrateSettings.allow_destroy_legacy_orders` (biến môi trường ALLOW_DESTROY_LEGACY_ORDERS, mặc định false).
"""
from argparse import Namespace

from alembic import context
from alembic.config import Config

ALLOW_FLAG = "allow_destroy_legacy_orders"
_TABLES = frozenset({"orders", "refunds"})


def with_allow_destroy_flag(cfg: Config, allow: bool) -> Config:
    """Gắn `-x allow_destroy_legacy_orders=true` vào Config chạy bằng code (không qua CLI)."""
    if allow:
        cfg.cmd_opts = Namespace(x=[f"{ALLOW_FLAG}=true"])
    return cfg


def require_destroy_allowed(bind, tables: tuple[str, ...], action: str) -> None:
    """Ném RuntimeError nếu một trong `tables` còn dòng mà cờ cho phép xoá chưa bật."""
    unknown = set(tables) - _TABLES
    if unknown:
        raise ValueError(f"bảng không được bảo vệ: {sorted(unknown)}")
    counts = {t: bind.exec_driver_sql(f"SELECT count(*) FROM {t}").scalar_one() for t in tables}  # noqa: S608
    rows = {t: n for t, n in counts.items() if n}
    if not rows:
        return
    if context.get_x_argument(as_dictionary=True).get(ALLOW_FLAG) == "true":
        return
    detail = ", ".join(f"{n} dòng ở {t}" for t, n in rows.items())
    raise RuntimeError(
        f"Từ chối {action}: sẽ xoá {detail}. Sao lưu (pg_dump) rồi chạy lại với "
        f"`alembic -x {ALLOW_FLAG}=true` (compose: ALLOW_DESTROY_LEGACY_ORDERS=true) nếu chắc chắn bỏ dữ liệu này."
    )
