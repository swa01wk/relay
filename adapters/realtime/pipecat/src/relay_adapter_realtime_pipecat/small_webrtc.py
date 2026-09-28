"""Pipecat SmallWebRTC implementation of ``RealtimeTransport``."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pipecat.frames.frames import (
    BotSpeakingFrame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    OutputAudioRawFrame,
    TranscriptionFrame,
    UserSpeakingFrame,
    UserStartedSpeakingFrame,
    VADUserStartedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    IceCandidate,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from relay_adapter_realtime_pipecat._loopback import AudioIngressSink, AudioLoopbackProcessor
from relay_adapter_realtime_pipecat.agent_audio import AgentAudioOutputProcessor
from relay_adapter_realtime_pipecat.voice_pipeline import (
    append_voice_turn_processors,
    VoicePipelineHooks,
)
from relay_adapter_speech_deepgram import build_pipecat_stt_service
from relay_adapter_speech_silero import build_turn_detector
from relay_adapter_realtime_pipecat.webrtc_fixup import apply_small_webrtc_audio_fixup
from relay_runtime.failure_injection import inject_transport_fail_connect
from relay_runtime.ports.realtime import RealtimeTransport

apply_small_webrtc_audio_fixup()

logger = logging.getLogger(__name__)

# Pipecat default idle frames omit mic ingress and agent PCM; voice sessions then
# hit "Idle timeout detected" while the user listens to long TTS or stays quiet.
_VOICE_PIPELINE_IDLE_FRAMES = (
    BotSpeakingFrame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    UserSpeakingFrame,
    UserStartedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    InputAudioRawFrame,
    OutputAudioRawFrame,
)


def _pipeline_idle_timeout_secs() -> float | None:
    raw = os.environ.get("RELAY_PIPELINE_IDLE_TIMEOUT_SECS", "").strip()
    if not raw:
        return None
    return float(raw)


TransportMetricCallback = Callable[[str, str, float], Awaitable[None]]
TransportStateCallback = Callable[[str, str], Awaitable[None]]


@dataclass
class _ActiveSession:
    session_id: str
    pc_id: str | None = None
    webrtc_connection: SmallWebRTCConnection | None = None
    runner: WorkerRunner | None = None
    pipeline_task: asyncio.Task[None] | None = None
    connected: bool = False
    agent_audio: AgentAudioOutputProcessor | None = None


@dataclass
class PipecatSmallWebRtcTransport(RealtimeTransport):
    """SmallWebRTC media plane bound to Relay RP ``session_id``."""

    ice_servers: list[IceServer] | None = None
    on_metric: TransportMetricCallback | None = None
    on_connection_state: TransportStateCallback | None = None
    voice_hooks: VoicePipelineHooks | None = None
    turn_detector_factory: Callable[[], Any] | None = None
    stt_factory: Callable[[], Any] | None = None
    agent_output_sample_rate: int = 24000
    _handler: SmallWebRTCRequestHandler = field(init=False, repr=False)
    _sessions: dict[str, _ActiveSession] = field(default_factory=dict, repr=False)
    _pc_to_session: dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._handler = SmallWebRTCRequestHandler(ice_servers=self.ice_servers)

    async def connect(self, session_id: str, *, offer: dict[str, Any] | None = None) -> dict[str, Any]:
        if inject_transport_fail_connect():
            if self.on_metric:
                await self.on_metric(session_id, "transport.connect_failed", 1.0)
            raise ConnectionError("RELAY_INJECT_TRANSPORT_DISCONNECT")
        if not offer or "sdp" not in offer or "type" not in offer:
            raise ValueError("WebRTC offer requires sdp and type")
        started = time.perf_counter()
        request = SmallWebRTCRequest.from_dict(
            {
                **offer,
                "request_data": {"session_id": session_id},
            }
        )

        async def on_webrtc_connection(connection: SmallWebRTCConnection) -> None:
            await self._attach_pipeline(session_id, connection)

        answer = await self._handler.handle_web_request(request, on_webrtc_connection)
        if answer is None:
            raise RuntimeError("no WebRTC answer")
        latency_ms = (time.perf_counter() - started) * 1000.0
        pc_id = answer.get("pc_id")
        active = self._sessions.setdefault(session_id, _ActiveSession(session_id=session_id))
        active.pc_id = pc_id
        if pc_id:
            self._pc_to_session[pc_id] = session_id
        if self.on_metric:
            await self.on_metric(session_id, "transport.connect_latency_ms", latency_ms)
        logger.info(
            "small_webrtc connect session_id=%s pc_id=%s latency_ms=%.1f",
            session_id,
            pc_id,
            latency_ms,
        )
        return answer

    async def patch_ice(
        self,
        session_id: str,
        *,
        pc_id: str,
        candidates: list[dict[str, Any]],
    ) -> None:
        if self._pc_to_session.get(pc_id) not in (None, session_id):
            raise ValueError("pc_id does not match session")
        patch = SmallWebRTCPatchRequest(
            pc_id=pc_id,
            candidates=[
                IceCandidate(
                    candidate=str(c["candidate"]),
                    sdp_mid=str(c["sdp_mid"]),
                    sdp_mline_index=int(c["sdp_mline_index"]),
                )
                for c in candidates
            ],
        )
        await self._handler.handle_patch_request(patch)

    async def disconnect(self, session_id: str) -> None:
        active = self._sessions.pop(session_id, None)
        if not active:
            return
        if active.pc_id:
            self._pc_to_session.pop(active.pc_id, None)
        if active.runner is not None:
            try:
                await active.runner.cancel()
            except Exception:
                logger.debug("runner cancel failed session_id=%s", session_id, exc_info=True)
        if active.pipeline_task is not None and not active.pipeline_task.done():
            active.pipeline_task.cancel()
            try:
                await active.pipeline_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("pipeline task cleanup failed session_id=%s", session_id, exc_info=True)
        if active.webrtc_connection is not None:
            try:
                await active.webrtc_connection.disconnect()
            except Exception:
                logger.debug("webrtc disconnect failed session_id=%s", session_id, exc_info=True)
        if self.on_connection_state:
            await self.on_connection_state(session_id, "disconnected")

    async def is_connected(self, session_id: str) -> bool:
        active = self._sessions.get(session_id)
        return bool(active and active.connected)

    def _agent_audio(self, session_id: str) -> AgentAudioOutputProcessor | None:
        active = self._sessions.get(session_id)
        return active.agent_audio if active else None

    async def push_output_pcm(
        self,
        session_id: str,
        *,
        audio: bytes,
        sample_rate: int,
        num_channels: int = 1,
    ) -> None:
        processor = self._agent_audio(session_id)
        if processor is None:
            return
        await processor.enqueue_pcm(audio, sample_rate=sample_rate, num_channels=num_channels)

    async def finish_output_pcm(self, session_id: str) -> None:
        processor = self._agent_audio(session_id)
        if processor is not None:
            await processor.finish()

    async def wait_output_drained(self, session_id: str) -> None:
        processor = self._agent_audio(session_id)
        if processor is not None:
            await processor.wait_drained()

    async def prepare_output_playout(self, session_id: str) -> None:
        processor = self._agent_audio(session_id)
        if processor is not None:
            processor.prepare_for_playout()

    async def cancel_output(self, session_id: str) -> None:
        processor = self._agent_audio(session_id)
        if processor is not None:
            await processor.cancel()

    async def close(self) -> None:
        for session_id in list(self._sessions):
            await self.disconnect(session_id)
        try:
            await self._handler.close()
        except Exception:
            logger.debug("handler close failed", exc_info=True)

    async def _attach_pipeline(self, session_id: str, webrtc_connection: SmallWebRTCConnection) -> None:
        active = self._sessions.setdefault(session_id, _ActiveSession(session_id=session_id))
        active.pc_id = webrtc_connection.pc_id
        active.webrtc_connection = webrtc_connection
        self._pc_to_session[webrtc_connection.pc_id] = session_id

        loopback = os.environ.get("RELAY_WEBRTC_AUDIO_LOOPBACK", "").lower() in (
            "1",
            "true",
            "yes",
        )
        agent_out = AgentAudioOutputProcessor(session_id=session_id)
        active.agent_audio = agent_out
        audio_out = loopback or self.voice_hooks is not None
        transport = SmallWebRTCTransport(
            webrtc_connection=webrtc_connection,
            params=TransportParams(
                audio_in_enabled=True,
                audio_in_sample_rate=16000,
                audio_out_enabled=audio_out,
                audio_out_sample_rate=self.agent_output_sample_rate,
                audio_out_10ms_chunks=2 if loopback else 1,
            ),
        )
        ingress = AudioLoopbackProcessor() if loopback else AudioIngressSink()
        processors: list[Any] = [transport.input()]
        if self.voice_hooks is not None:
            turn_detector = (
                self.turn_detector_factory() if self.turn_detector_factory else build_turn_detector()
            )
            stt = self.stt_factory() if self.stt_factory else build_pipecat_stt_service()
            if stt is None:
                logger.warning(
                    "voice pipeline without STT (DEEPGRAM_API_KEY missing) session_id=%s",
                    session_id,
                )
            append_voice_turn_processors(
                processors,
                session_id=session_id,
                hooks=self.voice_hooks,
                turn_detector=turn_detector,
                stt=stt,
            )
        processors.append(ingress)
        if audio_out:
            processors.extend([agent_out, transport.output()])
        pipeline = Pipeline(processors)
        idle_kw: dict[str, Any] = {}
        if self.voice_hooks is not None:
            idle_kw["idle_timeout_frames"] = _VOICE_PIPELINE_IDLE_FRAMES
        idle_secs = _pipeline_idle_timeout_secs()
        if idle_secs is not None:
            idle_kw["idle_timeout_secs"] = idle_secs
        worker = PipelineWorker(
            pipeline,
            params=PipelineParams(enable_metrics=True),
            enable_rtvi=False,
            setup_timeout_secs=90.0,
            **idle_kw,
        )
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)
        active.runner = runner

        @transport.event_handler("on_client_connected")
        async def _on_client_connected(_transport: SmallWebRTCTransport, _client: object) -> None:
            active.connected = True
            if self.on_connection_state:
                await self.on_connection_state(session_id, "connected")
            if self.on_metric:
                await self.on_metric(session_id, "transport.media_connected", 1.0)

        @transport.event_handler("on_client_disconnected")
        async def _on_client_disconnected(_transport: SmallWebRTCTransport, _client: object) -> None:
            active.connected = False
            if self.on_connection_state:
                await self.on_connection_state(session_id, "disconnected")
            await runner.cancel()

        async def _run() -> None:
            try:
                await runner.run()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("pipecat pipeline failed session_id=%s", session_id)
                if self.on_connection_state:
                    await self.on_connection_state(session_id, "error")

        active.pipeline_task = asyncio.create_task(_run(), name=f"pipecat-{session_id}")
