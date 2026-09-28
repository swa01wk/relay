"""Silero VAD analyzer factory (ingress, separate from end-of-turn)."""

from __future__ import annotations

import os

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams


def vad_params_from_env() -> VADParams:
    stop_ms = float(os.environ.get("RELAY_ENDPOINTING_SILENCE_MS", "400"))
    stop_secs = max(stop_ms / 1000.0, 0.05)
    min_volume = float(os.environ.get("RELAY_VAD_MIN_VOLUME", "0.35"))
    return VADParams(stop_secs=stop_secs, min_volume=min_volume)


def build_vad_analyzer() -> SileroVADAnalyzer:
    return SileroVADAnalyzer(params=vad_params_from_env())
