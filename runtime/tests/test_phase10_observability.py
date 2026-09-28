"""Phase 10 — observability, timeline reconstruction, spans."""

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
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    RegistryToolExecutor,
    SessionManager,
    ToolRegistry,
    TraceManager,
    build_session_timeline,
    reconstruct_turn_narrative,
)
from relay_runtime.observability import STAGE_MODEL, STAGE_TOOL


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
async def obs_fixture():
    manager, store, tools = _build_manager()
    yield manager, store, tools
    for session_id in list(manager._sessions):
        await manager.end_session(session_id)


@pytest.mark.asyncio
async def test_p10_tc_004_timeline_reconstructs_text_turn(obs_fixture):
    manager, store, _tools = obs_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.submit_user_text(session.session_id, "hello timeline")
    events = await store.list_for_session(session.session_id)
    timeline = build_session_timeline(events)
    assert timeline["event_count"] >= 5
    assert timeline["trace_id"] == session.trace_id
    assert len(timeline["turns"]) == 1
    turn_id = timeline["turns"][0]["turn_id"]
    narrative = reconstruct_turn_narrative(events, turn_id)
    assert narrative is not None
    assert narrative["user_text"] == "hello timeline"
    assert STAGE_MODEL in {s.get("stage") for s in timeline["spans"]}


@pytest.mark.asyncio
async def test_p10_tc_002_parallel_tools_child_spans(obs_fixture):
    manager, store, tools = obs_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    turn_id = "turn-par"
    session.context.begin_turn(turn_id)

    async def publish(event):
        await manager._publish(session, event)

    base = lambda: manager._base_metadata(session, source="test")

    await tools.execute_parallel(
        session.session_id,
        calls=[
            {"tool_name": "get_payments", "arguments": {"mortgage_id": "MORT-2931", "months": 2}},
            {"tool_name": "get_rate_history", "arguments": {"mortgage_id": "MORT-2931"}},
        ],
        turn_id=turn_id,
        publish=publish,
        base_metadata=base,
        context=session.context,
        activity_label="parallel",
    )
    events = await store.list_for_session(session.session_id)
    timeline = build_session_timeline(events)
    tool_spans = [s for s in timeline["spans"] if s.get("stage") == STAGE_TOOL]
    assert len(tool_spans) >= 4
    tool_call_ids = {s.get("tool_call_id") for s in tool_spans if s.get("tool_call_id")}
    assert len(tool_call_ids) >= 2


@pytest.mark.asyncio
async def test_p10_tc_003_hitl_spans_linked(obs_fixture):
    manager, store, _tools = obs_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    record = session.hitl_manager.register_request(
        tool_name="commit_correction",
        arguments={
            "mortgage_id": "MORT-2931",
            "effective_date": "2025-07-01",
            "proposed_rate": 6.02,
        },
    )
    session.hitl_manager.grant(record.approval_id, auth_proof="dev-approver")
    await manager._execute_hitl_commit(session, record.approval_id)
    timeline = build_session_timeline(await store.list_for_session(session.session_id))
    assert len(timeline["hitl"]) >= 2
    hitl_stages = {s.get("stage") for s in timeline["spans"] if "hitl" in str(s.get("stage"))}
    assert hitl_stages


@pytest.mark.asyncio
async def test_p10_tc_001_voice_span_stages_present(obs_fixture):
    """Voice path emits STT + model TRACE_LINK stages (TTS when WebRTC+TTS wired)."""
    from uuid import uuid4

    from relay_runtime.playback_tracker import PlaybackTracker
    from relay_runtime.turn_cancellation import TurnCancellation

    manager, store, _tools = obs_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    session.playback_tracker = PlaybackTracker(session_id=session.session_id)
    turn_id = str(uuid4())
    session.context.begin_turn(turn_id)
    session.voice_turn_cancel = TurnCancellation()
    await manager._run_voice_response_turn(session, turn_id=turn_id, user_text="What is my EMI?")
    timeline = build_session_timeline(await store.list_for_session(session.session_id))
    stages = {s.get("stage") for s in timeline["spans"]}
    assert "relay.stage.stt" in stages
    assert STAGE_MODEL in stages
    metrics = timeline["waterfall_ms"]
    assert "model.ttft_ms" in metrics or STAGE_MODEL in stages
