"""Words spoken while the agent is still working on a turn become the next turn."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from relay_runtime import MemoryEventStore, PersistingEventGateway, SessionManager, TurnPhase


async def _voice_session(release: asyncio.Event):
    runtime = MagicMock()
    texts: list[str] = []

    async def run_streaming_turn(*args, **kwargs):
        texts.append(kwargs["user_text"])
        if len(texts) == 1:
            await release.wait()  # the first turn is still "thinking"
        return "Okay."

    runtime.run_streaming_turn = run_streaming_turn
    manager = SessionManager(event_gateway=PersistingEventGateway(MemoryEventStore()), agent_runtime=runtime)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    return manager, session, texts


async def _say(manager, session_id, text):
    await manager.notify_voice_speech_started(session_id)
    await manager.notify_voice_transcript_final(session_id, text)
    await manager.notify_voice_speech_ended(session_id)


async def _wait_for(predicate, timeout=2.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < deadline, "timed out"
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_words_spoken_while_the_agent_thinks_start_the_next_turn(monkeypatch):
    monkeypatch.setenv("RELAY_UTTERANCE_COMMIT_DELAY_MS", "0")
    release = asyncio.Event()
    manager, session, texts = await _voice_session(release)

    await _say(manager, session.session_id, "I need a loan")
    await _wait_for(lambda: len(texts) == 1)
    assert session.turn_manager.phase == TurnPhase.PROCESSING

    await _say(manager, session.session_id, "for three months")
    await asyncio.sleep(0.05)
    assert len(texts) == 1  # still waiting for the first turn

    release.set()
    await _wait_for(lambda: len(texts) == 2)
    assert texts == ["I need a loan", "for three months"]
    await manager.end_session(session.session_id)


@pytest.mark.asyncio
async def test_a_late_final_of_the_committed_words_is_not_a_new_turn(monkeypatch):
    monkeypatch.setenv("RELAY_UTTERANCE_COMMIT_DELAY_MS", "0")
    monkeypatch.setenv("RELAY_STT_FINAL_WAIT_MS", "0")
    release = asyncio.Event()
    manager, session, texts = await _voice_session(release)

    await manager.notify_voice_speech_started(session.session_id)
    await manager.notify_voice_transcript_final(session.session_id, "Call Priya")
    await manager.notify_voice_transcript_delta(session.session_id, "tomorrow")
    await manager.notify_voice_speech_ended(session.session_id)
    await _wait_for(lambda: len(texts) == 1)
    assert texts == ["Call Priya tomorrow"]

    # The recognizer finalizes "tomorrow" after the turn already used its interim text.
    await manager.notify_voice_transcript_final(session.session_id, "Tomorrow.")
    release.set()
    await asyncio.sleep(0.1)
    assert texts == ["Call Priya tomorrow"]
    await manager.end_session(session.session_id)
