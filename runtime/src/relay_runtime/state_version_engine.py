"""Optimistic concurrency for shared semantic state (PRD §10.1, §3.3)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from relay_runtime.context_manager import ContextManager


class StateApplyOutcome(StrEnum):
    APPLIED = "applied"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class StateApplyResult:
    outcome: StateApplyOutcome
    state_version: int
    expected_version: int | None = None
    actual_version: int | None = None


@dataclass
class StateVersionEngine:
    """Human snapshots always win; agent deltas require matching ``based_on_version``."""

    def apply_client_snapshot(self, context: ContextManager, snapshot: dict[str, Any]) -> StateApplyResult:
        version = context.apply_snapshot(snapshot)
        return StateApplyResult(outcome=StateApplyOutcome.APPLIED, state_version=version)

    def try_apply_agent_delta(
        self,
        context: ContextManager,
        patch: list[dict[str, Any]],
        *,
        based_on_version: int,
    ) -> StateApplyResult:
        if based_on_version != context.state_version:
            return StateApplyResult(
                outcome=StateApplyOutcome.CONFLICT,
                state_version=context.state_version,
                expected_version=based_on_version,
                actual_version=context.state_version,
            )
        version = context.apply_patch(patch)
        return StateApplyResult(outcome=StateApplyOutcome.APPLIED, state_version=version)
