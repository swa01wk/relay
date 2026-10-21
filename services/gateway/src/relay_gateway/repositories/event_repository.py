"""The event log: every stored Relay Protocol event."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from relay_runtime import PersistingEventGateway
from relay_runtime.ports.events import EventStore
from relay_sdk import RelayEvent


class EventRepository:
    def __init__(self, store: EventStore, gateway: PersistingEventGateway) -> None:
        self._store = store
        self._gateway = gateway

    async def _settled(self) -> EventStore:
        # Writes are batched behind delivery; wait for them so a read sees what was just published.
        await self._gateway.flush()
        return self._store

    async def for_session(self, session_id: str) -> list[RelayEvent]:
        return await (await self._settled()).list_for_session(session_id)

    async def session_summaries(self, *, limit: int, project_id: str | None = None) -> list[dict[str, Any]]:
        return await (await self._settled()).list_sessions(limit=limit, project_id=project_id)

    async def newest_of_types(
        self,
        types: Sequence[str],
        *,
        limit: int,
        session_id: str | None = None,
        project_id: str | None = None,
        since: datetime | None = None,
    ) -> list[RelayEvent]:
        return await (await self._settled()).list_by_types(
            types, limit=limit, session_id=session_id, project_id=project_id, since=since
        )

    async def delete_older_than(self, cutoff: datetime) -> int:
        return await (await self._settled()).delete_older_than(cutoff)
