"""Shared semantic state storage port."""

from abc import ABC, abstractmethod
from typing import Any


class StateStore(ABC):
    @abstractmethod
    async def get_snapshot(self, session_id: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def apply_delta(
        self,
        session_id: str,
        *,
        patch: list[dict[str, Any]],
        based_on_version: int,
    ) -> int:
        """Apply patch; return new state_version or raise on conflict."""
