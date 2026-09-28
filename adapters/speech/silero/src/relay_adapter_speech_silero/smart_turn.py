"""Pipecat Smart Turn v3 — semantic end-of-turn (used with Silero VAD start)."""

from __future__ import annotations

import os

from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.turns.user_turn_strategies import UserTurnStrategies


def smart_turn_params_from_env() -> SmartTurnParams:
    stop_secs = float(os.environ.get("RELAY_SMART_TURN_STOP_SECS", "2.0"))
    pre_speech_ms = float(os.environ.get("RELAY_SMART_TURN_PRE_SPEECH_MS", "500"))
    max_duration_secs = float(os.environ.get("RELAY_SMART_TURN_MAX_DURATION_SECS", "8"))
    return SmartTurnParams(
        stop_secs=stop_secs,
        pre_speech_ms=pre_speech_ms,
        max_duration_secs=max_duration_secs,
    )


def build_hybrid_user_turn_strategies() -> UserTurnStrategies:
    """Silero VAD start + Smart Turn stop (no transcription turn-start).

    Pipecat defaults include ``TranscriptionUserTurnStartStrategy``, which fires
    on STT interims/finals and spuriously ``broadcast_interruption`` (worse on
    open speakers / echo). Hybrid mode already has VAD + ``RelayVadStartHookProcessor``
    for barge-in.
    """
    from pipecat.turns.user_start import VADUserTurnStartStrategy
    from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy

    analyzer = LocalSmartTurnAnalyzerV3(params=smart_turn_params_from_env())
    return UserTurnStrategies(
        start=[VADUserTurnStartStrategy()],
        stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=analyzer)],
    )
