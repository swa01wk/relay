"""PostgreSQL append-only RP event log."""

from __future__ import annotations

import json
import os

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
        await self.connect()
        assert self._pool is not None
        data = event.model_dump(mode="json")
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO relay_events (event_id, session_id, sequence, type, payload, metadata)
                VALUES ($1::uuid, $2::uuid, $3, $4, $5::jsonb, $6::jsonb)
                ON CONFLICT (event_id) DO NOTHING
                """,
                data["metadata"]["event_id"],
                data["metadata"]["session_id"],
                data["metadata"]["sequence"],
                data["type"],
                json.dumps(data["payload"]),
                json.dumps(data["metadata"]),
            )

    async def list_for_session(self, session_id: str, *, after_sequence: int = 0) -> list[RelayEvent]:
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
        events: list[RelayEvent] = []
        for row in rows:
            events.append(
                RelayEvent(
                    type=EventType(row["type"]),
                    metadata=row["metadata"],
                    payload=row["payload"],
                )
            )
        return events
