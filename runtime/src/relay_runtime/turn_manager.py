"""Turn finite-state machine (PRD §6.2) — text and voice paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import logging

logger = logging.getLogger(__name__)


class TurnPhase(StrEnum):
    IDLE = "IDLE"
    USER_SPEAKING = "USER_SPEAKING"
    ENDPOINTING = "ENDPOINTING"
    PROCESSING = "PROCESSING"
    AGENT_SPEAKING = "AGENT_SPEAKING"


class TurnTransitionError(Exception):
    """Illegal FSM transition."""


@dataclass
class TurnManager:
    """Single turn owner per session."""

    _phase: TurnPhase = field(default=TurnPhase.IDLE, init=False)
    _active_turn_id: str | None = field(default=None, init=False)

    @property
    def phase(self) -> TurnPhase:
        return self._phase

    @property
    def active_turn_id(self) -> str | None:
        return self._active_turn_id

    def on_user_speech_started(self) -> None:
        if self._phase == TurnPhase.PROCESSING:
            raise TurnTransitionError(f"cannot start speech in phase {self._phase}")
        if self._phase in (TurnPhase.USER_SPEAKING, TurnPhase.ENDPOINTING):
            return
        if self._phase != TurnPhase.IDLE:
            raise TurnTransitionError(f"cannot start speech in phase {self._phase}")
        self._phase = TurnPhase.USER_SPEAKING

    def on_user_speech_ended(self) -> None:
        if self._phase != TurnPhase.USER_SPEAKING:
            raise TurnTransitionError(f"cannot end speech in phase {self._phase}")
        self._phase = TurnPhase.ENDPOINTING

    def cancel_utterance(self) -> None:
        if self._phase in (TurnPhase.USER_SPEAKING, TurnPhase.ENDPOINTING):
            self._phase = TurnPhase.IDLE
            return
        raise TurnTransitionError(f"cannot cancel utterance in phase {self._phase}")

    def begin_turn(self, turn_id: str, *, voice: bool = False) -> None:
        if voice:
            if self._phase != TurnPhase.ENDPOINTING:
                logger.warning(
                    "reject begin_turn voice turn_id=%s phase=%s active_turn_id=%s",
                    turn_id,
                    self._phase,
                    self._active_turn_id,
                )
                raise TurnTransitionError(f"cannot begin voice turn in phase {self._phase}")
        elif self._phase != TurnPhase.IDLE:
            logger.warning(
                "reject begin_turn turn_id=%s phase=%s active_turn_id=%s",
                turn_id,
                self._phase,
                self._active_turn_id,
            )
            raise TurnTransitionError(f"cannot begin turn in phase {self._phase}")
        self._phase = TurnPhase.PROCESSING
        self._active_turn_id = turn_id

    def enter_agent_speaking(self, turn_id: str) -> None:
        if self._phase != TurnPhase.PROCESSING or self._active_turn_id != turn_id:
            raise TurnTransitionError(
                f"cannot enter agent speaking for {turn_id} in phase {self._phase}"
            )
        self._phase = TurnPhase.AGENT_SPEAKING

    def on_barge_in(self) -> None:
        """User spoke during agent playout — resume capture for the next utterance (§6.2)."""
        if self._phase != TurnPhase.AGENT_SPEAKING:
            raise TurnTransitionError(f"cannot barge-in in phase {self._phase}")
        self._phase = TurnPhase.USER_SPEAKING
        self._active_turn_id = None

    def complete_turn(self, turn_id: str) -> None:
        if self._active_turn_id != turn_id:
            logger.warning(
                "reject complete_turn turn_id=%s phase=%s active_turn_id=%s",
                turn_id,
                self._phase,
                self._active_turn_id,
            )
            raise TurnTransitionError(
                f"cannot complete turn {turn_id} in phase {self._phase}"
            )
        if self._phase not in (TurnPhase.PROCESSING, TurnPhase.AGENT_SPEAKING):
            logger.warning(
                "reject complete_turn turn_id=%s phase=%s active_turn_id=%s",
                turn_id,
                self._phase,
                self._active_turn_id,
            )
            raise TurnTransitionError(
                f"cannot complete turn {turn_id} in phase {self._phase}"
            )
        self._phase = TurnPhase.IDLE
        self._active_turn_id = None
