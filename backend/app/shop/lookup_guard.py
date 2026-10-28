"""Chặn dò tìm đơn hàng: tra cứu (mã đơn + SĐT) sai quá nhiều lần thì khoá tạm theo mã đơn và theo SĐT.

Mã đơn tuần tự và SĐT chỉ 10 số, nên nếu không giới hạn thì có thể thử lần lượt để xem đơn của người khác.
Lần sai được ghi bằng một kết nối riêng (sau khi giao dịch tra cứu đã đóng), không bị rollback theo lỗi nghiệp vụ.
Đổi lại, người thật nhập sai nhiều lần cũng bị khoá tạm vài phút; thông báo hướng dẫn liên hệ nhân viên.
"""

from collections.abc import Callable
from typing import TypeVar

from psycopg_pool import ConnectionPool

from app.shop.common import OrderNotFoundError, ShopError, ShopPolicy, normalize_phone

T = TypeVar("T")


class LookupGuard:
    def __init__(self, pool: ConnectionPool, policy: ShopPolicy):
        self._pool = pool
        self._policy = policy

    def verified(self, code: str, phone: str, work: Callable[[], T]) -> T:
        """Chạy `work` (tra cứu theo mã đơn + SĐT) với giới hạn dò tìm; ghi nhận lần sai khi không khớp đơn nào."""
        keys = self._keys(code, phone)
        self._check(keys)
        try:
            return work()
        except OrderNotFoundError:
            self._record(keys)
            raise

    def _keys(self, code: str, phone: str) -> list[tuple[str, int]]:
        keys = [(f"code:{(code or '').strip().upper()[:32]}", self._policy.lookup_max_failures_per_code)]
        try:
            keys.append((f"phone:{normalize_phone(phone)}", self._policy.lookup_max_failures_per_phone))
        except ShopError:
            pass  # SĐT sai định dạng vẫn tính vào mã đơn
        return keys

    def _check(self, keys: list[tuple[str, int]]) -> None:
        with self._pool.connection() as conn:
            for key, limit in keys:
                failures = conn.execute(
                    "SELECT count(*) FROM lookup_failures WHERE key = %s AND created_at > now() - make_interval(mins => %s)",
                    (key, self._policy.lookup_window_minutes),
                ).fetchone()[0]
                if failures >= limit:
                    raise ShopError(
                        "Thông tin tra cứu đơn hàng đã bị nhập sai quá nhiều lần. "
                        f"Vui lòng thử lại sau {self._policy.lookup_window_minutes} phút hoặc liên hệ nhân viên ShopMobile."
                    )

    def _record(self, keys: list[tuple[str, int]]) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM lookup_failures WHERE created_at < now() - interval '1 day'")  # dọn dòng cũ
            for key, _ in keys:
                conn.execute("INSERT INTO lookup_failures (key) VALUES (%s)", (key,))
