"""P03-TC-003 — voice TurnManager FSM (PRD §6.2)."""

import pytest

from relay_runtime.turn_manager import TurnManager, TurnPhase, TurnTransitionError


def test_p03_tc_003_voice_happy_path():
    tm = TurnManager()
    tm.on_user_speech_started()
    assert tm.phase == TurnPhase.USER_SPEAKING
    tm.on_user_speech_ended()
    assert tm.phase == TurnPhase.ENDPOINTING
    tm.begin_turn("turn-v1", voice=True)
    assert tm.phase == TurnPhase.PROCESSING
    tm.complete_turn("turn-v1")
    assert tm.phase == TurnPhase.IDLE


def test_p03_tc_003_cancel_mid_utterance():
    tm = TurnManager()
    tm.on_user_speech_started()
    tm.cancel_utterance()
    assert tm.phase == TurnPhase.IDLE
    tm.begin_turn("text-1")
    assert tm.phase == TurnPhase.PROCESSING


def test_p03_tc_003_no_duplicate_turn_during_processing():
    tm = TurnManager()
    tm.begin_turn("t1")
    with pytest.raises(TurnTransitionError):
        tm.on_user_speech_started()


def test_p07_barge_in_from_agent_speaking():
    tm = TurnManager()
    tm.on_user_speech_started()
    tm.on_user_speech_ended()
    tm.begin_turn("turn-voice", voice=True)
    tm.enter_agent_speaking("turn-voice")
    tm.on_barge_in()
    assert tm.phase == TurnPhase.USER_SPEAKING
    assert tm.active_turn_id is None


def test_p04_agent_speaking_phase():
    tm = TurnManager()
    tm.on_user_speech_started()
    tm.on_user_speech_ended()
    tm.begin_turn("turn-voice", voice=True)
    tm.enter_agent_speaking("turn-voice")
    assert tm.phase == TurnPhase.AGENT_SPEAKING
    tm.complete_turn("turn-voice")
    assert tm.phase == TurnPhase.IDLE
