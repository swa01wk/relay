"""Redis session routing lock (single writer per session)."""

from __future__ import annotations

import os

from redis.asyncio import Redis


class RedisSessionLock:
    def __init__(self, url: str | None = None) -> None:
        self._url = url or os.environ.get("RELAY_REDIS_URL", "redis://localhost:6379/0")
        self._client: Redis | None = None

    async def _redis(self) -> Redis:
        if self._client is None:
            self._client = Redis.from_url(self._url, decode_responses=True)
        return self._client

    async def acquire(self, session_id: str, *, owner: str, ttl_seconds: int = 300) -> bool:
        client = await self._redis()
        key = f"relay:session-lock:{session_id}"
        return bool(await client.set(key, owner, nx=True, ex=ttl_seconds))

    async def release(self, session_id: str, *, owner: str) -> None:
        client = await self._redis()
        key = f"relay:session-lock:{session_id}"
        current = await client.get(key)
        if current == owner:
            await client.delete(key)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
