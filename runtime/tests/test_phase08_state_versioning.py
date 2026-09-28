"""Phase 8 — StateVersionEngine + STATE_CONFLICT."""

from __future__ import annotations

import pytest
import pytest_asyncio

from relay_adapter_models_openai import OpenAIProvider
from relay_mortgage_agent.agent import MortgageServicingAgent
from relay_protocol import EventType, RelayEvent, RelayEventMetadata
from relay_runtime import (
    AgentRuntime,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    SessionManager,
    StateVersionEngine,
)
from relay_runtime.context_manager import ContextManager


def test_state_version_engine_rejects_stale_agent_delta():
    engine = StateVersionEngine()
    ctx = ContextManager()
    engine.apply_client_snapshot(ctx, {"screen": "home"})
    engine.apply_client_snapshot(ctx, {"screen": "mortgage_case"})
    assert ctx.state_version == 2

    result = engine.try_apply_agent_delta(
        ctx,
        [{"key": "workflow", "value": "correction_draft"}],
        based_on_version=1,
    )
    assert result.outcome == "conflict"
    assert result.expected_version == 1
    assert result.actual_version == 2
    assert ctx.state_version == 2
    assert ctx.state.get("workflow") != "correction_draft"


def test_state_version_engine_applies_matching_agent_delta():
    engine = StateVersionEngine()
    ctx = ContextManager()
    engine.apply_client_snapshot(ctx, {"screen": "mortgage_case"})
    result = engine.try_apply_agent_delta(
        ctx,
        [{"key": "correction_draft", "value": {"status": "draft"}}],
        based_on_version=1,
    )
    assert result.outcome == "applied"
    assert ctx.state_version == 2
    assert ctx.state["correction_draft"]["status"] == "draft"


@pytest_asyncio.fixture
async def mortgage_session_manager():
    store = MemoryEventStore()
    gateway = PersistingEventGateway(store)
    router = ModelRouter(OpenAIProvider(api_key=None))
    runtime = AgentRuntime(model_router=router, agent=MortgageServicingAgent(router))
    manager = SessionManager(event_gateway=gateway, agent_runtime=runtime, session_lock=None)
    yield manager, store
    for session_id in list(manager._sessions):
        await manager.end_session(session_id)


@pytest.mark.asyncio
async def test_p08_tc_004_stale_agent_delta_emits_state_conflict(mortgage_session_manager):
    manager, store = mortgage_session_manager
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.submit_client_state_snapshot(
        session.session_id,
        {"screen": "correction_draft", "correction_draft": {"effective_date": "2025-01-01"}},
    )
    await manager.submit_client_state_snapshot(
        session.session_id,
        {"screen": "correction_draft", "correction_draft": {"effective_date": "2025-03-01"}},
    )
    assert session.context.state_version == 2

    stale_delta = RelayEvent(
        type=EventType.STATE_DELTA,
        metadata=RelayEventMetadata(
            session_id=session.session_id,
            sequence=0,
            source="test",
            based_on_version=1,
        ),
        payload={
            "patch": [{"key": "correction_draft", "value": {"effective_date": "2025-01-01"}}],
            "based_on_version": 1,
        },
    )
    await manager._emit_agent_event(session, stale_delta)

    conflicts = [e for e in store.all_events() if e.type == EventType.STATE_CONFLICT]
    assert len(conflicts) == 1
    assert conflicts[0].payload["expected_version"] == 1
    assert conflicts[0].payload["actual_version"] == 2
    assert session.context.state["correction_draft"]["effective_date"] == "2025-03-01"


@pytest.mark.asyncio
async def test_p08_conflict_triggers_agent_recompute(mortgage_session_manager):
    manager, store = mortgage_session_manager
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.submit_client_state_snapshot(
        session.session_id,
        {
            "screen": "correction_draft",
            "correction_draft": {
                "mortgage_id": "MORT-2931",
                "effective_date": "2025-04-01",
                "proposed_rate": 6.125,
                "current_rate": 6.125,
                "current_emi": 2847.5,
            },
        },
    )
    stale_delta = RelayEvent(
        type=EventType.STATE_DELTA,
        metadata=RelayEventMetadata(
            session_id=session.session_id,
            sequence=0,
            source="test",
            based_on_version=0,
        ),
        payload={
            "patch": [
                {
                    "key": "correction_draft",
                    "value": {"effective_date": "2025-01-01", "mortgage_id": "MORT-2931"},
                }
            ],
            "based_on_version": 0,
        },
    )
    await manager._emit_agent_event(session, stale_delta)

    assert session.context.state["correction_draft"]["effective_date"] == "2025-04-01"
    snapshots = [e for e in store.all_events() if e.type == EventType.STATE_SNAPSHOT]
    assert len(snapshots) >= 2
    latest = snapshots[-1].payload["state"]["correction_draft"]
    assert latest["effective_date"] == "2025-04-01"
    assert latest.get("projected_emi") is not None
