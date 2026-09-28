"""In-memory append-only event log (tests and local dev without Postgres)."""

from __future__ import annotations

from relay_sdk import RelayEvent

from relay_runtime.ports.events import EventStore


class MemoryEventStore(EventStore):
    def __init__(self) -> None:
        self._events: list[RelayEvent] = []

    async def append(self, event: RelayEvent) -> None:
        self._events.append(event)

    async def list_for_session(self, session_id: str, *, after_sequence: int = 0) -> list[RelayEvent]:
        return [
            e
            for e in self._events
            if e.metadata.session_id == session_id and e.metadata.sequence > after_sequence
        ]

    def all_events(self) -> list[RelayEvent]:
        return list(self._events)
