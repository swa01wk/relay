"""Turn the Relay event stream into Prometheus metrics.

Subscribe ``on_event`` to every session (``event_gateway.subscribe("*", bridge.on_event)``) and
serve ``render()`` at ``/metrics``. Everything is derived from events that already exist, so the
runtime needs no instrumentation.

Label values come from models and clients, so each label is capped (overflow → ``other``) to keep
series cardinality bounded.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from relay_protocol import EventType
from relay_runtime.model_usage import MODEL_USAGE_METRIC
from relay_sdk import RelayEvent

_LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0)
_MAX_LABEL_VALUES = 100
_MAX_OPEN_SPANS = 10_000

# METRIC event name (milliseconds) → histogram attribute
_MS_METRICS = {
    "model.ttft_ms": "model_ttft",
    "voice.first_tts_byte_ms": "voice_first_tts_byte",
    "voice.user_stop_to_first_audio_ms": "voice_response",
    "turn.endpointing_delay_ms": "endpointing_delay",
    "transport.connect_latency_ms": "transport_connect",
}


class _Bounded:
    """Remember up to N distinct label values; anything beyond becomes ``other``."""

    def __init__(self, limit: int = _MAX_LABEL_VALUES) -> None:
        self._seen: set[str] = set()
        self._limit = limit

    def __call__(self, value: Any) -> str:
        text = str(value or "unknown")[:80]
        if text in self._seen:
            return text
        if len(self._seen) >= self._limit:
            return "other"
        self._seen.add(text)
        return text


class _OpenSpans:
    """Start times keyed by id, bounded so unfinished turns/tool calls cannot leak memory."""

    def __init__(self) -> None:
        self._starts: OrderedDict[str, tuple[datetime, str]] = OrderedDict()

    def start(self, key: str, at: datetime, label: str = "") -> None:
        self._starts[key] = (at, label)
        while len(self._starts) > _MAX_OPEN_SPANS:
            self._starts.popitem(last=False)

    def finish(self, key: str, at: datetime) -> tuple[float, str] | None:
        started = self._starts.pop(key, None)
        if started is None:
            return None
        return max(0.0, (at - started[0]).total_seconds()), started[1]


class PrometheusMetricsBridge:
    def __init__(
        self,
        *,
        registry: CollectorRegistry | None = None,
        agent_for_session: Callable[[str], str | None] | None = None,
        active_sessions: Callable[[], int] | None = None,
    ) -> None:
        self.registry = registry or CollectorRegistry()
        self._agent_for_session = agent_for_session or (lambda _session_id: None)
        self._agent, self._tool, self._model, self._action, self._code = (_Bounded() for _ in range(5))
        self._turns, self._tools = _OpenSpans(), _OpenSpans()
        self._failed_turns: OrderedDict[str, None] = OrderedDict()
        r = self.registry

        self.sessions = Counter("relay_sessions", "Sessions started and ended", ["agent", "event"], registry=r)
        if active_sessions is not None:
            Gauge("relay_sessions_active", "Sessions currently held by this gateway", registry=r).set_function(
                active_sessions
            )
        self.turns = Counter("relay_turns", "Turns by outcome", ["agent", "outcome"], registry=r)
        self.turn_duration = Histogram(
            "relay_turn_duration_seconds", "Turn start to completion", ["agent"], buckets=_LATENCY_BUCKETS, registry=r
        )
        self.session_errors = Counter("relay_session_errors", "SESSION_ERROR events", ["code"], registry=r)
        self.interruptions = Counter("relay_interruptions", "User barge-ins while the agent spoke", registry=r)

        self.model_calls = Counter("relay_model_calls", "Model completions", ["model"], registry=r)
        self.model_tokens = Counter("relay_model_tokens", "Model tokens", ["model", "kind"], registry=r)
        self.model_cost = Counter(
            "relay_model_cost_usd", "Model cost in USD (needs RELAY_MODEL_PRICES)", ["model"], registry=r
        )
        self.model_ttft = Histogram(
            "relay_model_ttft_seconds", "Time to first model token", buckets=_LATENCY_BUCKETS, registry=r
        )

        self.tool_calls = Counter("relay_tool_calls", "Tool calls by outcome", ["tool", "outcome"], registry=r)
        self.tool_duration = Histogram(
            "relay_tool_duration_seconds", "Tool call duration", ["tool"], buckets=_LATENCY_BUCKETS, registry=r
        )
        self.ui_actions = Counter(
            "relay_ui_actions", "UI actions requested of / acknowledged by the app", ["action", "outcome"], registry=r
        )
        self.approvals = Counter("relay_approvals", "Approval requests and decisions", ["outcome"], registry=r)
        self.commits = Counter("relay_commits", "Approved changes saved or failed", ["tool", "outcome"], registry=r)

        self.voice_response = Histogram(
            "relay_voice_response_seconds", "User stopped speaking → first agent audio",
            buckets=_LATENCY_BUCKETS, registry=r,
        )
        self.voice_first_tts_byte = Histogram(
            "relay_voice_first_tts_byte_seconds", "Text ready → first synthesized audio",
            buckets=_LATENCY_BUCKETS, registry=r,
        )
        self.endpointing_delay = Histogram(
            "relay_voice_endpointing_delay_seconds", "End-of-speech detection delay",
            buckets=_LATENCY_BUCKETS, registry=r,
        )
        self.transport_connect = Histogram(
            "relay_transport_connect_seconds", "WebRTC connection setup", buckets=_LATENCY_BUCKETS, registry=r
        )

    def render(self) -> tuple[bytes, str]:
        """Exposition body and content type for the scrape endpoint."""
        return generate_latest(self.registry), CONTENT_TYPE_LATEST

    def _agent_label(self, session_id: str) -> str:
        return self._agent(self._agent_for_session(session_id) or "default")

    async def on_event(self, event: RelayEvent) -> None:
        kind, payload, meta = event.type, event.payload, event.metadata
        session_id = str(meta.session_id)

        if kind == EventType.SESSION_STARTED:
            self.sessions.labels(self._agent_label(session_id), "started").inc()
        elif kind == EventType.SESSION_ENDED:
            self.sessions.labels(self._agent_label(session_id), "ended").inc()
        elif kind == EventType.TURN_STARTED and meta.turn_id:
            self._turns.start(meta.turn_id, meta.timestamp)
        elif kind == EventType.TURN_COMPLETED and meta.turn_id:
            agent = self._agent_label(session_id)
            failed = meta.turn_id in self._failed_turns
            self._failed_turns.pop(meta.turn_id, None)
            self.turns.labels(agent, "failed" if failed else "completed").inc()
            finished = self._turns.finish(meta.turn_id, meta.timestamp)
            if finished is not None:
                self.turn_duration.labels(agent).observe(finished[0])
        elif kind == EventType.SESSION_ERROR:
            code = str(payload.get("code") or "unknown")
            self.session_errors.labels(self._code(code)).inc()
            if code == "turn_failed" and meta.turn_id:
                self._failed_turns[meta.turn_id] = None
                while len(self._failed_turns) > _MAX_OPEN_SPANS:
                    self._failed_turns.popitem(last=False)
        elif kind == EventType.INTERRUPTION_DETECTED:
            self.interruptions.inc()
        elif kind == EventType.METRIC:
            self._on_metric(payload)
        elif kind == EventType.TOOL_CALL_STARTED and meta.tool_call_id:
            self._tools.start(meta.tool_call_id, meta.timestamp, self._tool(payload.get("name")))
        elif kind in (EventType.TOOL_CALL_COMPLETED, EventType.TOOL_CALL_FAILED):
            outcome = "completed" if kind == EventType.TOOL_CALL_COMPLETED else "failed"
            finished = self._tools.finish(meta.tool_call_id, meta.timestamp) if meta.tool_call_id else None
            tool = finished[1] if finished else self._tool(payload.get("name"))
            self.tool_calls.labels(tool, outcome).inc()
            if finished is not None:
                self.tool_duration.labels(tool).observe(finished[0])
        elif kind == EventType.ACTION_REQUESTED:
            self.ui_actions.labels(self._action(payload.get("action")), "requested").inc()
        elif kind == EventType.ACTION_APPLIED:
            self.ui_actions.labels(self._action(payload.get("action")), "applied").inc()
        elif kind == EventType.ACTION_FAILED:
            self.ui_actions.labels(self._action(payload.get("action")), "failed").inc()
        elif kind == EventType.APPROVAL_REQUESTED:
            self.approvals.labels("requested").inc()
        elif kind == EventType.APPROVAL_GRANTED:
            self.approvals.labels("form_submitted" if payload.get("via") == "form_submit" else "granted").inc()
        elif kind == EventType.APPROVAL_REJECTED:
            self.approvals.labels("rejected").inc()
        elif kind == EventType.COMMIT_VERIFIED:
            outcome = "saved" if payload.get("verified") else "unverified"
            self.commits.labels(self._tool(payload.get("tool_name")), outcome).inc()
        elif kind == EventType.ERROR and payload.get("message") == "commit_failed":
            self.commits.labels(self._tool(payload.get("tool_name")), "failed").inc()

    def _on_metric(self, payload: dict[str, Any]) -> None:
        name, value = payload.get("name"), payload.get("value")
        if name == MODEL_USAGE_METRIC:
            details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
            model = self._model(details.get("model"))
            self.model_calls.labels(model).inc()
            cached = int(details.get("cached_input_tokens") or 0)
            self.model_tokens.labels(model, "input").inc(max(0, int(details.get("input_tokens") or 0) - cached))
            self.model_tokens.labels(model, "cached_input").inc(cached)
            self.model_tokens.labels(model, "output").inc(int(details.get("output_tokens") or 0))
            if isinstance(details.get("cost_usd"), (int, float)):
                self.model_cost.labels(model).inc(float(details["cost_usd"]))
            return
        histogram = _MS_METRICS.get(str(name))
        if histogram and isinstance(value, (int, float)) and value >= 0:
            getattr(self, histogram).observe(float(value) / 1000.0)
