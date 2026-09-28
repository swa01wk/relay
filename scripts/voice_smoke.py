#!/usr/bin/env python3
"""Voice path smoke test.

Usage:
  python scripts/voice_smoke.py --in-process          # CI: embedded app + mock STT
  python scripts/voice_smoke.py                         # Docker :8080 WebRTC tone
  python scripts/voice_smoke.py --require-transcript  # Docker: require STT final (real speech)
"""

from __future__ import annotations

import argparse
import asyncio
import fractions
import json
import os
import sys
from pathlib import Path

import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaStreamTrack
from av import AudioFrame

VOICE_EVENT_TYPES = frozenset(
    {
        "USER_SPEECH_STARTED",
        "USER_SPEECH_ENDED",
        "TRANSCRIPT_DELTA",
        "TRANSCRIPT_FINAL",
        "TURN_PROCESSING",
        "TURN_COMPLETED",
    }
)


class ToneMicTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self._sample_rate = 16000
        self._i = 0

    async def recv(self) -> AudioFrame:
        n = 320
        t = np.arange(self._i, self._i + n, dtype=np.float64)
        self._i += n
        pcm = (0.55 * np.sin(2 * np.pi * 440.0 * t / self._sample_rate) * 32767.0).astype(np.int16)
        frame = AudioFrame(format="s16", layout="mono", samples=n)
        frame.planes[0].update(pcm.tobytes())
        frame.sample_rate = self._sample_rate
        frame.pts = self._i
        frame.time_base = fractions.Fraction(1, self._sample_rate)
        await asyncio.sleep(0.02)
        return frame


async def _run_in_process() -> int:
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / "services" / "gateway" / "src"))
    for pkg in (
        repo / "runtime" / "src",
        repo / "adapters" / "realtime" / "pipecat" / "src",
        repo / "adapters" / "speech" / "silero" / "src",
        repo / "adapters" / "speech" / "deepgram" / "src",
    ):
        sys.path.insert(0, str(pkg))

    from httpx import ASGITransport, AsyncClient
    from pipecat.frames.frames import InterimTranscriptionFrame, TranscriptionFrame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    from relay_gateway import deps
    from relay_gateway.app import create_app
    from relay_protocol import EventType
    from relay_runtime.memory_event_store import MemoryEventStore

    class FakeStt(FrameProcessor):
        def __init__(self) -> None:
            super().__init__()
            self._bytes = 0

        async def process_frame(self, frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)
            from pipecat.frames.frames import InputAudioRawFrame

            if isinstance(frame, InputAudioRawFrame):
                self._bytes += len(frame.audio)
                if self._bytes > 8000:
                    await self.push_frame(
                        InterimTranscriptionFrame(text="hello", user_id="u", timestamp="t0"),
                        direction,
                    )
                    await self.push_frame(
                        TranscriptionFrame(text="hello smoke", user_id="u", timestamp="t1"),
                        direction,
                    )
            await self.push_frame(frame, direction)

    transport = deps.realtime_transport
    if transport is None:
        print("FAIL: WebRTC disabled")
        return 1
    transport.stt_factory = lambda: FakeStt()

    app = create_app()
    if not isinstance(deps.event_store, MemoryEventStore):
        print("SKIP in-process: gateway uses Postgres event store")
        return 0

    transport_http = ASGITransport(app=app)
    async with AsyncClient(transport=transport_http, base_url="http://test") as client:
        created = await client.post(
            "/dev/sessions",
            json={"project_id": "proj-mortgage-poc", "agent_id": "agent-mortgage-ref"},
        )
        body = created.json()
        session_id = body["session_id"]
        token = body["dev_token"]

        pc = RTCPeerConnection()
        pc.addTrack(ToneMicTrack())
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        resp = await client.post(
            f"/sessions/{session_id}/webrtc/offer",
            params={"token": token},
            json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type},
        )
        resp.raise_for_status()
        answer = resp.json()
        await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
        for _ in range(80):
            if pc.iceConnectionState in ("connected", "completed"):
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(8.0)
        await pc.close()
        await deps.session_manager.end_session(session_id)

    types = [
        e.type
        for e in deps.event_store.all_events()
        if e.metadata.session_id == session_id
    ]
    voice_hits = [t for t in types if t in VOICE_EVENT_TYPES]
    if EventType.TRANSCRIPT_FINAL not in types:
        print("FAIL in-process:", types)
        return 1
    print("OK in-process:", voice_hits)
    return 0


