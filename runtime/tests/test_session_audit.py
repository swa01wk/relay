"""Session summaries and the approvals/saves audit trail, derived from stored events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from relay_protocol import EventType, RelayEvent, RelayEventMetadata
from relay_runtime import MemoryEventStore
from relay_runtime.session_audit import AUDIT_EVENT_TYPES, build_audit_trail

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _event(kind: EventType, payload: dict[str, Any], *, session: str, seq: int, **meta: Any) -> RelayEvent:
    return RelayEvent(
        type=kind,
        metadata=RelayEventMetadata(
            session_id=session, sequence=seq, source="test", timestamp=T0 + timedelta(seconds=seq), **meta
        ),
        payload=payload,
    )


async def _store() -> MemoryEventStore:
    store = MemoryEventStore()
    events = [
        _event(EventType.SESSION_STARTED, {"transport": "dev", "agent_id": "sales-crm"}, session="s1", seq=0),
        _event(EventType.TURN_STARTED, {}, session="s1", seq=1, turn_id="t1"),
        _event(EventType.APPROVAL_REQUESTED, {"approval_id": "a1", "tool_name": "update_deal", "summary": "Move to Won",
                                              "arguments": {"deal_id": "DEAL-1", "stage": "won"}}, session="s1", seq=2),
        _event(EventType.APPROVAL_GRANTED, {"approval_id": "a1", "tool_name": "update_deal"}, session="s1", seq=3),
        _event(EventType.COMMIT_VERIFIED, {"approval_id": "a1", "tool_name": "update_deal", "verified": True,
                                           "commit_id": "c1"}, session="s1", seq=4),
        _event(EventType.APPROVAL_REQUESTED, {"approval_id": "a2", "tool_name": "delete_deal", "arguments": {}},
               session="s1", seq=5),
        _event(EventType.APPROVAL_REJECTED, {"approval_id": "a2", "tool_name": "delete_deal"}, session="s1", seq=6),
        _event(EventType.SESSION_ERROR, {"code": "turn_failed"}, session="s1", seq=7, turn_id="t1"),
        _event(EventType.SESSION_STARTED, {"transport": "dev", "agent_id": "mortgage"}, session="s2", seq=10),
        # A saved form: granted without a request event, then the save fails.
        _event(EventType.APPROVAL_GRANTED, {"approval_id": "a3", "tool_name": "create_contact", "via": "form_submit"},
               session="s2", seq=11),
        _event(EventType.ERROR, {"message": "commit_failed", "approval_id": "a3", "tool_name": "create_contact",
                                 "error": "email already exists"}, session="s2", seq=12),
        _event(EventType.ERROR, {"message": "something else"}, session="s2", seq=13),
        _event(EventType.SESSION_ENDED, {"reason": "client_disconnect"}, session="s2", seq=14),
    ]
    for event in events:
        await store.append(event)
    return store


@pytest.mark.asyncio
async def test_session_summaries_most_recent_first():
    store = await _store()
    s2, s1 = await store.list_sessions()
    assert (s2["session_id"], s2["agent_id"], s2["ended"], s2["event_count"]) == ("s2", "mortgage", True, 5)
    assert (s1["agent_id"], s1["turns"], s1["errors"], s1["ended"]) == ("sales-crm", 1, 1, False)
    assert len(await store.list_sessions(limit=1)) == 1


@pytest.mark.asyncio
async def test_audit_trail_across_sessions():
    store = await _store()
    events = await store.list_by_types(AUDIT_EVENT_TYPES)
    failed, rejected, saved = build_audit_trail(events)

    assert (failed["approval_id"], failed["via"], failed["decision"], failed["outcome"]) == (
        "a3", "form_submit", "granted", "failed")
    assert failed["error"] == "email already exists" and failed["session_id"] == "s2"
    assert (rejected["tool_name"], rejected["decision"], rejected["outcome"]) == ("delete_deal", "rejected", None)
    assert (saved["decision"], saved["via"], saved["outcome"], saved["commit_id"]) == ("granted", "approval", "saved", "c1")
    assert saved["arguments"] == {"deal_id": "DEAL-1", "stage": "won"} and saved["summary"] == "Move to Won"

    only_s1 = build_audit_trail(await store.list_by_types(AUDIT_EVENT_TYPES, session_id="s1"))
    assert {e["approval_id"] for e in only_s1} == {"a1", "a2"}
