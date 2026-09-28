"""P07 — InterruptionManager FSM and heard-text policy."""

import pytest

from relay_runtime.interruption_manager import (
    InterruptionManager,
    InterruptionPhase,
    InterruptionTransitionError,
)
from relay_runtime.tool_registry import ToolClassification


def test_interruption_fsm_happy_path():
    im = InterruptionManager()
    assert im.phase == InterruptionPhase.IDLE
    im.on_agent_playout_started()
    assert im.phase == InterruptionPhase.AGENT_PLAYOUT
    im.on_barge_in_detected()
    assert im.phase == InterruptionPhase.INTERRUPTING
    im.on_interrupt_settled()
    assert im.phase == InterruptionPhase.USER_CAPTURE
    im.on_idle()
    assert im.phase == InterruptionPhase.IDLE


def test_interruption_fsm_rejects_barge_in_when_idle():
    im = InterruptionManager()
    with pytest.raises(InterruptionTransitionError):
        im.on_barge_in_detected()


def test_heard_prefix_is_subset_of_generated():
    generated = "ABCDEFGHIJ" * 5
    heard = InterruptionManager.heard_prefix(
        generated_text=generated,
        delivered_ms=250.0,
        total_audio_ms=1000.0,
    )
    assert heard
    assert heard in generated
    assert len(heard) < len(generated)


def test_p07_tc_004_side_effecting_result_discarded_on_interrupt():
    assert InterruptionManager.discard_tool_result_on_interrupt(
        classification=ToolClassification.SIDE_EFFECTING,
        turn_active=False,
    )
    assert not InterruptionManager.discard_tool_result_on_interrupt(
        classification=ToolClassification.READ_ONLY,
        turn_active=True,
    )
