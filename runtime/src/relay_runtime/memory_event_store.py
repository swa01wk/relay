"""In-memory append-only event log (tests and local dev without Postgres)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from relay_sdk import RelayEvent

from relay_runtime.ports.events import EventStore
from relay_runtime.session_audit import summarize_sessions


class MemoryEventStore(EventStore):
    def __init__(self) -> None:
        self._events: list[RelayEvent] = []

    async def append(self, event: RelayEvent) -> None:
        self._events.append(event)

    async def list_for_session(self, session_id: str, *, after_sequence: int = -1) -> list[RelayEvent]:
        return [
            e
            for e in self._events
            if e.metadata.session_id == session_id and e.metadata.sequence > after_sequence
        ]

    async def list_sessions(self, *, limit: int = 50, project_id: str | None = None) -> list[dict[str, Any]]:
        events = [e for e in self._events if project_id is None or e.metadata.project_id == project_id]
        return summarize_sessions(events, limit=limit)

    async def list_by_types(
        self,
        types: Sequence[str],
        *,
        limit: int = 500,
        session_id: str | None = None,
        project_id: str | None = None,
        since: datetime | None = None,
    ) -> list[RelayEvent]:
        wanted = {str(getattr(t, "value", t)) for t in types}
        matching = [
            e
            for e in self._events
            if e.type.value in wanted
            and (session_id is None or e.metadata.session_id == session_id)
            and (project_id is None or e.metadata.project_id == project_id)
            and (since is None or e.metadata.timestamp >= since)
        ]
        return matching[-limit:][::-1]

    async def delete_older_than(self, cutoff: datetime) -> int:
        kept = [e for e in self._events if e.metadata.timestamp >= cutoff]
        removed = len(self._events) - len(kept)
        self._events = kept
        return removed

    def all_events(self) -> list[RelayEvent]:
        return list(self._events)
