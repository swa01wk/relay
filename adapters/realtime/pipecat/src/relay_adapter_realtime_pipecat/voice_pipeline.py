"""Mic → VAD → STT → Relay session voice events."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
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


class OrderedHookDispatcher:
    """Runs a session's voice hooks in order without making the audio pipeline wait for them.

    The hooks hand work to the session actor and wait until it is handled. Awaited inline, a
    busy actor (e.g. finishing the previous reply) stalled the processor that called them —
    and the speech-start hook sits *before* speech recognition, so audio stopped reaching the
    recognizer and words were lost. Here each hook call is queued and a single drainer runs
    them one after another, so their order is kept and the pipeline never blocks.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[tuple[str, Callable[..., Awaitable[None]], tuple[Any, ...]]] = (
            asyncio.Queue()
        )
        self._drainer: asyncio.Task[None] | None = None

    def submit(self, name: str, hook: Callable[..., Awaitable[None]], *args: Any) -> None:
        self._queue.put_nowait((name, hook, args))
        if self._drainer is None or self._drainer.done():
            self._drainer = asyncio.get_running_loop().create_task(self._drain())

    async def _drain(self) -> None:
        while not self._queue.empty():
            name, hook, args = self._queue.get_nowait()
            try:
                await hook(*args)
            except Exception:
                logger.exception("voice hook %s failed session_id=%s", name, args[0] if args else "?")

    async def idle(self) -> None:
        """Wait until every queued hook has run (tests)."""
        while self._drainer is not None and not self._drainer.done():
            await asyncio.shield(self._drainer)


def non_blocking_hooks(hooks: VoicePipelineHooks) -> VoicePipelineHooks:
    """``hooks`` whose calls return at once and run in order on an ``OrderedHookDispatcher``."""
    dispatcher = OrderedHookDispatcher()

    def wrap(name: str) -> Callable[..., Awaitable[None]]:
        target = getattr(hooks, name)

        async def call(*args: Any) -> None:
            dispatcher.submit(name, target, *args)

        return call

    wrapped = VoicePipelineHooks(
        on_speech_started=wrap("on_speech_started"),
        on_speech_ended=wrap("on_speech_ended"),
        on_transcript_delta=wrap("on_transcript_delta"),
        on_transcript_final=wrap("on_transcript_final"),
    )
    wrapped.dispatcher = dispatcher  # type: ignore[attr-defined]
    return wrapped


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


class AudioIngressStats(FrameProcessor):
    """Measures the mic audio about to reach speech recognition; optionally records it.

    Logs once per call: seconds of audio vs. wall-clock seconds and gaps between frames
    (lost or late audio shows up as gaps). With ``RELAY_VOICE_AUDIO_DUMP_DIR`` set, the exact
    audio is also written to ``<dir>/<session_id>-<n>.wav`` for offline checks — a debugging
    aid for operators; never enable it where callers' audio must not be stored.
    """

    GAP_MS = 100.0

    def __init__(self, *, session_id: str) -> None:
        super().__init__()
        self._session_id = session_id
        self._first: float | None = None
        self._last: float | None = None
        self._audio_secs = 0.0
        self._gaps = 0
        self._gap_secs = 0.0
        self._max_gap_ms = 0.0
        self._wav: Any = None
        self._reported = False

    def _open_dump(self, sample_rate: int, channels: int) -> None:
        folder = os.environ.get("RELAY_VOICE_AUDIO_DUMP_DIR", "").strip()
        if not folder or self._wav is not None:
            return
        import wave
        from pathlib import Path

        Path(folder).mkdir(parents=True, exist_ok=True)
        n = 0
        while (path := Path(folder) / f"{self._session_id}-{n}.wav").exists():
            n += 1
        self._wav = wave.open(str(path), "wb")
        self._wav.setnchannels(channels)
        self._wav.setsampwidth(2)
        self._wav.setframerate(sample_rate)
        logger.info("voice audio dump session_id=%s path=%s", self._session_id, path)

    def _report(self) -> None:
        if self._reported or self._first is None or self._last is None:
            return
        self._reported = True
        logger.info(
            "voice audio ingress session_id=%s audio_secs=%.1f wall_secs=%.1f gaps=%d gap_secs=%.1f max_gap_ms=%.0f",
            self._session_id,
            self._audio_secs,
            self._last - self._first,
            self._gaps,
            self._gap_secs,
            self._max_gap_ms,
        )
        if self._wav is not None:
            self._wav.close()
            self._wav = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame) and frame.audio:
            now = time.monotonic()
            if self._last is not None:
                gap_ms = (now - self._last) * 1000.0
                if gap_ms > self.GAP_MS:
                    self._gaps += 1
                    self._gap_secs += gap_ms / 1000.0
                self._max_gap_ms = max(self._max_gap_ms, gap_ms)
            if self._first is None:
                self._first = now
                self._open_dump(frame.sample_rate, frame.num_channels)
            self._last = now
            channels = max(1, frame.num_channels)
            self._audio_secs += len(frame.audio) / 2 / channels / max(1, frame.sample_rate)
            if self._wav is not None:
                self._wav.writeframes(frame.audio)
        elif isinstance(frame, (EndFrame, CancelFrame)):
            self._report()
        await self.push_frame(frame, direction)

    async def cleanup(self) -> None:
        self._report()
        await super().cleanup()


def append_voice_turn_processors(
    processors: list[Any],
    *,
    session_id: str,
    hooks: VoicePipelineHooks,
    turn_detector: TurnDetector | None,
    stt: Any | None,
) -> None:
    """Extend a SmallWebRTC ingress chain with VAD/STT/turn detection."""
    hooks = non_blocking_hooks(hooks)
    if uses_hybrid_turn_detection():
        from relay_adapter_speech_silero.smart_turn import build_hybrid_user_turn_strategies
        from relay_adapter_speech_silero.vad import build_vad_analyzer

        stop_timeout = float(os.environ.get("RELAY_USER_TURN_STOP_TIMEOUT_SECS", "3"))
        processors.extend(
            [
                VADProcessor(vad_analyzer=build_vad_analyzer()),
                RelayVadStartHookProcessor(session_id=session_id, hooks=hooks),
            ]
        )
        if stt is not None:
            processors.extend([AudioIngressStats(session_id=session_id), stt])
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
