"""What the event log is allowed to keep.

Redaction applies only to the stored copy of an event (timeline, inspector, audit trail); the
live stream to the app is untouched. Modes (``RELAY_EVENT_STORE_REDACT``, comma-separated):

- ``text``: what people said and what the assistant answered (transcripts, responses).
- ``data``: business data — tool arguments and results, UI action payloads (tables, charts,
  forms), app state, and the details of approvals. Names, ids, statuses and errors are kept, so
  metrics, timings and the audit trail's who/what/when still work.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable

from relay_sdk import RelayEvent

REDACTED = "[redacted]"
MODES = ("text", "data")

_TEXT_PREFIXES = ("TRANSCRIPT_", "RESPONSE_", "HEARD_TEXT_")
_TEXT_KEYS = {"text", "generated_text", "heard_text", "delta"}
_DATA_PREFIXES = ("TOOL_CALL_", "ACTION_", "STATE_", "APPROVAL_", "COMMIT_", "APP_")
# Kept on data events; every other key is replaced (so new payload fields are private by default).
_DATA_KEEP = {
    "name", "action", "action_id", "approval_id", "tool_name", "commit_id", "form_id", "verified", "via",
    "lifecycle_stage", "error", "code", "message", "reason", "status", "ok", "version", "based_on_version",
    "end_user_id",
}  # fmt: skip


def modes_from_env() -> frozenset[str]:
    raw = os.environ.get("RELAY_EVENT_STORE_REDACT", "")
    chosen = {part.strip().lower() for part in raw.split(",") if part.strip()}
    unknown = chosen - set(MODES)
    if unknown:
        raise ValueError(f"RELAY_EVENT_STORE_REDACT: unknown mode(s) {sorted(unknown)}; use {', '.join(MODES)}")
    return frozenset(chosen)


def redactor(modes: Iterable[str]) -> Callable[[RelayEvent], RelayEvent] | None:
    """A function producing the copy to store, or ``None`` when nothing is redacted."""
    active = frozenset(modes)
    if not active:
        return None

    def redact_event(event: RelayEvent) -> RelayEvent:
        kind = event.type.value
        if "text" in active and kind.startswith(_TEXT_PREFIXES):
            payload = {k: REDACTED if k in _TEXT_KEYS and isinstance(v, str) else v for k, v in event.payload.items()}
        elif "data" in active and kind.startswith(_DATA_PREFIXES):
            payload = {k: v if k in _DATA_KEEP else REDACTED for k, v in event.payload.items()}
        else:
            return event
        return event.model_copy(update={"payload": payload})

    return redact_event
