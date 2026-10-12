"""Sales CRM agent built from agents/sales-crm.yaml + the CRM tools service's GET /tools."""

from __future__ import annotations

import inspect
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from pathlib import Path

from crm_tools_api.tools import TOOL_SPECS, call_tool, tool_manifest
from relay_gateway.manifests import build_manifest_runtime, parse_manifest
from relay_protocol import EventType
from relay_runtime import MemoryEventStore, ModelRouter, PersistingEventGateway, SessionManager
from relay_runtime.ports.model import ModelProvider
from relay_runtime.ports.tools import ToolExecutor

MANIFEST = Path(__file__).resolve().parents[3] / "agents" / "sales-crm.yaml"


class InProcessCrmTools(ToolExecutor):
    async def execute(self, session_id, *, tool_name, arguments, idempotency_key=None):
        del session_id, idempotency_key
        return call_tool(tool_name, arguments)


class PipelineChartModel(ModelProvider):
    async def stream_completion(
        self, session_id: str, *, messages: list[dict[str, Any]], tools: Any = None
    ) -> AsyncIterator[dict[str, Any]]:
        del session_id, tools
        results = [m for m in messages if m.get("role") == "tool"]
        if not results:
            yield {"type": "tool_calls", "calls": [{"id": "c1", "name": "get_pipeline_summary", "arguments": "{}"}]}
            return
        if len(results) == 1:
            stages = json.loads(results[0]["content"])["stages"]
            surface = {
                "kind": "chart",
                "title": "Pipeline by stage",
                "chart_type": "bar",
                "x_key": "stage",
                "series": [{"key": "amount_usd", "label": "Amount"}],
                "data": [{"stage": s["stage"], "amount_usd": s["amount_usd"]} for s in stages],
            }
            yield {"type": "tool_calls", "calls": [{"id": "c2", "name": "present_ui", "arguments": json.dumps({"surfaces": [surface]})}]}
            return
        yield {"type": "token", "text": "Your pipeline by stage is on screen."}

    async def cancel(self, session_id: str) -> None:
        del session_id


@pytest.mark.asyncio
async def test_crm_agent_charts_pipeline_from_tools():
    router = ModelRouter(PipelineChartModel())
    store = MemoryEventStore()
    manager = SessionManager(
        event_gateway=PersistingEventGateway(store),
        agent_runtime=build_manifest_runtime(
            parse_manifest(MANIFEST), tool_manifest(), model_router=router, delegate=InProcessCrmTools()
        ),
        session_lock=None,
        idle_grace_seconds=0,
    )
    session, _ = await manager.create_dev_session(project_id="p", agent_id="sales-crm")
    try:
        await manager.submit_user_text(session.session_id, "chart my pipeline by stage")
    finally:
        await manager.end_session(session.session_id)

    events = store.all_events()
    present = [e for e in events if e.type == EventType.ACTION_REQUESTED and e.payload.get("action") == "PRESENT_UI"]
    chart = present[-1].payload["params"]["surfaces"][0]
    assert chart["kind"] == "chart" and chart["chart_type"] == "bar"
    assert [p["stage"] for p in chart["data"]][:2] == ["Prospecting", "Qualification"]
    assert any(e.type == EventType.TOOL_CALL_COMPLETED and e.payload.get("name") == "get_pipeline_summary" for e in events)


def test_every_tool_spec_matches_its_function_signature():
    for name, spec in TOOL_SPECS.items():
        params = set(inspect.signature(spec.fn).parameters)
        assert set(spec.properties) == params, name
        assert set(spec.required) <= params, name
        if spec.classification == "read_only":  # never execute write tools here
            assert "error" not in call_tool(name, {key: _sample(key) for key in spec.required}), name


def _sample(key: str) -> str:
    return {"query": "north", "account_id": "ACC-101", "deal_id": "DEAL-2001"}[key]
