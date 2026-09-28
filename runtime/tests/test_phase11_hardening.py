"""Phase 11 — failure injection, smoke hooks, transport/LiveKit stubs."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio

from relay_adapter_models_openai import OpenAIProvider
from relay_adapter_realtime_pipecat.livekit import LiveKitRealtimeTransport
from relay_mortgage_agent.tool_definitions import register_mortgage_tools
from relay_mortgage_agent.tools_local import LocalMortgageToolExecutor
from relay_protocol import EventType
from relay_runtime import (
    AgentRuntime,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    RegistryToolExecutor,
    SessionManager,
    ToolRegistry,
    TraceManager,
)
from relay_adapter_agents_reference import ReferenceTextAgent


@pytest_asyncio.fixture
async def manager_fixture():
    store = MemoryEventStore()
    gateway = PersistingEventGateway(store)
    registry = ToolRegistry()
    register_mortgage_tools(registry)
    tools = RegistryToolExecutor(
        registry=registry,
        delegate=LocalMortgageToolExecutor(),
        trace_manager=TraceManager(),
        default_timeout_seconds=30.0,
    )
    router = ModelRouter(OpenAIProvider(api_key=None))
    runtime = AgentRuntime(model_router=router, agent=ReferenceTextAgent(router))
    manager = SessionManager(event_gateway=gateway, agent_runtime=runtime, tool_executor=tools)
    yield manager, store
    for sid in list(manager._sessions):
        await manager.end_session(sid)


@pytest.mark.asyncio
async def test_p11_tc_004_livekit_stub_imports():
    transport = LiveKitRealtimeTransport()
    assert await transport.is_connected("s1") is False


@pytest.mark.asyncio
async def test_p11_tc_002_model_timeout_injection(manager_fixture, monkeypatch):
    monkeypatch.setenv("RELAY_INJECT_MODEL_TIMEOUT", "1")
    manager, store = manager_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    with pytest.raises(RuntimeError, match="session actor failed"):
        await manager.submit_user_text(session.session_id, "trigger timeout")

    monkeypatch.delenv("RELAY_INJECT_MODEL_TIMEOUT", raising=False)
    session2, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.submit_user_text(session2.session_id, "recover session")
    types = [e.type for e in store.all_events()]
    assert EventType.TURN_COMPLETED in types


@pytest.mark.asyncio
async def test_p11_tc_003_transport_disconnect_metric(manager_fixture):
    manager, store = manager_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.record_transport_state(session.session_id, "disconnected")
    metrics = [e for e in store.all_events() if e.type == EventType.METRIC]
    assert any("transport" in str(m.payload.get("name", "")) for m in metrics)


@pytest.mark.asyncio
async def test_p11_tool_timeout_injection(monkeypatch):
    monkeypatch.setenv("RELAY_INJECT_TOOL_TIMEOUT_SEC", "0.001")
    from relay_adapter_tools_http.executor import HttpToolExecutor

    executor = HttpToolExecutor(base_url="http://127.0.0.1:1", timeout_seconds=30.0)
    with pytest.raises(Exception):
        await executor.execute("s", tool_name="get_mortgage", arguments={"mortgage_id": "MORT-2931"})


def test_p11_tc_005_smoke_import_boundaries():
    """Subset of regression: protocol + runtime timeline modules import."""
    import relay_protocol  # noqa: F401
    from relay_runtime.session_timeline import build_session_timeline  # noqa: F401
