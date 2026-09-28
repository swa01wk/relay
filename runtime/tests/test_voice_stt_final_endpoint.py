"""STT final closes utterance when Silero never sends speech_end."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from relay_protocol import EventType
from relay_runtime import MemoryEventStore, PersistingEventGateway, SessionManager, TurnPhase
from relay_runtime.turn_manager import TurnManager


@pytest.mark.asyncio
async def test_stt_final_triggers_turn_when_vad_stuck():
    store = MemoryEventStore()
    gateway = PersistingEventGateway(store)
    runtime = MagicMock()
    runtime.run_streaming_turn = AsyncMock(return_value="Hi there.")
    manager = SessionManager(event_gateway=gateway, agent_runtime=runtime)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")

    session.turn_manager = TurnManager()
    session.turn_manager.on_user_speech_started()

    await manager.notify_voice_transcript_final(session.session_id, "Hello?")
    await asyncio.sleep(0.05)

    assert any(e.type == EventType.USER_SPEECH_ENDED for e in store.all_events())
    assert any(e.type == EventType.TURN_STARTED for e in store.all_events())

    await manager.end_session(session.session_id)
