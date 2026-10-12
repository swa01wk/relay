"""PersistingEventGateway write-behind: delivery before persistence, ordered batches, retries."""

from __future__ import annotations

import asyncio

import pytest

from relay_protocol import EventType, RelayEvent, RelayEventMetadata
from relay_runtime import MemoryEventStore, PersistingEventGateway


def _event(session_id: str, sequence: int) -> RelayEvent:
    return RelayEvent(
        type=EventType.RESPONSE_DELTA,
        metadata=RelayEventMetadata(session_id=session_id, sequence=sequence, source="test"),
        payload={"text": str(sequence)},
    )


class SlowFlakyStore(MemoryEventStore):
    """Blocks until released; fails the first batch once."""

    def __init__(self) -> None:
        super().__init__()
        self.release = asyncio.Event()
        self.batches: list[int] = []
        self.failures_left = 1

    async def append_many(self, events: list[RelayEvent]) -> None:
        await self.release.wait()
        if self.failures_left:
            self.failures_left -= 1
            raise ConnectionError("db blip")
        self.batches.append(len(events))
        for event in events:
            await self.append(event)


@pytest.mark.asyncio
async def test_write_behind_delivers_before_persisting_and_keeps_order():
    store = SlowFlakyStore()
    gateway = PersistingEventGateway(store, write_behind=True)
    session_id = "11111111-1111-1111-1111-111111111111"
    delivered: list[int] = []

    async def on_event(event: RelayEvent) -> None:
        delivered.append(event.metadata.sequence)

    gateway.subscribe(session_id, on_event)
    for sequence in range(1, 51):
        await gateway.publish(_event(session_id, sequence))

    # Store is still blocked, yet every event already reached the subscriber.
    assert delivered == list(range(1, 51))
    assert store.all_events() == []

    store.release.set()
    await gateway.flush()
    stored = [e.metadata.sequence for e in store.all_events()]
    assert stored == list(range(1, 51))
    assert sum(store.batches) == 50 and len(store.batches) < 50
    await gateway.close()


@pytest.mark.asyncio
async def test_inline_mode_persists_before_delivery():
    store = MemoryEventStore()
    gateway = PersistingEventGateway(store)
    session_id = "22222222-2222-2222-2222-222222222222"
    seen_in_store: list[int] = []

    async def on_event(event: RelayEvent) -> None:
        seen_in_store.append(len(store.all_events()))

    gateway.subscribe(session_id, on_event)
    await gateway.publish(_event(session_id, 1))
    assert seen_in_store == [1]


def test_unsubscribe_drops_empty_session_entry():
    gateway = PersistingEventGateway(MemoryEventStore())

    async def handler(event: RelayEvent) -> None:
        del event

    off = gateway.subscribe("s", handler)
    assert gateway.subscriber_count("s") == 1
    off()
    off()
    assert gateway.subscriber_count("s") == 0


@pytest.mark.asyncio
async def test_list_for_session_includes_sequence_zero_by_default():
    store = MemoryEventStore()
    session_id = "33333333-3333-3333-3333-333333333333"
    for sequence in (0, 1, 2):
        await store.append(_event(session_id, sequence))
    assert [e.metadata.sequence for e in await store.list_for_session(session_id)] == [0, 1, 2]
    assert [e.metadata.sequence for e in await store.list_for_session(session_id, after_sequence=0)] == [1, 2]
