"""PostgreSQL append-only RP event log."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import asyncpg

from relay_protocol import EventType

from relay_sdk import RelayEvent

from relay_runtime.ports.events import EventStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS relay_events (
    event_id UUID PRIMARY KEY,
    session_id UUID NOT NULL,
    sequence INT NOT NULL,
    type TEXT NOT NULL,
    payload JSONB NOT NULL,
    metadata JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS relay_events_session_seq
    ON relay_events (session_id, sequence);
CREATE INDEX IF NOT EXISTS relay_events_type_created
    ON relay_events (type, created_at DESC);
CREATE INDEX IF NOT EXISTS relay_events_created
    ON relay_events (created_at);
CREATE INDEX IF NOT EXISTS relay_events_project_created
    ON relay_events ((metadata->>'project_id'), created_at DESC);
"""


class PostgresEventStore(EventStore):
    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn or os.environ.get(
            "RELAY_DATABASE_URL",
            "postgresql://relay:relay@localhost:5432/relay",
        )
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
            async with self._pool.acquire() as conn:
                await conn.execute(_SCHEMA)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def append(self, event: RelayEvent) -> None:
        await self.append_many([event])

    async def append_many(self, events: list[RelayEvent]) -> None:
        if not events:
            return
        await self.connect()
        assert self._pool is not None
        rows = []
        for event in events:
            data = event.model_dump(mode="json")
            rows.append(
                (
                    data["metadata"]["event_id"],
                    data["metadata"]["session_id"],
                    data["metadata"]["sequence"],
                    data["type"],
                    json.dumps(data["payload"]),
                    json.dumps(data["metadata"]),
                )
            )
        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO relay_events (event_id, session_id, sequence, type, payload, metadata)
                VALUES ($1::uuid, $2::uuid, $3, $4, $5::jsonb, $6::jsonb)
                ON CONFLICT (event_id) DO NOTHING
                """,
                rows,
            )

    async def list_sessions(self, *, limit: int = 50, project_id: str | None = None) -> list[dict[str, Any]]:
        await self.connect()
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT session_id::text AS session_id,
                       max(metadata->>'project_id') AS project_id,
                       max(payload->>'agent_id') FILTER (WHERE type = 'SESSION_STARTED') AS agent_id,
                       max(metadata->>'trace_id') AS trace_id,
                       min(metadata->>'timestamp') AS started_at,
                       max(metadata->>'timestamp') AS last_event_at,
                       count(*) AS event_count,
                       count(*) FILTER (WHERE type = 'TURN_STARTED') AS turns,
                       count(*) FILTER (WHERE type = 'SESSION_ERROR') AS errors,
                       bool_or(type = 'SESSION_ENDED') AS ended
                FROM relay_events
                WHERE ($2::text IS NULL OR metadata->>'project_id' = $2::text)
                GROUP BY session_id
                ORDER BY max(created_at) DESC
                LIMIT $1
                """,
                limit,
                project_id,
            )
        return [dict(row) for row in rows]

    async def list_by_types(
        self,
        types: Sequence[str],
        *,
        limit: int = 500,
        session_id: str | None = None,
        project_id: str | None = None,
        since: datetime | None = None,
    ) -> list[RelayEvent]:
        await self.connect()
        assert self._pool is not None
        names = [str(getattr(t, "value", t)) for t in types]
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT type, payload, metadata
                FROM relay_events
                WHERE type = ANY($1::text[]) AND ($3::uuid IS NULL OR session_id = $3::uuid)
                  AND ($4::text IS NULL OR metadata->>'project_id' = $4::text)
                  AND ($5::timestamptz IS NULL OR created_at >= $5::timestamptz)
                ORDER BY created_at DESC, sequence DESC
                LIMIT $2
                """,
                names,
                limit,
                session_id,
                project_id,
                since,
            )
        return [
            RelayEvent(
                type=EventType(row["type"]),
                metadata=_json_value(row["metadata"]),
                payload=_json_value(row["payload"]),
            )
            for row in rows
        ]

    async def delete_older_than(self, cutoff: datetime) -> int:
        await self.connect()
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            status = await conn.execute("DELETE FROM relay_events WHERE created_at < $1", cutoff)
        return int(status.rsplit(" ", 1)[-1])  # "DELETE <n>"

    async def list_for_session(self, session_id: str, *, after_sequence: int = -1) -> list[RelayEvent]:
        await self.connect()
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT type, payload, metadata
                FROM relay_events
                WHERE session_id = $1::uuid AND sequence > $2
                ORDER BY sequence ASC
                """,
                session_id,
                after_sequence,
            )
        # asyncpg returns JSONB as text unless a codec is registered.
        return [
            RelayEvent(
                type=EventType(row["type"]),
                metadata=_json_value(row["metadata"]),
                payload=_json_value(row["payload"]),
            )
            for row in rows
        ]


def _json_value(value: object) -> object:
    return json.loads(value) if isinstance(value, str) else value
