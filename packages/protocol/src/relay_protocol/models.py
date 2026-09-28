"""Pydantic models for RP envelopes (PRD §8.2)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from relay_protocol.events import EventType, PROTOCOL_VERSION


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RelayEventMetadata(BaseModel):
    """Canonical metadata fields (§8.2). Core subset required on every event."""

    protocol_version: str = Field(default=PROTOCOL_VERSION)
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    conversation_id: str | None = None
    turn_id: str | None = None
    response_id: str | None = None
    tool_call_id: str | None = None
    trace_id: str | None = None
    correlation_id: str | None = None
    sequence: int = Field(ge=0)
    timestamp: datetime = Field(default_factory=_utc_now)
    source: str = Field(min_length=1)
    tenant_id: str | None = None
    project_id: str | None = None
    state_version: int | None = Field(default=None, ge=0)
    based_on_version: int | None = Field(default=None, ge=0)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        raise TypeError("timestamp must be datetime or ISO-8601 string")


class RelayEvent(BaseModel):
    """Top-level RP event: type + metadata + payload."""

    type: EventType
    metadata: RelayEventMetadata
    payload: dict[str, Any] = Field(default_factory=dict)


def minimal_payload_for(event_type: EventType) -> dict[str, Any]:
    """Minimal valid payload per event family for contract round-trips."""
    family_payloads: dict[EventType, dict[str, Any]] = {
        EventType.SESSION_STARTED: {"transport": "dev"},
        EventType.SESSION_READY: {"ready": True},
        EventType.SESSION_ENDED: {"reason": "client_disconnect"},
        EventType.SESSION_ERROR: {"code": "internal", "message": "error"},
        EventType.TURN_STARTED: {},
        EventType.USER_SPEECH_STARTED: {},
        EventType.USER_SPEECH_ENDED: {},
        EventType.TURN_PROCESSING: {},
        EventType.TURN_COMPLETED: {},
        EventType.TRANSCRIPT_DELTA: {"text": "hel", "is_final": False},
        EventType.TRANSCRIPT_FINAL: {"text": "hello", "is_final": True},
        EventType.RESPONSE_STARTED: {},
        EventType.RESPONSE_DELTA: {"text": "hi"},
        EventType.RESPONSE_COMPLETED: {"text": "hi there"},
        EventType.RESPONSE_CANCELLED: {"reason": "interrupt"},
        EventType.SPEECH_STARTED: {},
        EventType.SPEECH_PROGRESS: {"position_ms": 0, "heard_text": ""},
        EventType.SPEECH_STOPPED: {},
        EventType.INTERRUPTION_DETECTED: {},
        EventType.RESPONSE_INTERRUPTED: {
            "generated_text": "full",
            "heard_text": "heard",
        },
        EventType.HEARD_TEXT_COMMITTED: {"text": "heard", "generated_text": "full"},
        EventType.TOOL_CALL_STARTED: {"name": "tool"},
        EventType.TOOL_CALL_PROGRESS: {"progress": 0.5},
        EventType.TOOL_CALL_COMPLETED: {"result": {}},
        EventType.TOOL_CALL_FAILED: {"error": "timeout"},
        EventType.ACTION_REQUESTED: {"action": "noop"},
        EventType.ACTION_APPLIED: {"action": "noop"},
        EventType.ACTION_FAILED: {"action": "noop", "reason": "unknown"},
        EventType.STATE_SNAPSHOT: {"state": {}},
        EventType.STATE_DELTA: {"patch": []},
        EventType.STATE_VERSION_ADVANCED: {"state_version": 1},
        EventType.STATE_CONFLICT: {"expected_version": 1, "actual_version": 2},
        EventType.ACTIVITY_STARTED: {"activity_id": "a1"},
        EventType.ACTIVITY_PROGRESS: {"activity_id": "a1", "progress": 0.1},
        EventType.ACTIVITY_COMPLETED: {"activity_id": "a1"},
        EventType.APPROVAL_REQUESTED: {"approval_id": "ap1"},
        EventType.APPROVAL_GRANTED: {"approval_id": "ap1"},
        EventType.APPROVAL_REJECTED: {"approval_id": "ap1"},
        EventType.COMMIT_STARTED: {"commit_id": "c1"},
        EventType.COMMIT_VERIFIED: {"commit_id": "c1", "verified": True},
        EventType.TRACE_LINK: {"trace_id": "trace-1", "span_id": "span-1"},
        EventType.METRIC: {"name": "latency_ms", "value": 1.0},
        EventType.WARNING: {"message": "warn"},
        EventType.ERROR: {"message": "err", "code": "E001"},
    }
    return dict(family_payloads.get(event_type, {}))
