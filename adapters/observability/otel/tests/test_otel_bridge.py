"""OpenTelemetry bridge: one trace per session, spans from a real session's events, no payload data."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from relay_adapter_observability_otel import OtelTraceBridge, tracer_provider_from_env
from relay_adapter_observability_otel.bridge import RelayIdGenerator
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

SECRET_QUESTION = "list deals for the Hartwell account"
SECRET_RESULT = "DEAL-SECRET-77"


class Tools(ToolExecutor):
    async def execute(self, session_id, *, tool_name, arguments, idempotency_key=None):
        del session_id, arguments, idempotency_key
        return {"deals": [{"id": SECRET_RESULT}]}


class Model(ModelProvider):
    async def stream_completion(self, session_id, *, messages, tools=None) -> AsyncIterator[dict[str, Any]]:
        del session_id, tools
        last_user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        if last_user == "boom":
            raise RuntimeError("upstream 401")
        if not [m for m in messages if m.get("role") == "tool"]:
            yield {"type": "tool_calls", "calls": [{"id": "c1", "name": "list_deals", "arguments": "{}"}]}
        else:
            yield {"type": "token", "text": "One deal."}
        yield {"type": "usage", "model": "test-model", "input_tokens": 100, "output_tokens": 20}

    async def cancel(self, session_id: str) -> None:
        del session_id


@pytest.mark.asyncio
async def test_session_trace_tree_and_no_payload_data():
    exporter = InMemorySpanExporter()
    provider = TracerProvider(id_generator=RelayIdGenerator())
    provider.add_span_processor(SimpleSpanProcessor(exporter))

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
            model_prices={},
        ),
        session_lock=None,
        idle_grace_seconds=0,
    )
    bridge = OtelTraceBridge(provider, agent_for_session=lambda _sid: "sales-crm")
    gateway.subscribe("*", bridge.on_event)

    session, _ = await manager.create_dev_session(project_id="p", agent_id="sales-crm")
    await manager.submit_user_text(session.session_id, SECRET_QUESTION)
    await manager.submit_user_text(session.session_id, "boom")
    await manager.end_session(session.session_id)

    spans = exporter.get_finished_spans()
    by_name: dict[str, list] = {}
    for span in spans:
        by_name.setdefault(span.name, []).append(span)

    root = by_name["relay.session"][0]
    assert root.parent is None
    assert format(root.context.trace_id, "032x") == session.trace_id.replace("-", "")
    assert all(s.context.trace_id == root.context.trace_id for s in spans)  # one trace per session
    assert root.attributes["relay.agent"] == "sales-crm"

    turns = sorted(by_name["relay.turn"], key=lambda s: s.start_time)
    assert len(turns) == 2 and all(t.parent.span_id == root.context.span_id for t in turns)
    assert turns[0].status.status_code != StatusCode.ERROR
    assert turns[1].status.status_code == StatusCode.ERROR
    assert turns[1].attributes["relay.error_code"] == "turn_failed"

    tool = by_name["relay.tool list_deals"][0]
    assert tool.parent.span_id == turns[0].context.span_id
    assert tool.end_time >= tool.start_time

    usage = [e for e in turns[0].events if e.name == "model.usage"]
    assert len(usage) == 2 and usage[0].attributes["relay.model.input_tokens"] == 100
    assert "relay.model.cost_usd" not in usage[0].attributes  # no prices configured

    exported = json.dumps(
        [[s.name, dict(s.attributes), [(e.name, dict(e.attributes)) for e in s.events]] for s in spans]
    )
    assert SECRET_QUESTION not in exported and SECRET_RESULT not in exported


def test_tracing_is_off_without_an_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    assert tracer_provider_from_env() is None

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.test:4318")
    provider = tracer_provider_from_env()
    assert provider is not None and isinstance(provider.id_generator, RelayIdGenerator)
    assert provider.resource.attributes["service.name"] == "relay-gateway"
    provider.shutdown()