async def _run_live_gateway(*, gateway: str, hold_secs: float, require_transcript: bool) -> int:
    import httpx
    import websockets

    async with httpx.AsyncClient(base_url=gateway, timeout=10.0) as client:
        health = await client.get("/health")
        if health.status_code != 200:
            print("health failed", health.status_code)
            return 1

    async with httpx.AsyncClient(base_url=gateway, timeout=60.0) as client:
        created = await client.post(
            "/dev/sessions",
            json={"project_id": "proj-mortgage-poc", "agent_id": "agent-mortgage-ref"},
        )
        created.raise_for_status()
        body = created.json()
        session_id = body["session_id"]
        token = body["dev_token"]

    ws_base = gateway.replace("https://", "wss://").replace("http://", "ws://")
    ws_uri = f"{ws_base}/ws/sessions/{session_id}?token={token}"
    types: list[str] = []

    async def pump_ws() -> None:
        async with websockets.connect(ws_uri) as ws:
            deadline = asyncio.get_running_loop().time() + 90.0
            while asyncio.get_running_loop().time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                except TimeoutError:
                    continue
                msg = json.loads(raw)
                t = msg.get("type")
                if t:
                    types.append(t)
                    payload = msg.get("payload") or {}
                    extra = payload.get("text") or payload.get("name") or ""
                    print("RP", t, str(extra)[:60])
                if t == "TURN_COMPLETED":
                    return

    ws_task = asyncio.create_task(pump_ws())
    await asyncio.sleep(0.5)

    pc = RTCPeerConnection()
    pc.addTrack(ToneMicTrack())
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    async with httpx.AsyncClient(base_url=gateway, timeout=60.0) as client:
        resp = await client.post(
            f"/sessions/{session_id}/webrtc/offer",
            params={"token": token},
            json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type},
        )
        resp.raise_for_status()
        answer = resp.json()
    await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))

    for _ in range(100):
        if pc.iceConnectionState in ("connected", "completed"):
            break
        await asyncio.sleep(0.1)
    print("ICE", pc.iceConnectionState)
    await asyncio.sleep(max(hold_secs, 5.0))
    await pc.close()
    try:
        await asyncio.wait_for(ws_task, timeout=20.0)
    except (TimeoutError, asyncio.CancelledError):
        ws_task.cancel()

    voice_hits = [t for t in types if t in VOICE_EVENT_TYPES]
    ok = ("TRANSCRIPT_FINAL" in types) if require_transcript else bool(voice_hits)
    if not ok:
        print(
            "FAIL live gateway — try browser mic, or use --in-process. "
            "Docker Desktop WebRTC from host often drops RTP; rebuild gateway if stale."
        )
        print("seen types:", types)
        return 1
    print("OK live:", voice_hits)
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description="WebRTC voice smoke test")
    parser.add_argument("--in-process", action="store_true", help="Embedded gateway + mock STT")
    parser.add_argument(
        "--require-transcript",
        action="store_true",
        help="Live mode: require TRANSCRIPT_FINAL (real speech, not tone)",
    )
    parser.add_argument("--hold-secs", type=float, default=22.0, help="Live mode: tone duration")
    args = parser.parse_args()

    if args.in_process:
        return await _run_in_process()

    gateway = os.environ.get("RELAY_GATEWAY_URL", "http://localhost:8080").rstrip("/")
    return await _run_live_gateway(
        gateway=gateway,
        hold_secs=args.hold_secs,
        require_transcript=args.require_transcript,
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
