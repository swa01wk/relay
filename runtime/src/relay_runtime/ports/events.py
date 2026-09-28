"""Event persistence and publication ports."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from relay_sdk import RelayEvent

EventHandler = Callable[[RelayEvent], Awaitable[None]]


class EventStore(ABC):
    @abstractmethod
    async def append(self, event: RelayEvent) -> None:
        """Append-only event log."""

    @abstractmethod
    async def list_for_session(self, session_id: str, *, after_sequence: int = 0) -> list[RelayEvent]:
        ...


class EventPublisher(ABC):
    @abstractmethod
    async def publish(self, event: RelayEvent) -> None:
        """Fan-out to subscribers (WebSocket, internal bus, etc.)."""

    @abstractmethod
    def subscribe(self, session_id: str, handler: EventHandler) -> Callable[[], None]:
        """Register handler; return unsubscribe callable."""
