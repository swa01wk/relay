"""Event persistence and publication ports."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any

from relay_sdk import RelayEvent

EventHandler = Callable[[RelayEvent], Awaitable[None]]


class EventStore(ABC):
    @abstractmethod
    async def append(self, event: RelayEvent) -> None:
        """Append-only event log."""

    async def append_many(self, events: list[RelayEvent]) -> None:
        """Append a batch in order; stores override for a single round trip."""
        for event in events:
            await self.append(event)

    @abstractmethod
    async def list_for_session(self, session_id: str, *, after_sequence: int = -1) -> list[RelayEvent]:
        ...

    async def list_sessions(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Session summaries, most recently active first (see ``session_audit.summarize_sessions``)."""
        raise NotImplementedError

    async def list_by_types(
        self, types: Sequence[str], *, limit: int = 500, session_id: str | None = None
    ) -> list[RelayEvent]:
        """The newest ``limit`` events of the given types, across sessions unless one is given."""
        raise NotImplementedError

    async def delete_older_than(self, cutoff: datetime) -> int:
        """Retention: delete events recorded before ``cutoff``; return how many were removed."""
        raise NotImplementedError


class EventPublisher(ABC):
    @abstractmethod
    async def publish(self, event: RelayEvent) -> None:
        """Fan-out to subscribers (WebSocket, internal bus, etc.)."""

    @abstractmethod
    def subscribe(self, session_id: str, handler: EventHandler) -> Callable[[], None]:
        """Register handler; return unsubscribe callable."""
