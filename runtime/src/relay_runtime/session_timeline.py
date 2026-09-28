"""Rebuild session narratives from append-only RP event logs (PRD §14.2)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from relay_protocol import EventType
from relay_sdk import RelayEvent


def build_session_timeline(events: list[RelayEvent]) -> dict[str, Any]:
    """Join events, metrics, and TRACE_LINK spans into a stakeholder-friendly timeline."""
    if not events:
        return {
            "trace_id": None,
            "event_count": 0,
            "turns": [],
            "metrics": [],
            "spans": [],
            "waterfall_ms": {},
            "hitl": [],
        }

    ordered = sorted(events, key=lambda e: e.metadata.sequence)
    trace_id = next((e.metadata.trace_id for e in ordered if e.metadata.trace_id), None)

    metrics: list[dict[str, Any]] = []
    spans: list[dict[str, Any]] = []
    hitl: list[dict[str, Any]] = []

    for event in ordered:
        if event.type == EventType.METRIC:
            metrics.append(
                {
                    "sequence": event.metadata.sequence,
                    "turn_id": event.metadata.turn_id,
                    "name": event.payload.get("name"),
                    "value": event.payload.get("value"),
                    "details": event.payload.get("details"),
                }
            )
        if event.type == EventType.TRACE_LINK:
            spans.append(
                {
                    "sequence": event.metadata.sequence,
                    "turn_id": event.metadata.turn_id,
                    "tool_call_id": event.metadata.tool_call_id,
                    **event.payload,
                }
            )
        if event.type in (
            EventType.APPROVAL_REQUESTED,
            EventType.APPROVAL_GRANTED,
            EventType.APPROVAL_REJECTED,
            EventType.COMMIT_STARTED,
            EventType.COMMIT_VERIFIED,
        ):
            hitl.append(
                {
                    "type": event.type.value,
                    "sequence": event.metadata.sequence,
                    "correlation_id": event.metadata.correlation_id,
                    "payload": dict(event.payload),
                }
            )

    turns = reconstruct_turns(ordered)
    waterfall = _aggregate_waterfall(metrics)

    return {
        "trace_id": trace_id,
        "event_count": len(ordered),
        "turns": turns,
        "metrics": metrics,
        "spans": spans,
        "waterfall_ms": waterfall,
        "hitl": hitl,
    }


def reconstruct_turns(events: list[RelayEvent]) -> list[dict[str, Any]]:
    """Group events by turn_id with ordered type trail."""
    by_turn: dict[str, list[RelayEvent]] = defaultdict(list)
    for event in events:
        tid = event.metadata.turn_id
        if tid:
            by_turn[tid].append(event)

    turns: list[dict[str, Any]] = []
    for turn_id, turn_events in by_turn.items():
        turn_events.sort(key=lambda e: e.metadata.sequence)
        types = [e.type.value for e in turn_events]
        user_text = _first_payload(turn_events, EventType.TRANSCRIPT_FINAL, "text")
        assistant_text = _first_payload(turn_events, EventType.RESPONSE_COMPLETED, "text")
        heard = _first_payload(turn_events, EventType.HEARD_TEXT_COMMITTED, "heard_text")
        tools = [
            e.payload.get("name")
            for e in turn_events
            if e.type
            in (EventType.TOOL_CALL_STARTED, EventType.TOOL_CALL_COMPLETED, EventType.TOOL_CALL_FAILED)
        ]
        turns.append(
            {
                "turn_id": turn_id,
                "event_types": types,
                "user_text": user_text,
                "assistant_text": assistant_text,
                "heard_text": heard,
                "tool_names": [t for t in tools if t],
            }
        )
    turn_start_seq: dict[str, int] = {}
    for event in events:
        tid = event.metadata.turn_id
        if tid:
            turn_start_seq[tid] = min(turn_start_seq.get(tid, event.metadata.sequence), event.metadata.sequence)
    turns.sort(key=lambda t: turn_start_seq.get(t["turn_id"], 0))
    return turns


def reconstruct_turn_narrative(events: list[RelayEvent], turn_id: str) -> dict[str, Any] | None:
    timeline = build_session_timeline(events)
    for turn in timeline["turns"]:
        if turn["turn_id"] == turn_id:
            return turn
    return None


def _first_payload(events: list[RelayEvent], event_type: EventType, key: str) -> str | None:
    for event in events:
        if event.type == event_type:
            val = event.payload.get(key)
            return str(val) if val is not None else None
    return None


def _aggregate_waterfall(metrics: list[dict[str, Any]]) -> dict[str, float]:
    """Last value wins per metric name (POC tuning view)."""
    out: dict[str, float] = {}
    for row in metrics:
        name = row.get("name")
        value = row.get("value")
        if isinstance(name, str) and isinstance(value, (int, float)):
            out[name] = float(value)
    return out
