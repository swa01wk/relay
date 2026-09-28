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
