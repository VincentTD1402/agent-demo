"""Chạy coroutine từ mã đồng bộ (bootstrap, test) với event loop mà psycopg async dùng được."""
import asyncio
import selectors
import sys
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """psycopg async không chạy trên ProactorEventLoop (mặc định của Windows) nên dùng Selector loop."""
    if sys.platform == "win32":
        return asyncio.run(coro, loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
    return asyncio.run(coro)
