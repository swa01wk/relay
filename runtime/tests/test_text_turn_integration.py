"""P01-TC-002, P01-TC-004, integration text turn without browser."""

from __future__ import annotations

import asyncio

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
async def test_p01_integration_single_text_turn(session_manager_fixture):
    manager, store = session_manager_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.submit_user_text(session.session_id, "hello")
    types = [e.type for e in store.all_events()]
    assert EventType.TRANSCRIPT_FINAL in types
    assert EventType.RESPONSE_COMPLETED in types
    assert EventType.TURN_COMPLETED in types


@pytest.mark.asyncio
async def test_p01_tc_002_rapid_messages_ordered(session_manager_fixture):
    manager, store = session_manager_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")

    async def send(text: str) -> None:
        await manager.submit_user_text(session.session_id, text)

    first = asyncio.create_task(send("one"))
    second = asyncio.create_task(send("two"))
    await asyncio.gather(first, second)
    turn_completed = [e for e in store.all_events() if e.type == EventType.TURN_COMPLETED]
    assert len(turn_completed) == 2
    sequences = [e.metadata.sequence for e in turn_completed]
    assert sequences == sorted(sequences)
    turn_ids = [e.metadata.turn_id for e in turn_completed]
    assert len(set(turn_ids)) == 2


@pytest.mark.asyncio
async def test_p01_tc_004_reconstruct_turn_from_event_log(session_manager_fixture):
    manager, store = session_manager_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.submit_user_text(session.session_id, "who are you?")

    events = await store.list_for_session(session.session_id)
    by_turn: dict[str, list] = {}
    for event in events:
        if event.metadata.turn_id:
            by_turn.setdefault(event.metadata.turn_id, []).append(event)

    assert len(by_turn) == 1
    turn_events = next(iter(by_turn.values()))
    types = {e.type for e in turn_events}
    assert EventType.TURN_STARTED in types
    assert EventType.TRANSCRIPT_FINAL in types
    assert EventType.RESPONSE_COMPLETED in types
    assert EventType.TURN_COMPLETED in types
    user = next(e for e in turn_events if e.type == EventType.TRANSCRIPT_FINAL)
    assistant = next(e for e in turn_events if e.type == EventType.RESPONSE_COMPLETED)
    assert user.payload["text"] == "who are you?"
    assert assistant.payload["text"]
