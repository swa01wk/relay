"""Counters for rate limits: fixed windows keyed by what is being limited.

In memory for a single gateway process; in Redis (``RELAY_REDIS_URL``) so several gateway
processes share the same limits.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from redis.asyncio import Redis


class RateLimitRepository(ABC):
    @abstractmethod
    async def hit(self, key: str, *, window_seconds: int) -> tuple[int, int]:
        """Count one event; returns (events in the current window, seconds until it resets)."""

    @abstractmethod
    async def count(self, key: str) -> tuple[int, int]:
        """Events in the current window without counting a new one, and seconds until reset."""

    @abstractmethod
    async def reset(self, key: str) -> None: ...


class MemoryRateLimitRepository(RateLimitRepository):
    _MAX_KEYS = 100_000

    def __init__(self) -> None:
        self._windows: dict[str, tuple[float, int]] = {}  # key → (window end, count)

    def _current(self, key: str) -> tuple[float, int] | None:
        window = self._windows.get(key)
        if window is None or window[0] <= time.monotonic():
            self._windows.pop(key, None)
            return None
        return window

    async def hit(self, key: str, *, window_seconds: int) -> tuple[int, int]:
        window = self._current(key)
        if window is None:
            if len(self._windows) >= self._MAX_KEYS:  # drop expired windows before growing further
                now = time.monotonic()
                self._windows = {k: v for k, v in self._windows.items() if v[0] > now}
            window = (time.monotonic() + window_seconds, 0)
        window = (window[0], window[1] + 1)
        self._windows[key] = window
        return window[1], int(window[0] - time.monotonic()) + 1

    async def count(self, key: str) -> tuple[int, int]:
        window = self._current(key)
        return (window[1], int(window[0] - time.monotonic()) + 1) if window else (0, 0)

    async def reset(self, key: str) -> None:
        self._windows.pop(key, None)

    def clear(self) -> None:
        self._windows.clear()


class RedisRateLimitRepository(RateLimitRepository):
    def __init__(self, url: str) -> None:
        self._client = Redis.from_url(url, decode_responses=True)

    async def hit(self, key: str, *, window_seconds: int) -> tuple[int, int]:
        name = f"relay:rl:{key}"
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.incr(name)
            pipe.expire(name, window_seconds, nx=True)
            pipe.ttl(name)
            count, _set, ttl = await pipe.execute()
        return int(count), max(int(ttl), 1)

    async def count(self, key: str) -> tuple[int, int]:
        name = f"relay:rl:{key}"
        async with self._client.pipeline(transaction=False) as pipe:
            pipe.get(name)
            pipe.ttl(name)
            count, ttl = await pipe.execute()
        return int(count or 0), max(int(ttl), 0)

    async def reset(self, key: str) -> None:
        await self._client.delete(f"relay:rl:{key}")

    async def aclose(self) -> None:
        await self._client.aclose()
