"""RP-native spans and stage metrics (Phase 10 — complements optional OTLP)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from relay_protocol import EventType, RelayEvent, RelayEventMetadata, minimal_payload_for

PublishFn = Callable[[RelayEvent], Awaitable[None]]
MetadataFn = Callable[[], RelayEventMetadata]

# PRD §14.1 stage names
STAGE_TRANSPORT = "relay.stage.transport"
STAGE_TURN_DETECT = "relay.stage.turn_detection"
STAGE_STT = "relay.stage.stt"
STAGE_MODEL = "relay.stage.model"
STAGE_TOOL = "relay.stage.tool"
STAGE_TTS = "relay.stage.tts"
STAGE_HITL = "relay.stage.hitl"
STAGE_UX = "relay.stage.ux"


async def emit_trace_span(
    *,
    publish: PublishFn | None,
    base_metadata: MetadataFn | None,
    stage: str,
    trace_id: str,
    turn_id: str | None = None,
    tool_call_id: str | None = None,
    parent_span_id: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> str:
    span_id = str(uuid4())
    if publish is None or base_metadata is None:
        return span_id
    meta = base_metadata().model_copy(
        update={
            "turn_id": turn_id,
            "tool_call_id": tool_call_id,
            "trace_id": trace_id,
            "correlation_id": span_id,
        }
    )
    await publish(
        RelayEvent(
            type=EventType.TRACE_LINK,
            metadata=meta,
            payload={
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "stage": stage,
                **(attributes or {}),
            },
        )
    )
    return span_id


async def emit_stage_metric(
    *,
    publish: PublishFn | None,
    base_metadata: MetadataFn | None,
    name: str,
    value_ms: float,
    turn_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    if publish is None or base_metadata is None:
        return
    payload: dict[str, Any] = {"name": name, "value": value_ms}
    if details:
        payload["details"] = details
    await publish(
        RelayEvent(
            type=EventType.METRIC,
            metadata=base_metadata().model_copy(update={"turn_id": turn_id, "source": "observability"}),
            payload=payload,
        )
    )
