"""Agent orchestration port.

POC: ``adapters/agents/`` (LangGraph or thin async handler).
"""

from abc import ABC, abstractmethod
from typing import Any

from relay_sdk import RelayEvent


class AgentAdapter(ABC):
    @abstractmethod
    async def on_turn(
        self,
        session_id: str,
        *,
        context: dict[str, Any],
    ) -> list[RelayEvent]:
        """Process a turn and return RP events to publish."""

    async def handle_runtime_event(
        self,
        session_id: str,
        *,
        event: RelayEvent,
        context: dict[str, Any],
    ) -> list[RelayEvent]:
        """Optional hook for runtime events (e.g. ``STATE_CONFLICT`` → recompute)."""
        del session_id, event, context
        return []

    def state_after_commit(
        self,
        *,
        state: dict[str, Any],
        tool_name: str,
        arguments: dict[str, Any],
        commit_result: dict[str, Any],
        verify_result: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Optional hook: the shared state to apply after an approved change was saved and
        verified (e.g. mark a draft as committed, refresh a summary). Return the full new state,
        or ``None`` to leave the state as it is. ``verify_result`` is the verify tool's result,
        or the commit result when the approval had no verify step."""
        del state, tool_name, arguments, commit_result, verify_result
        return None
