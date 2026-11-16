"""Token usage per model call → model.usage METRIC events, cost from configured prices, totals."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from relay_adapter_agents_reference import ReferenceTextAgent
from relay_adapter_models_openai import OpenAIProvider
from relay_protocol import EventType
from relay_runtime import (
    AgentRuntime,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    SessionManager,
    ToolRegistry,
    ToolUsingAgent,
)
from relay_runtime.model_usage import load_prices, summarize_usage, usage_details
from relay_runtime.ports.model import ModelProvider
from relay_runtime.session_timeline import build_session_timeline

PRICES = {"test-model": {"input": 2.0, "output": 10.0, "cached_input": 0.5}}


class UsageModel(ModelProvider):
    async def stream_completion(self, session_id, *, messages, tools=None) -> AsyncIterator[dict[str, Any]]:
        del session_id, messages, tools
        yield {"type": "token", "text": "Hello."}
        yield {"type": "usage", "model": "test-model", "input_tokens": 1000, "output_tokens": 200, "cached_input_tokens": 400}

    async def cancel(self, session_id: str) -> None:
        del session_id


def test_cost_counts_cached_input_at_its_own_price():
    details = usage_details(
        {"model": "test-model", "input_tokens": 1000, "output_tokens": 200, "cached_input_tokens": 400}, PRICES
    )
    # 600 uncached × $2 + 400 cached × $0.5 + 200 output × $10, per 1M tokens
    assert details["cost_usd"] == pytest.approx((600 * 2.0 + 400 * 0.5 + 200 * 10.0) / 1_000_000)
    assert details["total_tokens"] == 1200


def test_unpriced_model_reports_tokens_without_cost():
    details = usage_details({"model": "other", "input_tokens": 10, "output_tokens": 5}, PRICES)
    assert "cost_usd" not in details and details["total_tokens"] == 15
    assert usage_details({"model": "other", "input_tokens": 10, "output_tokens": 5},
                         {"*": {"input": 1.0, "output": 1.0}})["cost_usd"] == pytest.approx(15 / 1_000_000)


def test_load_prices_ignores_malformed_config(monkeypatch):
    monkeypatch.setenv("RELAY_MODEL_PRICES", "{not json")
    assert load_prices() == {}
    monkeypatch.setenv("RELAY_MODEL_PRICES", json.dumps({"m": {"input": "1.5", "output": 2}, "bad": {"input": "x"}}))
    assert load_prices() == {"m": {"input": 1.5, "output": 2.0}}


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_kind", ["tool_using", "reference"])
async def test_each_model_call_publishes_usage_metric_and_timeline_totals(agent_kind):
    router = ModelRouter(UsageModel())
    agent = (
        ToolUsingAgent(router, system_prompt="x", registry=ToolRegistry())
        if agent_kind == "tool_using"
        else ReferenceTextAgent(router)
    )
    store = MemoryEventStore()
    manager = SessionManager(
        event_gateway=PersistingEventGateway(store),
        agent_runtime=AgentRuntime(model_router=router, agent=agent, model_prices=PRICES),
        session_lock=None,
        idle_grace_seconds=0,
    )
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "hi")
        await manager.submit_user_text(session.session_id, "again")
    finally:
        await manager.end_session(session.session_id)

    usage = [e for e in store.all_events() if e.type == EventType.METRIC and e.payload["name"] == "model.usage"]
    assert len(usage) == 2
    assert usage[0].metadata.turn_id and usage[0].payload["value"] == 1200
    assert usage[0].payload["details"]["model"] == "test-model"
    assert [e for e in store.all_events() if e.type == EventType.RESPONSE_COMPLETED][-1].payload["text"] == "Hello."

    totals = build_session_timeline(store.all_events())["usage"]
    assert totals["model_calls"] == 2 and totals["input_tokens"] == 2000 and totals["output_tokens"] == 400
    assert totals["cost_usd"] == pytest.approx(2 * (600 * 2.0 + 400 * 0.5 + 200 * 10.0) / 1_000_000)


def test_summary_without_prices_has_no_cost():
    rows = [{"name": "model.usage", "details": {"input_tokens": 5, "output_tokens": 1, "total_tokens": 6}},
            {"name": "model.ttft_ms", "value": 12.0}]
    assert summarize_usage(rows) == {
        "model_calls": 1, "input_tokens": 5, "output_tokens": 1, "cached_input_tokens": 0, "total_tokens": 6,
    }


def _sse(*chunks: dict[str, Any]) -> bytes:
    return ("".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n").encode()


@pytest.mark.asyncio
async def test_openai_provider_requests_and_parses_usage():
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=_sse(
            {"choices": [{"delta": {"content": "Hi"}}]},
            # The usage chunk has no choices; indexing choices[0] used to crash here.
            {"choices": [], "usage": {"prompt_tokens": 120, "completion_tokens": 7,
                                       "prompt_tokens_details": {"cached_tokens": 100}}},
        ))

    provider = OpenAIProvider(api_key="k", model="test-model", base_url="http://openai.test/v1")
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    chunks = [c async for c in provider.stream_completion("s", messages=[{"role": "user", "content": "hi"}])]
    await provider.aclose()

    assert seen["body"]["stream_options"] == {"include_usage": True}
    assert chunks == [
        {"type": "token", "text": "Hi"},
        {"type": "usage", "model": "test-model", "input_tokens": 120, "output_tokens": 7, "cached_input_tokens": 100},
    ]


@pytest.mark.asyncio
async def test_usage_request_can_be_disabled(monkeypatch):
    monkeypatch.setenv("RELAY_OPENAI_STREAM_USAGE", "0")
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=_sse({"choices": [{"delta": {"content": "Hi"}}]}))

    provider = OpenAIProvider(api_key="k", model="m", base_url="http://openai.test/v1")
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    chunks = [c async for c in provider.stream_completion("s", messages=[])]
    await provider.aclose()
    assert "stream_options" not in seen["body"] and chunks == [{"type": "token", "text": "Hi"}]


@pytest.mark.asyncio
async def test_text_turns_record_time_to_first_token():
    router = ModelRouter(UsageModel())
    store = MemoryEventStore()
    manager = SessionManager(
        event_gateway=PersistingEventGateway(store),
        agent_runtime=AgentRuntime(model_router=router, agent=ReferenceTextAgent(router), model_prices={}),
        session_lock=None,
        idle_grace_seconds=0,
    )
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "hi")
    finally:
        await manager.end_session(session.session_id)
    ttft = [e for e in store.all_events() if e.type == EventType.METRIC and e.payload["name"] == "model.ttft_ms"]
    assert len(ttft) == 1 and ttft[0].payload["value"] >= 0 and ttft[0].metadata.turn_id
