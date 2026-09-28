"""Mic → VAD → STT → Relay session voice events."""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    StartFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.turns.user_turn_processor import UserTurnProcessor

from relay_runtime.ports.speech import TurnDetector

logger = logging.getLogger(__name__)


def turn_detection_mode() -> str:
    """``silero`` = VAD-only endpointing; ``hybrid`` = Silero start + Smart Turn stop."""
    return os.environ.get("RELAY_TURN_DETECTOR", "hybrid").strip().lower()


def uses_hybrid_turn_detection() -> bool:
    return turn_detection_mode() in ("hybrid", "silero+smart", "smart")


@dataclass
class VoicePipelineHooks:
    """Async callbacks keyed by session_id."""

    on_speech_started: Callable[[str], Awaitable[None]]
    on_speech_ended: Callable[[str], Awaitable[None]]
    on_transcript_delta: Callable[[str, str], Awaitable[None]]
    on_transcript_final: Callable[[str, str], Awaitable[None]]


class RelayVadProcessor(FrameProcessor):
    """TurnDetector on ingress audio — emits speech boundary signals."""

    def __init__(self, *, session_id: str, turn_detector: TurnDetector, hooks: VoicePipelineHooks):
        super().__init__()
        self._session_id = session_id
        self._turn_detector = turn_detector
        self._hooks = hooks

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            rate = frame.audio_in_sample_rate or 16000
            if hasattr(self._turn_detector, "set_sample_rate"):
                self._turn_detector.set_sample_rate(rate)
        if isinstance(frame, InputAudioRawFrame):
            count = getattr(self, "_audio_frame_count", 0) + 1
            self._audio_frame_count = count
            if count == 1 or count % 250 == 0:
                logger.info(
                    "voice pipeline audio ingress session_id=%s frames=%s sample_rate=%s bytes=%s",
                    self._session_id,
                    count,
                    frame.sample_rate,
                    len(frame.audio),
                )
            signal = await self._turn_detector.on_audio_frame(self._session_id, frame.audio)
            if signal:
                if signal.get("type") == "speech_started":
                    await self._hooks.on_speech_started(self._session_id)
                    await self.push_frame(VADUserStartedSpeakingFrame(), direction)
                elif signal.get("type") == "speech_ended":
                    await self._hooks.on_speech_ended(self._session_id)
                    await self.push_frame(VADUserStoppedSpeakingFrame(), direction)
        await self.push_frame(frame, direction)


class RelayVadStartHookProcessor(FrameProcessor):
    """Fast ``on_speech_started`` for barge-in (VAD boundary, before semantic turn end)."""

    def __init__(self, *, session_id: str, hooks: VoicePipelineHooks) -> None:
        super().__init__()
        self._session_id = session_id
        self._hooks = hooks

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, VADUserStartedSpeakingFrame):
            await self._hooks.on_speech_started(self._session_id)
        await self.push_frame(frame, direction)


class RelayUserTurnProcessor(UserTurnProcessor):
    """Pipecat user turn FSM with Smart Turn stop → Relay ``on_speech_ended``."""

    def __init__(self, *, session_id: str, hooks: VoicePipelineHooks, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._session_id = session_id
        self._hooks = hooks

        @self.event_handler("on_user_turn_stopped")
        async def _on_user_turn_stopped(processor, strategy) -> None:
            del processor, strategy
            await hooks.on_speech_ended(session_id)


def append_voice_turn_processors(
    processors: list[Any],
    *,
    session_id: str,
    hooks: VoicePipelineHooks,
    turn_detector: TurnDetector | None,
    stt: Any | None,
) -> None:
    """Extend a SmallWebRTC ingress chain with VAD/STT/turn detection."""
    if uses_hybrid_turn_detection():
        from relay_adapter_speech_silero.smart_turn import build_hybrid_user_turn_strategies
        from relay_adapter_speech_silero.vad import build_vad_analyzer

        stop_timeout = float(os.environ.get("RELAY_USER_TURN_STOP_TIMEOUT_SECS", "8"))
        processors.extend(
            [
                VADProcessor(vad_analyzer=build_vad_analyzer()),
                RelayVadStartHookProcessor(session_id=session_id, hooks=hooks),
            ]
        )
        if stt is not None:
            processors.append(stt)
        processors.extend(
            [
                RelayUserTurnProcessor(
                    session_id=session_id,
                    hooks=hooks,
                    user_turn_strategies=build_hybrid_user_turn_strategies(),
                    user_turn_stop_timeout=stop_timeout,
                ),
                RelayTranscriptProcessor(session_id=session_id, hooks=hooks),
            ]
        )
        return

    if turn_detector is None:
        logger.warning("voice pipeline missing turn detector session_id=%s", session_id)
    else:
        processors.append(
            RelayVadProcessor(session_id=session_id, turn_detector=turn_detector, hooks=hooks)
        )
    if stt is not None:
        processors.append(stt)
    processors.append(RelayTranscriptProcessor(session_id=session_id, hooks=hooks))


class RelayTranscriptProcessor(FrameProcessor):
    """Map Pipecat STT frames to Relay transcript + turn finalization."""

    def __init__(self, *, session_id: str, hooks: VoicePipelineHooks):
        super().__init__()
        self._session_id = session_id
        self._hooks = hooks

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InterimTranscriptionFrame) and frame.text:
            await self._hooks.on_transcript_delta(self._session_id, frame.text)
        elif isinstance(frame, TranscriptionFrame) and frame.text:
            await self._hooks.on_transcript_final(self._session_id, frame.text)
        await self.push_frame(frame, direction)
