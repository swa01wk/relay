"""Turn the Relay event stream into OpenTelemetry traces.

One trace per session, using Relay's own ``trace_id`` so logs, the session timeline and the
trace line up. Spans:

    relay.session                      SESSION_STARTED → SESSION_ENDED
      relay.turn                       TURN_STARTED → TURN_COMPLETED   (ERROR on turn_failed)
        relay.tool <name>              TOOL_CALL_STARTED → COMPLETED / FAILED
        events: model.first_token, model.usage (tokens, cost), interruption
      relay.approval <tool>            APPROVAL_REQUESTED → GRANTED / REJECTED (+ commit result)

Spans carry names, counts, durations and status only — never message text, tool arguments or
tool results — so traces are safe to ship to a shared monitoring backend.

Subscribe ``on_event`` with ``event_gateway.subscribe("*", bridge.on_event)``.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Span, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.id_generator import RandomIdGenerator
from opentelemetry.trace import Status, StatusCode

from relay_protocol import EventType
from relay_runtime.model_usage import MODEL_USAGE_METRIC
from relay_sdk import RelayEvent

_MAX_OPEN = 10_000


class RelayIdGenerator(RandomIdGenerator):
    """Lets the bridge choose the trace id of the next root span (Relay's session trace id)."""

    def __init__(self) -> None:
        self.next_trace_id: int | None = None

    def generate_trace_id(self) -> int:
        chosen, self.next_trace_id = self.next_trace_id, None
        return chosen or super().generate_trace_id()
        

def tracer_provider_from_env() -> TracerProvider | None:
    """A provider exporting OTLP/HTTP when ``OTEL_EXPORTER_OTLP_ENDPOINT`` (or the traces-specific
    variable) is set; otherwise ``None`` (tracing off). Other standard ``OTEL_*`` variables apply."""
    if not (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")):
        return None
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    resource = Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", "relay-gateway")})
    provider = TracerProvider(resource=resource, id_generator=RelayIdGenerator())
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    return provider


def _ns(at: datetime) -> int:
    return int(at.timestamp() * 1_000_000_000)


def _trace_id_int(value: str | None) -> int | None:
    try:
        return int(str(value).replace("-", ""), 16) or None
    except (TypeError, ValueError):
        return None


class _Open:
    """Open spans by key, bounded; evicted spans are ended so they still export."""

    def __init__(self) -> None:
        self._spans: OrderedDict[str, Span] = OrderedDict()

    def put(self, key: str, span: Span) -> None:
        self._spans[key] = span
        while len(self._spans) > _MAX_OPEN:
            _key, evicted = self._spans.popitem(last=False)
            evicted.set_attribute("relay.evicted", True)
            evicted.end()

    def get(self, key: str | None) -> Span | None:
        return self._spans.get(key) if key else None

    def pop(self, key: str | None) -> Span | None:
        return self._spans.pop(key, None) if key else None


class OtelTraceBridge:
    def __init__(
        self,
        provider: TracerProvider,
        *,
        agent_for_session: Callable[[str], str | None] | None = None,
    ) -> None:
        self._provider = provider
        self._tracer = provider.get_tracer("relay")
        self._ids = provider.id_generator if isinstance(provider.id_generator, RelayIdGenerator) else None
        self._agent_for_session = agent_for_session or (lambda _session_id: None)
        self._sessions, self._turns, self._tools, self._approvals = _Open(), _Open(), _Open(), _Open()

    def shutdown(self) -> None:
        """Flush and stop the exporter (call on gateway shutdown)."""
        self._provider.shutdown()

    def _child(self, name: str, parent: Span | None, at: datetime, attributes: dict[str, Any]) -> Span:
        context = trace.set_span_in_context(parent) if parent is not None else None
        return self._tracer.start_span(name, context=context, start_time=_ns(at), attributes=attributes)

    def _session_span(self, event: RelayEvent) -> Span:
        """The session's root span; created on first sight (e.g. a session older than the gateway)."""
        session_id = str(event.metadata.session_id)
        span = self._sessions.get(session_id)
        if span is None:
            if self._ids is not None:
                self._ids.next_trace_id = _trace_id_int(event.metadata.trace_id)
            span = self._tracer.start_span(
                "relay.session",
                start_time=_ns(event.metadata.timestamp),
                attributes={
                    "relay.session_id": session_id,
                    "relay.agent": self._agent_for_session(session_id) or "default",
                },
            )
            self._sessions.put(session_id, span)
        return span

    async def on_event(self, event: RelayEvent) -> None:
        kind, payload, meta = event.type, event.payload, event.metadata
        at = meta.timestamp

        if kind == EventType.SESSION_STARTED:
            self._session_span(event)
        elif kind == EventType.SESSION_ENDED:
            span = self._sessions.pop(str(meta.session_id))
            if span is not None:
                span.end(end_time=_ns(at))
        elif kind == EventType.TURN_STARTED and meta.turn_id:
            self._turns.put(
                meta.turn_id,
                self._child("relay.turn", self._session_span(event), at, {"relay.turn_id": meta.turn_id}),
            )
        elif kind == EventType.TURN_COMPLETED:
            span = self._turns.pop(meta.turn_id)
            if span is not None:
                span.end(end_time=_ns(at))
        elif kind == EventType.SESSION_ERROR:
            span = self._turns.get(meta.turn_id)
            if span is not None:
                span.set_status(Status(StatusCode.ERROR, str(payload.get("code") or "error")))
                span.set_attribute("relay.error_code", str(payload.get("code") or "unknown"))
        elif kind == EventType.TRANSCRIPT_FINAL:
            span = self._turns.get(meta.turn_id)
            if span is not None:
                span.set_attribute("relay.input", "voice" if meta.source == "speech_to_text" else "text")
        elif kind == EventType.INTERRUPTION_DETECTED:
            span = self._turns.get(meta.turn_id)
            if span is not None:
                span.add_event("interruption", timestamp=_ns(at))
        elif kind == EventType.METRIC:
            self._on_metric(event)
        elif kind == EventType.TOOL_CALL_STARTED and meta.tool_call_id:
            name = str(payload.get("name") or "unknown")
            parent = self._turns.get(meta.turn_id) or self._session_span(event)
            self._tools.put(meta.tool_call_id, self._child(f"relay.tool {name}", parent, at, {"relay.tool": name}))
        elif kind in (EventType.TOOL_CALL_COMPLETED, EventType.TOOL_CALL_FAILED):
            span = self._tools.pop(meta.tool_call_id)
            if span is not None:
                if kind == EventType.TOOL_CALL_FAILED:
                    span.set_status(Status(StatusCode.ERROR, str(payload.get("error") or "failed")))
                span.end(end_time=_ns(at))
        elif kind == EventType.APPROVAL_REQUESTED and payload.get("approval_id"):
            tool = str(payload.get("tool_name") or "unknown")
            self._approvals.put(
                str(payload["approval_id"]),
                self._child(f"relay.approval {tool}", self._session_span(event), at, {"relay.tool": tool}),
            )
        elif kind in (EventType.APPROVAL_GRANTED, EventType.APPROVAL_REJECTED):
            approval_id = str(payload.get("approval_id") or "")
            span = self._approvals.get(approval_id)
            if span is None and kind == EventType.APPROVAL_GRANTED and approval_id:
                # Saved forms are granted without a prior request event.
                tool = str(payload.get("tool_name") or "unknown")
                span = self._child(f"relay.approval {tool}", self._session_span(event), at, {"relay.tool": tool})
                self._approvals.put(approval_id, span)
            if span is not None:
                decision = "rejected" if kind == EventType.APPROVAL_REJECTED else str(payload.get("via") or "granted")
                span.set_attribute("relay.decision", decision)
                if kind == EventType.APPROVAL_REJECTED:
                    self._approvals.pop(approval_id)
                    span.end(end_time=_ns(at))
        elif kind == EventType.COMMIT_VERIFIED or (kind == EventType.ERROR and payload.get("message") == "commit_failed"):
            span = self._approvals.pop(str(payload.get("approval_id") or ""))
            if span is not None:
                saved = kind == EventType.COMMIT_VERIFIED and bool(payload.get("verified"))
                span.set_attribute("relay.saved", saved)
                if not saved:
                    span.set_status(Status(StatusCode.ERROR, str(payload.get("error") or "not verified")))
                span.end(end_time=_ns(at))

    def _on_metric(self, event: RelayEvent) -> None:
        span = self._turns.get(event.metadata.turn_id)
        if span is None:
            return
        name, value, at = event.payload.get("name"), event.payload.get("value"), _ns(event.metadata.timestamp)
        if name == MODEL_USAGE_METRIC and isinstance(event.payload.get("details"), dict):
            details = event.payload["details"]
            attributes = {
                f"relay.model.{key}": details[key]
                for key in ("model", "input_tokens", "output_tokens", "cached_input_tokens", "cost_usd")
                if details.get(key) is not None
            }
            span.add_event("model.usage", attributes=attributes, timestamp=at)
        elif name == "model.ttft_ms" and isinstance(value, (int, float)):
            span.add_event("model.first_token", attributes={"relay.ttft_ms": float(value)}, timestamp=at)
        elif name == "voice.user_stop_to_first_audio_ms" and isinstance(value, (int, float)):
            span.set_attribute("relay.voice.response_ms", float(value))
