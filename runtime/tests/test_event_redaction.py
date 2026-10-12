"""Event-log redaction (stored copy only) and retention."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from relay_protocol import EventType, RelayEvent, RelayEventMetadata
from relay_runtime import MemoryEventStore, PersistingEventGateway
from relay_runtime.event_redaction import REDACTED, modes_from_env, redactor
from relay_runtime.session_audit import AUDIT_EVENT_TYPES, build_audit_trail

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _event(kind: EventType, payload: dict[str, Any], seq: int, at: datetime = NOW) -> RelayEvent:
    return RelayEvent(
        type=kind,
        metadata=RelayEventMetadata(session_id="s", sequence=seq, source="test", timestamp=at),
        payload=payload,
    )


EVENTS = [
    _event(EventType.TRANSCRIPT_FINAL, {"text": "my SSN is 123", "is_final": True}, 0),
    _event(EventType.RESPONSE_COMPLETED, {"text": "Noted, Priya."}, 1),
    _event(EventType.TOOL_CALL_COMPLETED, {"name": "get_account", "result": {"owner": "Priya"}}, 2),
    _event(EventType.ACTION_REQUESTED, {"action": "PRESENT_UI", "action_id": "x1", "payload": {"rows": ["Priya"]}}, 3),
    _event(EventType.APPROVAL_REQUESTED, {"approval_id": "a1", "tool_name": "update_deal", "summary": "Priya's deal",
                                          "arguments": {"owner": "Priya"}}, 4),
    _event(EventType.APPROVAL_GRANTED, {"approval_id": "a1", "tool_name": "update_deal"}, 5),
    _event(EventType.COMMIT_VERIFIED, {"approval_id": "a1", "tool_name": "update_deal", "verified": True,
                                       "result": {"owner": "Priya"}}, 6),
    _event(EventType.METRIC, {"name": "model.usage", "value": 10, "details": {"model": "m"}}, 7),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("modes", [("text",), ("data",), ("text", "data")])
async def test_store_gets_the_redacted_copy_and_subscribers_the_original(modes):
    store = MemoryEventStore()
    gateway = PersistingEventGateway(store, stored_copy=redactor(modes))
    live: list[RelayEvent] = []

    async def on_event(event: RelayEvent) -> None:
        live.append(event)

    gateway.subscribe("s", on_event)
    for event in EVENTS:
        await gateway.publish(event)

    assert [e.payload for e in live] == [e.payload for e in EVENTS]  # the app still sees everything
    stored = {e.type: e.payload for e in store.all_events()}
    dumped = str(stored)
    assert ("123" in dumped) == ("text" not in modes)
    assert ("Priya" in dumped) == (set(modes) != {"text", "data"})
    if "text" in modes:
        assert stored[EventType.TRANSCRIPT_FINAL] == {"text": REDACTED, "is_final": True}
    if "data" in modes:
        assert stored[EventType.TOOL_CALL_COMPLETED] == {"name": "get_account", "result": REDACTED}
        assert stored[EventType.ACTION_REQUESTED] == {"action": "PRESENT_UI", "action_id": "x1", "payload": REDACTED}
        # The audit trail still says what was approved and that it was saved — without the values.
        (entry,) = build_audit_trail(await store.list_by_types(AUDIT_EVENT_TYPES))
        assert (entry["tool_name"], entry["decision"], entry["outcome"]) == ("update_deal", "granted", "saved")
        assert entry["arguments"] == REDACTED
    assert stored[EventType.METRIC]["details"] == {"model": "m"}


def test_modes_from_env(monkeypatch):
    monkeypatch.delenv("RELAY_EVENT_STORE_REDACT", raising=False)
    assert modes_from_env() == frozenset() and redactor(modes_from_env()) is None
    monkeypatch.setenv("RELAY_EVENT_STORE_REDACT", " Text, data ")
    assert modes_from_env() == {"text", "data"}
    monkeypatch.setenv("RELAY_EVENT_STORE_REDACT", "everything")
    with pytest.raises(ValueError, match="unknown mode"):
        modes_from_env()


@pytest.mark.asyncio
async def test_retention_deletes_only_old_events():
    store = MemoryEventStore()
    await store.append(_event(EventType.TURN_STARTED, {}, 0, at=NOW - timedelta(days=40)))
    await store.append(_event(EventType.TURN_STARTED, {}, 1, at=NOW - timedelta(days=2)))
    assert await store.delete_older_than(NOW - timedelta(days=30)) == 1
    assert [e.metadata.sequence for e in store.all_events()] == [1]
