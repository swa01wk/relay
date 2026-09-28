"""P07-TC-001/002 — voice barge-in and heard-text commit."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio

from relay_adapter_agents_reference import ReferenceTextAgent
from relay_adapter_models_openai import OpenAIProvider
from relay_adapter_speech_deepgram.tts_provider import MockTextToSpeechProvider
from relay_protocol import EventType
from relay_runtime import (
    AgentRuntime,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    SessionManager,
    TurnPhase,
)
from relay_runtime.ports.realtime import RealtimeTransport
from relay_runtime.voice_output import VoiceOutputConfig


@dataclass
class RecordingTransport(RealtimeTransport):
    connected: set[str] = field(default_factory=set)
    pcm_chunks: list[bytes] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)

    async def connect(self, session_id: str, *, offer: dict[str, Any] | None = None) -> dict[str, Any]:
        self.connected.add(session_id)
        return {"sdp": "mock", "type": "answer", "pc_id": "pc-mock"}

    async def disconnect(self, session_id: str) -> None:
        self.connected.discard(session_id)

    async def is_connected(self, session_id: str) -> bool:
        return session_id in self.connected

    async def push_output_pcm(
        self,
        session_id: str,
        *,
        audio: bytes,
        sample_rate: int,
        num_channels: int = 1,
    ) -> None:
        _ = (session_id, sample_rate, num_channels)
        self.pcm_chunks.append(audio)

    async def finish_output_pcm(self, session_id: str) -> None:
        _ = session_id

    async def wait_output_drained(self, session_id: str) -> None:
        _ = session_id

    async def cancel_output(self, session_id: str) -> None:
        self.cancelled.append(session_id)


class _SlowMockTts(MockTextToSpeechProvider):
    async def synthesize_stream(self, session_id, text):
        async for chunk in super().synthesize_stream(session_id, text):
            await asyncio.sleep(0.04)
            yield chunk


def _build_manager(transport: RecordingTransport) -> tuple[SessionManager, MemoryEventStore]:
    store = MemoryEventStore()
    gateway = PersistingEventGateway(store)
    router = ModelRouter(OpenAIProvider(api_key=None))
    runtime = AgentRuntime(model_router=router, agent=ReferenceTextAgent(router))
    manager = SessionManager(
        event_gateway=gateway,
        agent_runtime=runtime,
        session_lock=None,
        realtime_transport=transport,
        text_to_speech=MockTextToSpeechProvider(sample_rate=24000, chunk_ms=20),
        voice_output=VoiceOutputConfig(sample_rate=24000),
    )
    return manager, store


@pytest_asyncio.fixture
async def voice_interrupt_fixture():
    transport = RecordingTransport()
    manager, store = _build_manager(transport)
    yield manager, store, transport
    for session_id in list(manager._sessions):
        await manager.end_session(session_id)


@pytest.mark.asyncio
async def test_p07_tc_001_barge_in_stops_playout(voice_interrupt_fixture):
    manager, store, transport = voice_interrupt_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.start_realtime(session.session_id, {"sdp": "v=0", "type": "offer"})
    manager.text_to_speech = _SlowMockTts(sample_rate=24000, chunk_ms=20)

    await manager.notify_voice_speech_started(session.session_id)
    await manager.notify_voice_speech_ended(session.session_id)
    final_task = asyncio.create_task(
        manager.notify_voice_transcript_final(
            session.session_id,
            "Please explain the EMI increase in detail for this mortgage",
        )
    )
    await asyncio.sleep(0.08)
    await manager.notify_voice_speech_started(session.session_id)
    await final_task
    rec = manager.get(session.session_id)
    if rec and rec.voice_response_task is not None:
        await rec.voice_response_task

    types = [e.type for e in store.all_events()]
    assert EventType.INTERRUPTION_DETECTED in types
    assert EventType.RESPONSE_INTERRUPTED in types or EventType.RESPONSE_CANCELLED in types
    assert session.session_id in transport.cancelled
    assert manager.get(session.session_id).turn_manager.phase in (
        TurnPhase.USER_SPEAKING,
        TurnPhase.IDLE,
    )


@pytest.mark.asyncio
async def test_p07_tc_002_heard_text_committed_subset(voice_interrupt_fixture):
    manager, store, _transport = voice_interrupt_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.start_realtime(session.session_id, {"sdp": "v=0", "type": "offer"})
    manager.text_to_speech = _SlowMockTts(sample_rate=24000, chunk_ms=20)

    await manager.notify_voice_speech_started(session.session_id)
    await manager.notify_voice_speech_ended(session.session_id)
    final_task = asyncio.create_task(
        manager.notify_voice_transcript_final(session.session_id, "hello there friend")
    )
    await asyncio.sleep(0.12)
    await manager.cancel_agent_playback(session.session_id)
    await final_task
    rec = manager.get(session.session_id)
    if rec and rec.voice_response_task is not None:
        await rec.voice_response_task

    heard_events = [e for e in store.all_events() if e.type == EventType.HEARD_TEXT_COMMITTED]
    interrupted = [e for e in store.all_events() if e.type == EventType.RESPONSE_INTERRUPTED]
    assert heard_events
    assert interrupted
    heard = str(heard_events[-1].payload.get("text", ""))
    generated = str(interrupted[-1].payload.get("generated_text", ""))
    assert generated
    assert heard in generated
    if len(generated) > 20:
        assert len(heard) < len(generated)

    ctx = manager.get(session.session_id).context
    assistant_msgs = [m for m in ctx.messages if m["role"] == "assistant"]
    assert assistant_msgs
    assert assistant_msgs[-1]["content"] == heard


@pytest.mark.asyncio
async def test_transcript_delta_while_agent_speaking_not_blocked(voice_interrupt_fixture):
    """STT must publish while the voice response task is still running (not actor-blocked)."""
    manager, store, _transport = voice_interrupt_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.start_realtime(session.session_id, {"sdp": "v=0", "type": "offer"})
    manager.text_to_speech = _SlowMockTts(sample_rate=24000, chunk_ms=20)

    await manager.notify_voice_speech_started(session.session_id)
    await manager.notify_voice_speech_ended(session.session_id)
    await manager.notify_voice_transcript_final(session.session_id, "Tell me a long story please")

    for _ in range(80):
        rec = manager.get(session.session_id)
        if rec and rec.turn_manager.phase == TurnPhase.AGENT_SPEAKING:
            break
        await asyncio.sleep(0.05)
    assert manager.get(session.session_id).turn_manager.phase == TurnPhase.AGENT_SPEAKING

    await manager.notify_voice_transcript_delta(session.session_id, "Wait stop")

    deltas = [e for e in store.all_events() if e.type == EventType.TRANSCRIPT_DELTA]
    assert any("Wait" in str(e.payload.get("text", "")) for e in deltas)
