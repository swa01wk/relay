"""Human snapshots apply while a long tool turn is in flight."""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from relay_adapter_models_openai import OpenAIProvider
from relay_mortgage_agent.agent import MortgageServicingAgent
from relay_protocol import EventType
from relay_runtime import (
    AgentRuntime,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    RegistryToolExecutor,
    SessionManager,
    ToolRegistry,
)
from relay_mortgage_agent.tool_definitions import register_mortgage_tools
from relay_mortgage_agent.tools_local import LocalMortgageToolExecutor


@pytest_asyncio.fixture
async def manager_with_tools():
    store = MemoryEventStore()
    gateway = PersistingEventGateway(store)
    router = ModelRouter(OpenAIProvider(api_key=None))
    registry = ToolRegistry()
    register_mortgage_tools(registry)
    tools = RegistryToolExecutor(
        registry=registry,
        delegate=LocalMortgageToolExecutor(),
    )
    runtime = AgentRuntime(model_router=router, agent=MortgageServicingAgent(router), tool_executor=tools)
    manager = SessionManager(event_gateway=gateway, agent_runtime=runtime, session_lock=None)
    yield manager, store
    for session_id in list(manager._sessions):
        await manager.end_session(session_id)


@pytest.mark.asyncio
async def test_client_snapshot_applies_during_slow_tool(manager_with_tools):
    manager, store = manager_with_tools
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.submit_client_state_snapshot(
        session.session_id,
        {"screen": "mortgage_case", "selected_entity": {"type": "mortgage", "id": "MORT-2931"}},
    )
    version_before = session.context.state_version

    async def human_edit_during_tool() -> None:
        await asyncio.sleep(0.3)
        await manager.submit_client_state_snapshot(
            session.session_id,
            {
                "screen": "correction_draft",
                "correction_draft": {"effective_date": "2025-08-01", "mortgage_id": "MORT-2931"},
            },
        )

    edit_task = asyncio.create_task(human_edit_during_tool())
    await manager.submit_user_text(session.session_id, "Prepare correction draft race")
    await edit_task

    conflicts = [e for e in store.all_events() if e.type == EventType.STATE_CONFLICT]
    assert len(conflicts) >= 1, f"events: {[e.type for e in store.all_events()]}"
    assert session.context.state_version > version_before + 1
    assert session.context.state["correction_draft"]["effective_date"] == "2025-08-01"
