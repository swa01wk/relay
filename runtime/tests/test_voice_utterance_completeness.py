"""Every word the speech recognizer returns must reach the agent's turn."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from relay_runtime import MemoryEventStore, PersistingEventGateway, SessionManager, TurnPhase


async def _voice_session():
    runtime = MagicMock()
    runtime.run_streaming_turn = AsyncMock(return_value="Okay.")
    manager = SessionManager(event_gateway=PersistingEventGateway(MemoryEventStore()), agent_runtime=runtime)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    return manager, session


def _turn_count(manager: SessionManager) -> int:
    return manager.agent_runtime.run_streaming_turn.await_count


def _user_text(manager: SessionManager) -> str:
    """The text the agent's turn was started with."""
    calls = manager.agent_runtime.run_streaming_turn.await_args_list
    assert len(calls) == 1, f"expected one turn, got {len(calls)}"
    return calls[0].kwargs["user_text"]


@pytest.mark.asyncio
async def test_pause_mid_sentence_does_not_end_the_turn_with_default_timing(monkeypatch):
    """A recognizer final is not the end of the sentence; the turn detector decides that."""
    monkeypatch.delenv("RELAY_STT_FINAL_ENDPOINT_MS", raising=False)
    manager, session = await _voice_session()
    await manager.notify_voice_speech_started(session.session_id)

    await manager.notify_voice_transcript_final(session.session_id, "Show me the deals")
    await asyncio.sleep(0.5)

    assert session.turn_manager.phase == TurnPhase.USER_SPEAKING
    assert _turn_count(manager) == 0

    await manager.notify_voice_transcript_final(session.session_id, "closing this month")
    await manager.notify_voice_speech_ended(session.session_id)
    await asyncio.sleep(0.05)

    assert _user_text(manager) == "Show me the deals closing this month"
    await manager.end_session(session.session_id)


@pytest.mark.asyncio
async def test_commit_waits_for_the_final_of_words_still_being_recognized(monkeypatch):
    monkeypatch.setenv("RELAY_UTTERANCE_COMMIT_DELAY_MS", "10")
    manager, session = await _voice_session()
    await manager.notify_voice_speech_started(session.session_id)
    await manager.notify_voice_transcript_final(session.session_id, "Call Priya")
    await manager.notify_voice_transcript_delta(session.session_id, "tomorrow at")

    await manager.notify_voice_speech_ended(session.session_id)
    await asyncio.sleep(0.1)
    assert _turn_count(manager) == 0

    await manager.notify_voice_transcript_final(session.session_id, "tomorrow at noon")
    await asyncio.sleep(0.05)

    assert _user_text(manager) == "Call Priya tomorrow at noon"
    await manager.end_session(session.session_id)


@pytest.mark.asyncio
async def test_interim_words_are_used_when_the_final_never_arrives(monkeypatch):
    monkeypatch.setenv("RELAY_UTTERANCE_COMMIT_DELAY_MS", "10")
    monkeypatch.setenv("RELAY_STT_FINAL_WAIT_MS", "60")
    manager, session = await _voice_session()
    await manager.notify_voice_speech_started(session.session_id)
    await manager.notify_voice_transcript_final(session.session_id, "Call Priya")
    await manager.notify_voice_transcript_delta(session.session_id, "tomorrow")

    await manager.notify_voice_speech_ended(session.session_id)
    await asyncio.sleep(0.2)

    assert _user_text(manager) == "Call Priya tomorrow"
    await manager.end_session(session.session_id)


@pytest.mark.asyncio
async def test_resuming_speech_before_the_commit_keeps_the_earlier_words(monkeypatch):
    monkeypatch.setenv("RELAY_UTTERANCE_COMMIT_DELAY_MS", "60000")
    manager, session = await _voice_session()
    await manager.notify_voice_speech_started(session.session_id)
    await manager.notify_voice_transcript_final(session.session_id, "Book a table")
    await manager.notify_voice_speech_ended(session.session_id)
    assert session.turn_manager.phase == TurnPhase.ENDPOINTING

    await manager.notify_voice_speech_started(session.session_id)
    assert session.turn_manager.phase == TurnPhase.USER_SPEAKING
    await manager.notify_voice_transcript_final(session.session_id, "for two people")

    monkeypatch.setenv("RELAY_UTTERANCE_COMMIT_DELAY_MS", "0")
    await manager.notify_voice_speech_ended(session.session_id)
    await asyncio.sleep(0.05)

    assert _user_text(manager) == "Book a table for two people"
    await manager.end_session(session.session_id)


@pytest.mark.parametrize(
    ("segments", "expected"),
    [
        (["no", "I know that one"], "no I know that one"),
        (["yes", "yes"], "yes yes"),
        (["the", "the other deal"], "the the other deal"),
        (["Show me", "open deals"], "Show me open deals"),
    ],
)
def test_consecutive_finals_are_never_swallowed(segments, expected):
    text = ""
    for segment in segments:
        text = SessionManager._merge_voice_transcript(text, segment)
    assert text == expected
