"""Hybrid turn strategy wiring (log-driven: avoid transcription turn-start)."""

from pipecat.turns.user_start import VADUserTurnStartStrategy, TranscriptionUserTurnStartStrategy
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy

from relay_adapter_speech_silero.smart_turn import build_hybrid_user_turn_strategies


def test_hybrid_turn_start_is_vad_only() -> None:
    strategies = build_hybrid_user_turn_strategies()
    assert strategies.start is not None
    assert len(strategies.start) == 1
    assert isinstance(strategies.start[0], VADUserTurnStartStrategy)
    assert not any(isinstance(s, TranscriptionUserTurnStartStrategy) for s in strategies.start)


def test_hybrid_turn_stop_uses_smart_turn_analyzer() -> None:
    strategies = build_hybrid_user_turn_strategies()
    assert strategies.stop is not None
    assert len(strategies.stop) == 1
    assert isinstance(strategies.stop[0], TurnAnalyzerUserTurnStopStrategy)
