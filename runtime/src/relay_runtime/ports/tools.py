"""Tool execution port (side-effecting work gated by HITL in later phases)."""

from abc import ABC, abstractmethod
from typing import Any


class ToolExecutor(ABC):
    @abstractmethod
    async def execute(
        self,
        session_id: str,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Run a registered tool and return a structured result."""
