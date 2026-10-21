"""What a project's assistant has been doing: its sessions, one session in full, and usage.

The customer-facing counterpart of ``AdminService``: the same stored events, filtered to one
project. Callers check that the account owns the project first (``ProjectService.owned``); a
session of another project looks exactly like a missing one.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from relay_gateway.core.errors import NotFound
from relay_gateway.repositories.event_repository import EventRepository
from relay_gateway.repositories.session_repository import SessionRepository
from relay_protocol import EventType
from relay_runtime.model_usage import MODEL_USAGE_METRIC, summarize_usage
from relay_runtime.session_audit import build_audit_trail
from relay_runtime.session_timeline import build_session_timeline
from relay_sdk import RelayEvent

# Usage reads at most this many events; a busier period is reported as ``truncated``.
USAGE_EVENT_LIMIT = 20_000
_USAGE_EVENT_TYPES = (
    EventType.SESSION_STARTED,
    EventType.TURN_STARTED,
    EventType.SESSION_ERROR,
    EventType.METRIC,
    EventType.TOOL_CALL_STARTED,
    EventType.TOOL_CALL_COMPLETED,
    EventType.TOOL_CALL_FAILED,
)


class ProjectActivityService:
    def __init__(self, sessions: SessionRepository, events: EventRepository) -> None:
        self._sessions = sessions
        self._events = events

    async def list_sessions(self, project_id: str, *, limit: int) -> list[dict[str, Any]]:
        rows = await self._events.session_summaries(limit=limit, project_id=project_id)
        return [
            {**{k: v for k, v in row.items() if k != "project_id"}, "live": self._sessions.is_live(row["session_id"])}
            for row in rows
        ]

    async def session_detail(self, project_id: str, session_id: str) -> dict[str, Any]:
        events = await self._events.for_session(session_id)
        if not events or events[0].metadata.project_id != project_id:
            raise NotFound("session not found")
        timeline = build_session_timeline(events)
        started = next((e for e in events if e.type == EventType.SESSION_STARTED), None)
        return {
            "session_id": session_id,
            "agent_id": started.payload.get("agent_id") if started else None,
            "started_at": events[0].metadata.timestamp.isoformat(),
            "last_event_at": events[-1].metadata.timestamp.isoformat(),
            "live": self._sessions.is_live(session_id),
            "turns": timeline["turns"],
            "usage": timeline["usage"],
            "errors": _errors(events),
            "approvals": build_audit_trail(events),
        }

    async def usage(self, project_id: str, *, days: int) -> dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        events = await self._events.newest_of_types(
            _USAGE_EVENT_TYPES, limit=USAGE_EVENT_LIMIT, project_id=project_id, since=since
        )
        return {
            "days": days,
            "since": since.isoformat(),
            "truncated": len(events) >= USAGE_EVENT_LIMIT,
            **summarize_project_usage(events),
        }


def _errors(events: list[RelayEvent]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for event in events:
        if event.type == EventType.SESSION_ERROR:
            kind, detail = event.payload.get("code"), event.payload.get("message")
        elif event.type == EventType.TOOL_CALL_FAILED:
            kind, detail = f"tool_failed:{event.payload.get('name')}", event.payload.get("error")
        else:
            continue
        out.append(
            {"at": event.metadata.timestamp.isoformat(), "turn_id": event.metadata.turn_id, "code": kind, "message": detail}
        )
    return out


def _counts() -> dict[str, Any]:
    return {"sessions": 0, "turns": 0, "errors": 0, "usage_rows": []}


def summarize_project_usage(events: list[RelayEvent]) -> dict[str, Any]:
    """Totals, per day (UTC), per agent, per model and per tool over a project's events."""
    agent_of: dict[str, str | None] = {}
    for event in events:
        if event.type == EventType.SESSION_STARTED:
            agent_of[event.metadata.session_id] = event.payload.get("agent_id")

    total, by_day = _counts(), defaultdict(_counts)
    by_agent: dict[str | None, dict[str, Any]] = defaultdict(_counts)
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tool_started: dict[str, datetime] = {}
    tools: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "failures": 0, "durations_ms": []})

    for event in sorted(events, key=lambda e: e.metadata.timestamp):
        meta = event.metadata
        buckets = (total, by_day[meta.timestamp.date().isoformat()], by_agent[agent_of.get(meta.session_id)])
        if event.type == EventType.SESSION_STARTED:
            for bucket in buckets:
                bucket["sessions"] += 1
        elif event.type == EventType.TURN_STARTED:
            for bucket in buckets:
                bucket["turns"] += 1
        elif event.type == EventType.SESSION_ERROR:
            for bucket in buckets:
                bucket["errors"] += 1
        elif event.type == EventType.METRIC and event.payload.get("name") == MODEL_USAGE_METRIC:
            row = {"name": MODEL_USAGE_METRIC, "details": event.payload.get("details")}
            for bucket in buckets:
                bucket["usage_rows"].append(row)
            details = row["details"] if isinstance(row["details"], dict) else {}
            by_model[str(details.get("model") or "unknown")].append(row)
        elif event.type == EventType.TOOL_CALL_STARTED and meta.tool_call_id:
            tool_started[meta.tool_call_id] = meta.timestamp
        elif event.type in (EventType.TOOL_CALL_COMPLETED, EventType.TOOL_CALL_FAILED):
            tool = tools[str(event.payload.get("name") or "unknown")]
            tool["calls"] += 1
            if event.type == EventType.TOOL_CALL_FAILED:
                tool["failures"] += 1
            began = tool_started.pop(meta.tool_call_id, None) if meta.tool_call_id else None
            if began is not None:
                tool["durations_ms"].append((meta.timestamp - began).total_seconds() * 1000)

    def finish(bucket: dict[str, Any]) -> dict[str, Any]:
        rows = bucket.pop("usage_rows")
        return {**bucket, "model": summarize_usage(rows)}

    return {
        "total": finish(total),
        "by_day": [{"date": day, **finish(bucket)} for day, bucket in sorted(by_day.items())],
        "by_agent": [{"agent_id": agent, **finish(bucket)} for agent, bucket in by_agent.items()],
        "by_model": [{"model": model, **summarize_usage(rows)} for model, rows in sorted(by_model.items())],
        "tools": [
            {
                "name": name,
                "calls": tool["calls"],
                "failures": tool["failures"],
                "avg_ms": round(sum(tool["durations_ms"]) / len(tool["durations_ms"]), 1) if tool["durations_ms"] else None,
                "max_ms": round(max(tool["durations_ms"]), 1) if tool["durations_ms"] else None,
            }
            for name, tool in sorted(tools.items())
        ],
    }
