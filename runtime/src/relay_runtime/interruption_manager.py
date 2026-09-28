"""Interruption FSM and heard-text policy (PRD §7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from relay_runtime.tool_registry import ToolClassification


class InterruptionPhase(StrEnum):
    IDLE = "IDLE"
    AGENT_PLAYOUT = "AGENT_PLAYOUT"
    INTERRUPTING = "INTERRUPTING"
    USER_CAPTURE = "USER_CAPTURE"


class InterruptionTransitionError(Exception):
    """Illegal interruption FSM transition."""


@dataclass
class InterruptionManager:
    """Per-session interruption state (orthogonal to TurnManager voice FSM)."""

    _phase: InterruptionPhase = field(default=InterruptionPhase.IDLE, init=False)

    @property
    def phase(self) -> InterruptionPhase:
        return self._phase

    def on_agent_playout_started(self) -> None:
        if self._phase not in (InterruptionPhase.IDLE, InterruptionPhase.USER_CAPTURE):
            raise InterruptionTransitionError(f"cannot start playout in {self._phase}")
        self._phase = InterruptionPhase.AGENT_PLAYOUT

    def on_barge_in_detected(self) -> None:
        if self._phase != InterruptionPhase.AGENT_PLAYOUT:
            raise InterruptionTransitionError(f"cannot barge-in in {self._phase}")
        self._phase = InterruptionPhase.INTERRUPTING

    def on_interrupt_settled(self) -> None:
        if self._phase != InterruptionPhase.INTERRUPTING:
            raise InterruptionTransitionError(f"cannot settle interrupt in {self._phase}")
        self._phase = InterruptionPhase.USER_CAPTURE

    def on_idle(self) -> None:
        self._phase = InterruptionPhase.IDLE

    @staticmethod
    def heard_prefix(
        *,
        generated_text: str,
        delivered_ms: float,
        total_audio_ms: float,
    ) -> str:
        """Map playout progress to a heard text prefix (heard ⊆ generated)."""
        if not generated_text:
            return ""
        total = max(total_audio_ms, delivered_ms, 0.0)
        if total <= 0:
            return ""
        ratio = min(1.0, delivered_ms / total)
        if ratio >= 0.999:
            return generated_text
        if ratio <= 0:
            return ""
        char_count = max(1, int(len(generated_text) * ratio))
        return generated_text[:char_count].rstrip()

    @staticmethod
    def discard_tool_result_on_interrupt(
        *,
        classification: ToolClassification,
        turn_active: bool,
    ) -> bool:
        """§7.3 — drop in-flight tool results when the turn was interrupted."""
        if turn_active:
            return False
        if classification == ToolClassification.SIDE_EFFECTING:
            return True
        return True
