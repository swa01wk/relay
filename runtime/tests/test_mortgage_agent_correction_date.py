"""Mortgage agent — draft effective date updates via tools + state sync."""

from __future__ import annotations

import pytest
import pytest_asyncio

from relay_adapter_models_openai import OpenAIProvider
from relay_mortgage_agent.agent import (
    MortgageServicingAgent,
    _parse_effective_date,
    _resolve_correction_date_request,
)
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


def test_parse_effective_date_formats():
    assert _parse_effective_date("change to 01/01/2026") == "2026-01-01"
    assert _parse_effective_date("use 2026-01-01") == "2026-01-01"


def test_resolve_affirmation_uses_recent_user_date():
    ctx = {
        "state": {"state": {"screen": "correction_draft", "correction_draft": {"status": "draft"}}},
        "messages": [
            {"role": "user", "content": "change the date to 01/01/2026?"},
            {"role": "assistant", "content": "I can update that."},
        ],
    }
    assert _resolve_correction_date_request("Yeah. Update.", "yeah. update.", ctx) == "2026-01-01"


@pytest_asyncio.fixture
async def manager_with_tools():
    store = MemoryEventStore()
    gateway = PersistingEventGateway(store)
    router = ModelRouter(OpenAIProvider(api_key=None))
    registry = ToolRegistry()
    register_mortgage_tools(registry)
    tools = RegistryToolExecutor(registry=registry, delegate=LocalMortgageToolExecutor())
    runtime = AgentRuntime(model_router=router, agent=MortgageServicingAgent(router), tool_executor=tools)
    manager = SessionManager(event_gateway=gateway, agent_runtime=runtime, session_lock=None)
    yield manager, store
    for session_id in list(manager._sessions):
        await manager.end_session(session_id)


@pytest.mark.asyncio
async def test_voice_style_date_update_syncs_state(manager_with_tools):
    manager, _store = manager_with_tools
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.submit_client_state_snapshot(
        session.session_id,
        {
            "screen": "correction_draft",
            "workflow": "correction_draft",
            "correction_draft": {
                "mortgage_id": "MORT-2931",
                "effective_date": "2025-01-01",
                "status": "draft",
            },
        },
    )
    await manager.submit_user_text(
        session.session_id,
        "change the date to 01/01/2026?",
    )
    assert session.context.state["correction_draft"]["effective_date"] == "2026-01-01"

    await manager.submit_user_text(session.session_id, "Yeah. Update.")
    assert session.context.state["correction_draft"]["effective_date"] == "2026-01-01"
