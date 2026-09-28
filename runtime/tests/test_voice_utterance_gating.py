"""Voice turns must not start while USER_SPEAKING (STT early finals)."""

from unittest.mock import MagicMock

import pytest

from relay_protocol import EventType
from relay_runtime import MemoryEventStore, PersistingEventGateway, SessionManager, TurnPhase
from relay_runtime.turn_manager import TurnManager


@pytest.mark.asyncio
async def test_stt_final_while_user_speaking_does_not_start_turn():
    store = MemoryEventStore()
    gateway = PersistingEventGateway(store)
    manager = SessionManager(event_gateway=gateway, agent_runtime=MagicMock())
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")

    session.turn_manager = TurnManager()
    session.turn_manager.on_user_speech_started()
    assert session.turn_manager.phase == TurnPhase.USER_SPEAKING

    import os

    os.environ["RELAY_STT_FINAL_ENDPOINT_MS"] = "60000"
    await manager.notify_voice_transcript_final(session.session_id, "Can we find the")
    assert session.turn_manager.phase == TurnPhase.USER_SPEAKING
    assert session.voice_transcript_buffer == "Can we find the"
    assert not any(e.type == EventType.TURN_STARTED for e in store.all_events())

    await manager.end_session(session.session_id)
