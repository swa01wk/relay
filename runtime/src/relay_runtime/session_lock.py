"""No-op session lock for single-process dev."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LocalSessionLock:
    """Phase 1 single-process stand-in for Redis routing lock."""

    _held: set[str] | None = None

    def __post_init__(self) -> None:
        if self._held is None:
            self._held = set()

    async def acquire(self, session_id: str, *, owner: str, ttl_seconds: int = 300) -> bool:
        del owner, ttl_seconds
        assert self._held is not None
        if session_id in self._held:
            return False
        self._held.add(session_id)
        return True

    async def release(self, session_id: str, *, owner: str) -> None:
        del owner
        assert self._held is not None
        self._held.discard(session_id)
