"""Event bus that persists then fans out to subscribers."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable

from relay_sdk import RelayEvent

from relay_runtime.ports.events import EventHandler, EventPublisher, EventStore

Handler = Callable[[RelayEvent], Awaitable[None]]

logger = logging.getLogger(__name__)

_WRITE_RETRIES = 3


class PersistingEventGateway(EventPublisher):
    """Append to EventStore and deliver to in-process subscribers.

    ``write_behind=False`` (default) persists before delivery. ``write_behind=True`` delivers
    first and batches appends on a background writer in publish order, so a slow store does not
    sit on the streaming path; call ``flush()`` before reading the store, ``close()`` on shutdown.
    """

    def __init__(
        self,
        event_store: EventStore,
        *,
        write_behind: bool = False,
        max_batch: int = 200,
        stored_copy: Callable[[RelayEvent], RelayEvent] | None = None,
    ) -> None:
        self._store = event_store
        # Applied to what is written to the store only (see event_redaction); subscribers get the original.
        self._stored_copy = stored_copy
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._write_behind = write_behind
        self._max_batch = max_batch
        self._pending: asyncio.Queue[RelayEvent] | None = None
        self._writer: asyncio.Task[None] | None = None

    async def publish(self, event: RelayEvent) -> None:
        stored = self._stored_copy(event) if self._stored_copy is not None else event
        if self._write_behind:
            self._enqueue(stored)
        else:
            await self._store.append(stored)
        session_id = event.metadata.session_id
        for handler in list(self._handlers.get(session_id, [])):
            await handler(event)
        for handler in list(self._handlers.get("*", [])):
            await handler(event)

    def subscribe(self, session_id: str, handler: EventHandler) -> Callable[[], None]:
        self._handlers[session_id].append(handler)

        def unsubscribe() -> None:
            if handler in self._handlers[session_id]:
                self._handlers[session_id].remove(handler)
            if not self._handlers[session_id]:
                del self._handlers[session_id]

        return unsubscribe

    def subscriber_count(self, session_id: str) -> int:
        return len(self._handlers.get(session_id, []))

    async def flush(self) -> None:
        """Wait until every published event has been written."""
        if self._pending is not None:
            await self._pending.join()

    async def close(self) -> None:
        await self.flush()
        if self._writer is not None:
            self._writer.cancel()
            try:
                await self._writer
            except asyncio.CancelledError:
                pass
            self._writer = None

    def _enqueue(self, event: RelayEvent) -> None:
        if self._pending is None:
            self._pending = asyncio.Queue()
        self._pending.put_nowait(event)
        if self._writer is None or self._writer.done():
            self._writer = asyncio.create_task(self._write_loop())

    async def _write_loop(self) -> None:
        assert self._pending is not None
        queue = self._pending
        while True:
            batch = [await queue.get()]
            while len(batch) < self._max_batch and not queue.empty():
                batch.append(queue.get_nowait())
            try:
                await self._append_with_retry(batch)
            finally:
                for _ in batch:
                    queue.task_done()

    async def _append_with_retry(self, batch: list[RelayEvent]) -> None:
        for attempt in range(1, _WRITE_RETRIES + 1):
            try:
                await self._store.append_many(batch)
                return
            except Exception:
                if attempt == _WRITE_RETRIES:
                    logger.exception("event store write failed; dropped %d events", len(batch))
                    return
                await asyncio.sleep(0.2 * 2**attempt)
