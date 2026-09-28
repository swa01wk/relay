"""Silero VAD behind the ``TurnDetector`` port."""

from __future__ import annotations

import os
from typing import Any

from pipecat.audio.vad.vad_analyzer import VADState

from pipecat.audio.vad.vad_analyzer import VADParams

from relay_adapter_speech_silero.vad import build_vad_analyzer
from relay_runtime.ports.speech import TurnDetector


class SileroTurnDetector(TurnDetector):
    """Maps mic PCM chunks to speech start/end signals (Silero-only mode)."""

    def __init__(self, *, params: VADParams | None = None) -> None:
        if params is not None:
            from pipecat.audio.vad.silero import SileroVADAnalyzer

            self._analyzer = SileroVADAnalyzer(params=params)
        else:
            self._analyzer = build_vad_analyzer()
        self._last_state = VADState.QUIET
        self._sample_rate_set = False

    def set_sample_rate(self, sample_rate: int) -> None:
        self._analyzer.set_sample_rate(sample_rate)
        self._sample_rate_set = True

    async def on_audio_frame(self, session_id: str, frame: bytes) -> dict[str, Any] | None:
        del session_id
        if not self._sample_rate_set:
            self.set_sample_rate(16000)
        state = await self._analyzer.analyze_audio(frame)
        if state == self._last_state:
            return None
        prev = self._last_state
        self._last_state = state
        if prev != VADState.SPEAKING and state == VADState.SPEAKING:
            return {"type": "speech_started"}
        if prev == VADState.SPEAKING and state == VADState.QUIET:
            return {"type": "speech_ended"}
        return None


def build_turn_detector() -> TurnDetector:
    kind = os.environ.get("RELAY_TURN_DETECTOR", "hybrid").lower()
    if kind in ("hybrid", "silero+smart", "smart"):
        # Hybrid mode uses Pipecat UserTurnProcessor; port kept for silero-only fallback tests.
        return SileroTurnDetector()
    if kind in ("silero", "default"):
        return SileroTurnDetector()
    raise ValueError(f"unsupported RELAY_TURN_DETECTOR={kind!r}")
