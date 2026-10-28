"""Guardrail đầu vào cho chat: giới hạn tần suất và lọc tin nhắn rác/tiêm lệnh trước khi tốn lượt LLM.

Chạy trước agent, không phụ thuộc model, nên spam và các câu "bỏ qua hướng dẫn" không tốn token và không thể thương lượng.
Bộ đếm nằm trong bộ nhớ tiến trình (một replica api); chạy nhiều replica thì mỗi replica đếm riêng.
"""

import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from app.settings import Settings

# Câu trả lời dựng sẵn (không gọi LLM), giọng nhân viên tư vấn
REPLY_EMPTY = "Dạ, anh/chị cho em biết mình cần em hỗ trợ gì về sản phẩm hoặc đơn hàng ở ShopMobile nhé ạ."
REPLY_SPAM = (
    "Dạ em chưa hiểu tin nhắn này ạ. Anh/chị nhắn rõ giúp em nội dung cần hỗ trợ về sản phẩm, giá, đặt hàng "
    "hoặc chính sách của ShopMobile nhé."
)
REPLY_LINKS = "Dạ em chưa xem được các đường dẫn ạ. Anh/chị cho em biết tên sản phẩm hoặc nội dung cần hỗ trợ tại ShopMobile nhé."
REPLY_STOP = (
    "Dạ em chỉ hỗ trợ các vấn đề mua sắm tại ShopMobile ạ. Khi nào anh/chị cần tư vấn sản phẩm hay kiểm tra đơn hàng "
    "thì nhắn em nhé!"
)
REPLY_SCOPE = (
    "Dạ em là trợ lý của ShopMobile nên chỉ hỗ trợ tư vấn sản phẩm, đặt hàng và các chính sách của cửa hàng thôi ạ. "
    "Anh/chị cần em hỗ trợ gì về mua sắm thì cứ nói em nhé!"
)

# Cố tình đổi vai trò / lộ hướng dẫn hệ thống: trả lời dựng sẵn, không đưa cho model
_INJECTION = re.compile(
    r"(ignore|disregard|forget|override)\s+(?:(?:all|any|the|your|previous|prior|above|earlier|these|those)\s+)*"
    r"(instructions?|rules?|prompts?|guidelines?)"
    r"|system\s+prompt|developer\s+mode|jailbreak|\bDAN\b"
    r"|bỏ\s+qua\s+(?:(?:mọi|tất\s+cả|các|những)\s+)?(?:hướng\s+dẫn|quy\s+tắc|chỉ\s+dẫn|lệnh)"
    r"|quên\s+(?:hết\s+)?(?:hướng\s+dẫn|quy\s+tắc|chỉ\s+dẫn)"
    r"|prompt\s+hệ\s+thống|đóng\s+vai",
    re.IGNORECASE,
)
_REPEATED_CHAR = re.compile(r"(.)\1{14,}")
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)


def screen_message(text: str) -> str | None:
    """Câu trả lời dựng sẵn nếu tin nhắn không nên đến model (rác, nhiều link, tiêm lệnh); None nếu bình thường."""
    stripped = (text or "").strip()
    if not any(ch.isalnum() for ch in stripped):
        return REPLY_EMPTY
    if _INJECTION.search(stripped):
        return REPLY_SCOPE
    if len(_URL.findall(stripped)) >= 3:
        return REPLY_LINKS
    words = stripped.lower().split()
    if _REPEATED_CHAR.search(stripped) or (len(words) >= 8 and len(set(words)) <= max(1, len(words) // 6)):
        return REPLY_SPAM
    return None


class SlidingWindowLimiter:
    """Tối đa `limit` lần trong `window_s` giây cho mỗi khoá."""

    def __init__(self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic):
        self._limit, self._window, self._clock = limit, window_s, clock
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str) -> float | None:
        """Ghi nhận một lần; trả về số giây phải chờ nếu đã vượt giới hạn (lần bị chặn không được ghi)."""
        now = self._clock()
        queue = self._hits.setdefault(key, deque())
        while queue and now - queue[0] >= self._window:
            queue.popleft()
        if len(queue) >= self._limit:
            return max(self._window - (now - queue[0]), 1.0)
        queue.append(now)
        if len(self._hits) > 5000:  # dọn khoá đã hết hạn để bộ nhớ không phình mãi
            self._hits = {k: q for k, q in self._hits.items() if q and now - q[-1] < self._window}
        return None


@dataclass(frozen=True)
class GuardVerdict:
    retry_after: int | None = None  # có giá trị: từ chối 429, client chờ ngần này giây
    reply: str | None = None  # có giá trị: trả câu dựng sẵn, không gọi agent

    @property
    def allowed(self) -> bool:
        return self.retry_after is None and self.reply is None


class ChatGuard:
    def __init__(self, per_minute: int, per_hour: int, per_ip_per_minute: int, duplicate_limit: int,
                 clock: Callable[[], float] = time.monotonic):
        self._minute = SlidingWindowLimiter(per_minute, 60, clock)
        self._hour = SlidingWindowLimiter(per_hour, 3600, clock)
        self._ip = SlidingWindowLimiter(per_ip_per_minute, 60, clock)
        # Cùng một nội dung gửi lặp lại trong 1 phút: duplicate_limit lần là tối đa
        self._same = SlidingWindowLimiter(duplicate_limit, 60, clock)

    @classmethod
    def from_settings(cls, s: Settings) -> "ChatGuard":
        return cls(s.chat_rate_per_minute, s.chat_rate_per_hour, s.chat_rate_per_ip_per_minute, s.chat_duplicate_limit)

    def check(self, session_key: str, ip: str, message: str) -> GuardVerdict:
        normalized = " ".join((message or "").lower().split())
        for limiter, key in (
            (self._ip, f"ip:{ip}"), (self._minute, session_key), (self._hour, session_key),
            (self._same, f"{session_key}|{normalized}"),
        ):
            wait = limiter.hit(key)
            if wait is not None:
                return GuardVerdict(retry_after=int(wait) + 1)
        return GuardVerdict(reply=screen_message(message))
