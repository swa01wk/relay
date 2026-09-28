"""P03 voice smoke — WebRTC synthetic mic + mock STT → TRANSCRIPT_FINAL in event log."""

from __future__ import annotations

import asyncio
import fractions

import numpy as np
import pytest
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaStreamTrack
from av import AudioFrame
from httpx import ASGITransport, AsyncClient
from pipecat.frames.frames import InterimTranscriptionFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from relay_gateway.app import create_app
from relay_gateway import deps
from relay_protocol import EventType
from relay_runtime.memory_event_store import MemoryEventStore

pytest.importorskip("aiortc")


class _ToneMicTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self._sample_rate = 16000
        self._sample_index = 0

    async def recv(self) -> AudioFrame:
        samples = 320
        t = np.arange(self._sample_index, self._sample_index + samples, dtype=np.float64)
        self._sample_index += samples
        wave = (0.45 * np.sin(2 * np.pi * 440.0 * t / self._sample_rate) * 32767.0).astype(
            np.int16
        )
        frame = AudioFrame(format="s16", layout="mono", samples=samples)
        frame.planes[0].update(wave.tobytes())
        frame.sample_rate = self._sample_rate
        frame.pts = self._sample_index
        frame.time_base = fractions.Fraction(1, self._sample_rate)
        await asyncio.sleep(0.02)
        return frame


class _FakeSttService(FrameProcessor):
    def __init__(self) -> None:
        super().__init__()
        self._bytes = 0
        self._emitted = False

    async def process_frame(self, frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        from pipecat.frames.frames import InputAudioRawFrame

        if isinstance(frame, InputAudioRawFrame):
            self._bytes += len(frame.audio)
            if self._bytes > 8000 and not self._emitted:
                self._emitted = True
                await self.push_frame(
                    InterimTranscriptionFrame(text="hello", user_id="user", timestamp="t0"),
                    direction,
                )
                await self.push_frame(
                    TranscriptionFrame(text="hello smoke", user_id="user", timestamp="t1"),
                    direction,
                )
        await self.push_frame(frame, direction)


@pytest.fixture
def app_with_fake_stt():
    transport = deps.realtime_transport
    if transport is None:
        pytest.skip("realtime transport disabled")
    transport.stt_factory = lambda: _FakeSttService()
    yield create_app()


@pytest.mark.asyncio
async def test_p03_voice_smoke_webrtc_injects_transcript(app_with_fake_stt):
    if not isinstance(deps.event_store, MemoryEventStore):
        pytest.skip("requires in-memory event store (no RELAY_DATABASE_URL in test env)")

    app = app_with_fake_stt
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/dev/sessions",
            json={"project_id": "proj-mortgage", "agent_id": "agent-ref"},
        )
        body = created.json()
        session_id = body["session_id"]
        token = body["dev_token"]

        pc = RTCPeerConnection()
        pc.addTrack(_ToneMicTrack())
        try:
            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)
            resp = await client.post(
                f"/sessions/{session_id}/webrtc/offer",
                params={"token": token},
                json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type},
            )
            assert resp.status_code == 200, resp.text
            answer = resp.json()
            await pc.setRemoteDescription(
                RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
            )
            for _ in range(100):
                if pc.iceConnectionState in ("connected", "completed"):
                    break
                await asyncio.sleep(0.05)
            await asyncio.sleep(8.0)
        finally:
            await pc.close()
            await deps.session_manager.end_session(session_id)

    types = [
        e.type
        for e in deps.event_store.all_events()
        if e.metadata.session_id == session_id
    ]
    assert EventType.TRANSCRIPT_FINAL in types, types
    assert EventType.TURN_PROCESSING in types, types
