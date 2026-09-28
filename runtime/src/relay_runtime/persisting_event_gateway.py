"""Event bus that persists then fans out to subscribers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable

from relay_sdk import RelayEvent

from relay_runtime.ports.events import EventHandler, EventPublisher, EventStore

Handler = Callable[[RelayEvent], Awaitable[None]]


class PersistingEventGateway(EventPublisher):
    """Append to EventStore, then deliver to in-process subscribers."""

    def __init__(self, event_store: EventStore) -> None:
        self._store = event_store
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    async def publish(self, event: RelayEvent) -> None:
        await self._store.append(event)
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

        return unsubscribe
