"""Voice turn orchestration via SessionManager notifications."""

from __future__ import annotations

import pytest
import pytest_asyncio

from relay_adapter_agents_reference import ReferenceTextAgent
from relay_adapter_models_openai import OpenAIProvider
from relay_protocol import EventType
from relay_runtime import (
    AgentRuntime,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    SessionManager,
    TurnPhase,
)


def _build_session_manager() -> tuple[SessionManager, MemoryEventStore]:
    store = MemoryEventStore()
    gateway = PersistingEventGateway(store)
    router = ModelRouter(OpenAIProvider(api_key=None))
    runtime = AgentRuntime(model_router=router, agent=ReferenceTextAgent(router))
    manager = SessionManager(event_gateway=gateway, agent_runtime=runtime, session_lock=None)
    return manager, store


@pytest_asyncio.fixture
async def session_manager_fixture():
    manager, store = _build_session_manager()
    yield manager, store
    for session_id in list(manager._sessions):
        await manager.end_session(session_id)


@pytest.mark.asyncio
async def test_voice_transcript_final_emits_turn_and_response(session_manager_fixture):
    manager, store = session_manager_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.notify_voice_speech_started(session.session_id)
    await manager.notify_voice_speech_ended(session.session_id)
    await manager.notify_voice_transcript_delta(session.session_id, "hel")
    await manager.notify_voice_transcript_final(session.session_id, "hello")

    types = [e.type for e in store.all_events()]
    assert EventType.USER_SPEECH_STARTED in types
    assert EventType.USER_SPEECH_ENDED in types
    assert EventType.TRANSCRIPT_DELTA in types
    assert types.count(EventType.TRANSCRIPT_FINAL) == 1
    assert EventType.TURN_PROCESSING in types
    assert EventType.TURN_COMPLETED in types
    completed = next(e for e in store.all_events() if e.type == EventType.RESPONSE_COMPLETED)
    assert completed.payload.get("generated_text")
    assert session.turn_manager.phase == TurnPhase.IDLE


@pytest.mark.asyncio
async def test_user_text_during_voice_clears_utterance_and_runs_text_turn(
    session_manager_fixture,
):
    manager, store = session_manager_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.notify_voice_speech_started(session.session_id)
    await manager.submit_user_text(session.session_id, "typed while speaking")

    types = [e.type for e in store.all_events()]
    assert EventType.SESSION_ERROR not in types
    assert EventType.TURN_STARTED in types
    assert session.turn_manager.phase == TurnPhase.IDLE


@pytest.mark.asyncio
async def test_p03_tc_004_cancel_mid_utterance_no_turn(session_manager_fixture):
    manager, store = session_manager_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.notify_voice_speech_started(session.session_id)
    await manager.cancel_voice_utterance(session.session_id)
    await manager.notify_voice_transcript_final(session.session_id, "should not run")

    types = [e.type for e in store.all_events()]
    assert EventType.TURN_STARTED not in types
    assert session.turn_manager.phase == TurnPhase.IDLE
