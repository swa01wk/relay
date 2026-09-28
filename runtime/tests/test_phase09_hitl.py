"""Phase 9 — HITL commit + verify."""

from __future__ import annotations

import pytest
import pytest_asyncio

from relay_mortgage_agent import MortgageServicingAgent
from relay_mortgage_agent.tool_definitions import register_mortgage_tools
from relay_mortgage_agent.tools_local import LocalMortgageToolExecutor
from relay_adapter_models_openai import OpenAIProvider
from relay_protocol import EventType
from relay_runtime import (
    AgentRuntime,
    HITLManager,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    RegistryToolExecutor,
    SessionManager,
    ToolRegistry,
    TraceManager,
)


def _build_manager() -> tuple[SessionManager, MemoryEventStore, RegistryToolExecutor]:
    store = MemoryEventStore()
    gateway = PersistingEventGateway(store)
    registry = ToolRegistry()
    register_mortgage_tools(registry)
    tools = RegistryToolExecutor(
        registry=registry,
        delegate=LocalMortgageToolExecutor(),
        trace_manager=TraceManager(),
    )
    router = ModelRouter(OpenAIProvider(api_key=None))
    runtime = AgentRuntime(model_router=router, agent=MortgageServicingAgent(router), tool_executor=tools)
    manager = SessionManager(
        event_gateway=gateway,
        agent_runtime=runtime,
        tool_executor=tools,
        session_lock=None,
    )
    tools.hitl_for_session = lambda sid: manager._sessions[sid].hitl_manager if sid in manager._sessions else None
    return manager, store, tools


@pytest_asyncio.fixture
async def hitl_fixture():
    manager, store, tools = _build_manager()
    yield manager, store, tools
    for session_id in list(manager._sessions):
        await manager.end_session(session_id)


@pytest.mark.asyncio
async def test_p09_tc_003_commit_blocked_without_approval(hitl_fixture):
    manager, _store, tools = hitl_fixture
    result = await tools.execute(
        "s1",
        tool_name="commit_correction",
        arguments={
            "mortgage_id": "MORT-2931",
            "effective_date": "2025-03-01",
            "proposed_rate": 6.0,
        },
    )
    assert result.get("error") == "side_effecting_blocked_until_hitl"


@pytest.mark.asyncio
async def test_p09_tc_001_approve_commit_verify(hitl_fixture):
    manager, store, tools = hitl_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    hitl = session.hitl_manager
    record = hitl.register_request(
        tool_name="commit_correction",
        arguments={
            "mortgage_id": "MORT-2931",
            "effective_date": "2025-03-01",
            "proposed_rate": 6.0,
        },
        summary="Test commit",
    )
    hitl.grant(record.approval_id, auth_proof="dev-approver")
    await manager._execute_hitl_commit(session, record.approval_id)

    types = [e.type for e in store.all_events()]
    assert EventType.COMMIT_STARTED in types
    assert EventType.COMMIT_VERIFIED in types
    verified = [e for e in store.all_events() if e.type == EventType.COMMIT_VERIFIED][0]
    assert verified.payload.get("verified") is True
    assert session.context.state.get("correction_draft", {}).get("status") == "committed"


@pytest.mark.asyncio
async def test_p09_tc_002_reject_leaves_draft(hitl_fixture):
    manager, store, _tools = hitl_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.submit_client_state_snapshot(
        session.session_id,
        {
            "screen": "correction_draft",
            "correction_draft": {
                "mortgage_id": "MORT-2931",
                "effective_date": "2025-03-01",
                "status": "draft",
                "proposed_rate": 6.125,
            },
        },
    )
    record = session.hitl_manager.register_request(
        tool_name="commit_correction",
        arguments={
            "mortgage_id": "MORT-2931",
            "effective_date": "2025-03-01",
            "proposed_rate": 6.125,
        },
    )
    await manager.submit_client_app_event(
        session.session_id,
        name="approval.reject",
        payload={"approval_id": record.approval_id},
    )
    assert session.context.state["correction_draft"]["status"] == "draft"
    assert EventType.APPROVAL_REJECTED in [e.type for e in store.all_events()]
    assert EventType.COMMIT_STARTED not in [e.type for e in store.all_events()]


@pytest.mark.asyncio
async def test_p09_audit_trail_event_sequence(hitl_fixture):
    manager, store, _tools = hitl_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    record = session.hitl_manager.register_request(
        tool_name="commit_correction",
        arguments={
            "mortgage_id": "MORT-2931",
            "effective_date": "2025-05-01",
            "proposed_rate": 6.01,
        },
    )
    session.hitl_manager.grant(record.approval_id, auth_proof="dev-approver")
    await manager._execute_hitl_commit(session, record.approval_id)

    types = [e.type for e in store.all_events()]
    for required in (
        EventType.COMMIT_STARTED,
        EventType.TOOL_CALL_COMPLETED,
        EventType.COMMIT_VERIFIED,
    ):
        assert required in types
    verified = [e for e in store.all_events() if e.type == EventType.COMMIT_VERIFIED][0]
    assert verified.payload.get("approval_id") == record.approval_id
    assert verified.metadata.correlation_id


@pytest.mark.asyncio
async def test_p09_agent_submit_for_approval_emits_event(hitl_fixture):
    manager, store, _tools = hitl_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.submit_client_state_snapshot(
        session.session_id,
        {
            "screen": "correction_draft",
            "correction_draft": {
                "mortgage_id": "MORT-2931",
                "effective_date": "2025-06-01",
                "proposed_rate": 6.125,
                "current_rate": 6.125,
                "status": "draft",
            },
        },
    )
    await manager.submit_user_text(session.session_id, "Submit for approval")
    requested = [e for e in store.all_events() if e.type == EventType.APPROVAL_REQUESTED]
    assert len(requested) == 1
    assert requested[0].payload.get("tool_name") == "commit_correction"


@pytest.mark.asyncio
async def test_hitl_idempotent_commit(hitl_fixture):
    manager, _store, tools = hitl_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    record = session.hitl_manager.register_request(
        tool_name="commit_correction",
        arguments={
            "mortgage_id": "MORT-2931",
            "effective_date": "2025-04-01",
            "proposed_rate": 6.05,
        },
    )
    session.hitl_manager.grant(record.approval_id, auth_proof="dev-approver")
    await manager._execute_hitl_commit(session, record.approval_id)
    first = await tools.execute(
        session.session_id,
        tool_name="commit_correction",
        arguments=dict(record.arguments),
        approval_id=record.approval_id,
    )
    second = await tools.execute(
        session.session_id,
        tool_name="commit_correction",
        arguments=dict(record.arguments),
        approval_id=record.approval_id,
    )
    assert first.get("commit_id") == second.get("commit_id")
