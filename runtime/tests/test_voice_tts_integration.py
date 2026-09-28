"""Phase 4 — voice turn with mocked TTS + transport playout."""

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
async def voice_tts_fixture():
    transport = RecordingTransport()
    manager, store = _build_manager(transport)
    yield manager, store, transport
    for session_id in list(manager._sessions):
        await manager.end_session(session_id)


@pytest.mark.asyncio
async def test_p04_voice_turn_emits_speech_and_pcm(voice_tts_fixture):
    manager, store, transport = voice_tts_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.start_realtime(session.session_id, {"sdp": "v=0", "type": "offer"})
    await manager.notify_voice_speech_started(session.session_id)
    await manager.notify_voice_speech_ended(session.session_id)
    await manager.notify_voice_transcript_final(session.session_id, "hello")

    types = [e.type for e in store.all_events()]
    assert EventType.SPEECH_STARTED in types
    assert EventType.SPEECH_STOPPED in types
    assert EventType.RESPONSE_COMPLETED in types
    assert transport.pcm_chunks
    completed = next(e for e in store.all_events() if e.type == EventType.RESPONSE_COMPLETED)
    assert completed.payload.get("generated_text")
    assert session.turn_manager.phase == TurnPhase.IDLE


@pytest.mark.asyncio
async def test_p04_tc_004_latency_metrics_logged(voice_tts_fixture):
    manager, store, _transport = voice_tts_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.start_realtime(session.session_id, {"sdp": "v=0", "type": "offer"})
    await manager.notify_voice_speech_started(session.session_id)
    await manager.notify_voice_speech_ended(session.session_id)
    await manager.notify_voice_transcript_final(session.session_id, "hello")

    metrics = {
        e.payload.get("name")
        for e in store.all_events()
        if e.type == EventType.METRIC
    }
    assert "model.ttft_ms" in metrics
    assert "voice.first_tts_byte_ms" in metrics


@pytest.mark.asyncio
async def test_p04_tc_003_cancel_agent_playback(voice_tts_fixture):
    manager, store, transport = voice_tts_fixture
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.start_realtime(session.session_id, {"sdp": "v=0", "type": "offer"})
    await manager.notify_voice_speech_started(session.session_id)
    await manager.notify_voice_speech_ended(session.session_id)

    slow_tts = _SlowMockTts()
    manager.text_to_speech = slow_tts

    final_task = asyncio.create_task(
        manager.notify_voice_transcript_final(session.session_id, "hello there friend")
    )
    await asyncio.sleep(0.12)
    await manager.cancel_agent_playback(session.session_id)
    await final_task

    types = [e.type for e in store.all_events()]
    assert EventType.SPEECH_STARTED in types
    assert EventType.SPEECH_STOPPED in types
    assert session.session_id in transport.cancelled


class _SlowMockTts(MockTextToSpeechProvider):
    async def synthesize_stream(self, session_id, text):
        async for chunk in super().synthesize_stream(session_id, text):
            await asyncio.sleep(0.05)
            yield chunk
