"""Event-log retention: delete events older than ``RELAY_EVENT_RETENTION_DAYS``."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from relay_gateway.repositories.event_repository import EventRepository

logger = logging.getLogger(__name__)


class RetentionService:
    def __init__(self, events: EventRepository) -> None:
        self._events = events
        self._task: asyncio.Task[None] | None = None

    @staticmethod
    def days() -> float:
        raw = os.environ.get("RELAY_EVENT_RETENTION_DAYS", "").strip()
        return float(raw) if raw else 0.0

    async def purge(self, days: float) -> int:
        removed = await self._events.delete_older_than(datetime.now(timezone.utc) - timedelta(days=days))
        if removed:
            logger.info("event retention removed %d events older than %g days", removed, days)
        return removed

    def start(self) -> None:
        """Purge now and then hourly, when a retention window is configured."""
        if self.days() > 0 and self._task is None:
            self._task = asyncio.create_task(self._loop(self.days()))

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self, days: float) -> None:
        while True:
            try:
                await self.purge(days)
            except Exception:
                logger.exception("event retention failed")
            await asyncio.sleep(3600)
