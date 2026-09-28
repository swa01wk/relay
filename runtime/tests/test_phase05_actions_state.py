"""Phase 5 — ActionRouter + client state sync on SessionManager."""

from __future__ import annotations

import pytest
import pytest_asyncio

from relay_adapter_agents_reference import ReferenceTextAgent
from relay_adapter_models_openai import OpenAIProvider
from relay_protocol import EventType
from relay_runtime import (
    ActionRouter,
    AgentRuntime,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    SessionManager,
)
from relay_runtime.context_manager import ContextManager


def _build_manager() -> tuple[SessionManager, MemoryEventStore]:
    store = MemoryEventStore()
    gateway = PersistingEventGateway(store)
    router = ModelRouter(OpenAIProvider(api_key=None))
    runtime = AgentRuntime(model_router=router, agent=ReferenceTextAgent(router))
    manager = SessionManager(event_gateway=gateway, agent_runtime=runtime, session_lock=None)
    return manager, store


@pytest_asyncio.fixture
async def session_manager_fixture():
    manager, store = _build_manager()
    yield manager, store
    for session_id in list(manager._sessions):
        await manager.end_session(session_id)


def test_context_manager_state_version():
    ctx = ContextManager()
    v1 = ctx.apply_snapshot({"screen": "search_results"})
    v2 = ctx.apply_snapshot({"screen": "mortgage_case"})
    assert v1 == 1
    assert v2 == 2
    assert ctx.state["screen"] == "mortgage_case"


@pytest.mark.asyncio
async def test_p05_state_snapshot_advances_version(session_manager_fixture):
    manager, store = session_manager_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.submit_client_state_snapshot(
        session.session_id,
        {"screen": "mortgage_case", "selected_entity": {"type": "mortgage", "id": "MORT-2931"}},
    )
    assert session.context.state_version == 1
    assert session.context.state["screen"] == "mortgage_case"
    types = [e.type for e in store.all_events()]
    assert EventType.STATE_SNAPSHOT in types
    assert EventType.STATE_VERSION_ADVANCED in types


@pytest.mark.asyncio
async def test_p05_tc_004_unknown_action_failed(session_manager_fixture):
    manager, store = session_manager_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.submit_client_action_result(
        session.session_id,
        action_id="act-unknown",
        name="NOT_A_REAL_ACTION",
        outcome="failed",
        reason="no_handler_registered",
    )
    failed = [e for e in store.all_events() if e.type == EventType.ACTION_FAILED]
    assert len(failed) == 1
    assert failed[0].payload["reason"] == "no_handler_registered"


@pytest.mark.asyncio
async def test_action_router_resolve():
    import asyncio

    router = ActionRouter()
    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    router._pending["aid"] = future
    router.resolve("aid", "applied")
    assert await future == "applied"
