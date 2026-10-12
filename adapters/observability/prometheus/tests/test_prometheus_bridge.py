"""Prometheus bridge: metrics derived from a real session's event stream."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from relay_adapter_observability_prometheus import PrometheusMetricsBridge
from relay_protocol import EventType, RelayEvent, RelayEventMetadata
from relay_runtime import (
    AgentRuntime,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    RegistryToolExecutor,
    SessionManager,
    ToolClassification,
    ToolDefinition,
    ToolRegistry,
    ToolUsingAgent,
)
from relay_runtime.ports.model import ModelProvider
from relay_runtime.ports.tools import ToolExecutor


class Tools(ToolExecutor):
    async def execute(self, session_id, *, tool_name, arguments, idempotency_key=None):
        del session_id, arguments, idempotency_key
        return {"deals": [{"id": "DEAL-1"}]}


class Model(ModelProvider):
    """Turn 1: call list_deals, then answer. Turn 2 ('boom'): fail like an upstream 401."""

    async def stream_completion(self, session_id, *, messages, tools=None) -> AsyncIterator[dict[str, Any]]:
        del session_id, tools
        last_user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        if last_user == "boom":
            raise RuntimeError("upstream 401")
        if not [m for m in messages if m.get("role") == "tool"]:
            yield {"type": "tool_calls", "calls": [{"id": "c1", "name": "list_deals", "arguments": "{}"}]}
        else:
            yield {"type": "token", "text": "One deal."}
        yield {"type": "usage", "model": "test-model", "input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 40}

    async def cancel(self, session_id: str) -> None:
        del session_id


@pytest.mark.asyncio
async def test_metrics_from_a_real_session():
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="list_deals", classification=ToolClassification.READ_ONLY,
                                     input_schema={"type": "object", "properties": {}}))
    router = ModelRouter(Model())
    gateway = PersistingEventGateway(MemoryEventStore())
    manager = SessionManager(
        event_gateway=gateway,
        agent_runtime=AgentRuntime(
            model_router=router,
            agent=ToolUsingAgent(router, system_prompt="x", registry=registry),
            tool_executor=RegistryToolExecutor(registry=registry, delegate=Tools()),
            model_prices={"test-model": {"input": 1.0, "output": 2.0, "cached_input": 0.5}},
        ),
        session_lock=None,
        idle_grace_seconds=0,
    )
    bridge = PrometheusMetricsBridge(
        agent_for_session=lambda sid: (manager.get(sid).agent_id if manager.get(sid) else None),
        active_sessions=lambda: len(manager._sessions),
    )
    gateway.subscribe("*", bridge.on_event)

    session, _ = await manager.create_dev_session(project_id="p", agent_id="sales-crm")
    value = bridge.registry.get_sample_value
    assert value("relay_sessions_active") == 1
    await manager.submit_user_text(session.session_id, "list deals")
    await manager.submit_user_text(session.session_id, "boom")
    await manager.end_session(session.session_id)

    assert value("relay_turns_total", {"agent": "sales-crm", "outcome": "completed"}) == 1
    assert value("relay_turns_total", {"agent": "sales-crm", "outcome": "failed"}) == 1
    assert value("relay_turn_duration_seconds_count", {"agent": "sales-crm"}) == 2
    assert value("relay_session_errors_total", {"code": "turn_failed"}) == 1
    assert value("relay_tool_calls_total", {"tool": "list_deals", "outcome": "completed"}) == 1
    assert value("relay_tool_duration_seconds_count", {"tool": "list_deals"}) == 1
    # Two model calls in the first turn (tool round + answer); the failed turn reports none.
    assert value("relay_model_calls_total", {"model": "test-model"}) == 2
    assert value("relay_model_tokens_total", {"model": "test-model", "kind": "input"}) == 120
    assert value("relay_model_tokens_total", {"model": "test-model", "kind": "cached_input"}) == 80
    assert value("relay_model_tokens_total", {"model": "test-model", "kind": "output"}) == 40
    assert value("relay_model_cost_usd_total", {"model": "test-model"}) == pytest.approx(
        2 * (60 * 1.0 + 40 * 0.5 + 20 * 2.0) / 1_000_000
    )
    assert value("relay_sessions_total", {"agent": "sales-crm", "event": "ended"}) == 1
    assert value("relay_sessions_active") == 0

    body, content_type = bridge.render()
    assert content_type.startswith("text/plain") and b"relay_turns_total" in body


def _event(kind: EventType, payload: dict[str, Any], *, at: datetime, **meta: Any) -> RelayEvent:
    return RelayEvent(
        type=kind,
        metadata=RelayEventMetadata(session_id="s", sequence=0, source="test", timestamp=at, **meta),
        payload=payload,
    )


@pytest.mark.asyncio
async def test_durations_approvals_actions_and_label_cap():
    bridge = PrometheusMetricsBridge()
    value = bridge.registry.get_sample_value
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

    await bridge.on_event(_event(EventType.TOOL_CALL_STARTED, {"name": "slow"}, at=t0, tool_call_id="t1"))
    await bridge.on_event(_event(EventType.TOOL_CALL_FAILED, {"name": "slow", "error": "timeout"},
                                 at=t0 + timedelta(seconds=3), tool_call_id="t1"))
    assert value("relay_tool_calls_total", {"tool": "slow", "outcome": "failed"}) == 1
    assert value("relay_tool_duration_seconds_sum", {"tool": "slow"}) == pytest.approx(3.0)

    await bridge.on_event(_event(EventType.METRIC, {"name": "voice.user_stop_to_first_audio_ms", "value": 800}, at=t0))
    assert value("relay_voice_response_seconds_sum") == pytest.approx(0.8)

    for kind, payload in [
        (EventType.APPROVAL_REQUESTED, {}),
        (EventType.APPROVAL_GRANTED, {}),
        (EventType.APPROVAL_GRANTED, {"via": "form_submit"}),
        (EventType.APPROVAL_REJECTED, {}),
        (EventType.COMMIT_VERIFIED, {"tool_name": "update_deal", "verified": True}),
        (EventType.ERROR, {"message": "commit_failed", "tool_name": "update_deal"}),
        (EventType.ACTION_REQUESTED, {"action": "PRESENT_UI"}),
        (EventType.ACTION_APPLIED, {"action": "PRESENT_UI"}),
        (EventType.INTERRUPTION_DETECTED, {}),
    ]:
        await bridge.on_event(_event(kind, payload, at=t0))
    assert value("relay_approvals_total", {"outcome": "granted"}) == 1
    assert value("relay_approvals_total", {"outcome": "form_submitted"}) == 1
    assert value("relay_approvals_total", {"outcome": "rejected"}) == 1
    assert value("relay_commits_total", {"tool": "update_deal", "outcome": "saved"}) == 1
    assert value("relay_commits_total", {"tool": "update_deal", "outcome": "failed"}) == 1
    assert value("relay_ui_actions_total", {"action": "PRESENT_UI", "outcome": "applied"}) == 1
    assert value("relay_interruptions_total") == 1

    # A model inventing tool names must not create unbounded series.
    for i in range(150):
        await bridge.on_event(_event(EventType.TOOL_CALL_FAILED, {"name": f"made_up_{i}", "error": "unknown_tool"}, at=t0))
    names = {json.dumps(s.labels) for m in bridge.registry.collect() if m.name == "relay_tool_calls" for s in m.samples}
    assert len(names) <= 102  # 100 distinct + "other" (+ created samples share labels)
    assert value("relay_tool_calls_total", {"tool": "other", "outcome": "failed"}) >= 50
