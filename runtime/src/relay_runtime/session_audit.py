"""Operator views over the event log: session summaries and the approvals/saves audit trail.

Both are derived from stored events, so they work for any agent and survive gateway restarts
(with a persistent ``EventStore``).
"""

from __future__ import annotations

from typing import Any

from relay_protocol import EventType
from relay_sdk import RelayEvent

AUDIT_EVENT_TYPES = (
    EventType.APPROVAL_REQUESTED,
    EventType.APPROVAL_GRANTED,
    EventType.APPROVAL_REJECTED,
    EventType.COMMIT_VERIFIED,
    EventType.ERROR,
)


def summarize_sessions(events: list[RelayEvent], *, limit: int = 50) -> list[dict[str, Any]]:
    """One row per session, most recently active first."""
    rows: dict[str, dict[str, Any]] = {}
    for event in events:
        meta = event.metadata
        at = meta.timestamp.isoformat()
        row = rows.setdefault(
            str(meta.session_id),
            {
                "session_id": str(meta.session_id),
                "project_id": meta.project_id,
                "agent_id": None,
                "trace_id": meta.trace_id,
                "started_at": at,
                "last_event_at": at,
                "event_count": 0,
                "turns": 0,
                "errors": 0,
                "ended": False,
            },
        )
        row["event_count"] += 1
        row["started_at"], row["last_event_at"] = min(row["started_at"], at), max(row["last_event_at"], at)
        if event.type == EventType.SESSION_STARTED:
            row["agent_id"] = event.payload.get("agent_id")
        elif event.type == EventType.TURN_STARTED:
            row["turns"] += 1
        elif event.type == EventType.SESSION_ERROR:
            row["errors"] += 1
        elif event.type == EventType.SESSION_ENDED:
            row["ended"] = True
    return sorted(rows.values(), key=lambda r: r["last_event_at"], reverse=True)[:limit]


def build_audit_trail(events: list[RelayEvent], *, limit: int = 100) -> list[dict[str, Any]]:
    """One entry per approval: what was asked, the decision, and whether the change was saved.

    ``decision`` is ``pending`` / ``granted`` / ``rejected``; ``via`` is ``approval`` (a proposed
    action the user confirmed) or ``form_submit``; ``outcome`` is ``saved`` / ``unverified`` /
    ``failed`` once the commit ran. Relay has no end-user identity yet, so entries identify the
    session, not a person.
    """
    entries: dict[str, dict[str, Any]] = {}
    for event in sorted(events, key=lambda e: (e.metadata.timestamp, e.metadata.sequence)):
        payload, meta = event.payload, event.metadata
        approval_id = payload.get("approval_id")
        if not approval_id:
            continue
        if event.type == EventType.ERROR and payload.get("message") != "commit_failed":
            continue
        at = meta.timestamp.isoformat()
        entry = entries.setdefault(
            str(approval_id),
            {
                "approval_id": str(approval_id),
                "session_id": str(meta.session_id),
                "trace_id": meta.trace_id,
                "tool_name": payload.get("tool_name"),
                "summary": None,
                "arguments": None,
                "requested_at": None,
                "decision": "pending",
                "via": None,
                "decided_at": None,
                "outcome": None,
                "completed_at": None,
                "commit_id": None,
                "error": None,
            },
        )
        entry["tool_name"] = entry["tool_name"] or payload.get("tool_name")
        if event.type == EventType.APPROVAL_REQUESTED:
            entry.update(requested_at=at, summary=payload.get("summary"), arguments=payload.get("arguments"))
        elif event.type == EventType.APPROVAL_GRANTED:
            entry.update(decision="granted", decided_at=at, via=str(payload.get("via") or "approval"))
        elif event.type == EventType.APPROVAL_REJECTED:
            entry.update(decision="rejected", decided_at=at, via="approval")
        elif event.type == EventType.COMMIT_VERIFIED:
            entry.update(
                outcome="saved" if payload.get("verified") else "unverified",
                completed_at=at,
                commit_id=payload.get("commit_id"),
            )
        else:  # ERROR commit_failed
            entry.update(
                outcome="failed", completed_at=at, commit_id=payload.get("commit_id"), error=payload.get("error")
            )
    ordered = sorted(
        entries.values(),
        key=lambda e: e["completed_at"] or e["decided_at"] or e["requested_at"] or "",
        reverse=True,
    )
    return ordered[:limit]
