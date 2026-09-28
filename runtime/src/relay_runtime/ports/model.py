"""LLM / model provider port.

POC: ``adapters/models/openai/`` behind ``ModelProvider``.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class ModelProvider(ABC):
    @abstractmethod
    async def stream_completion(
        self,
        session_id: str,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream model output chunks (tokens, tool calls, etc.)."""

    @abstractmethod
    async def cancel(self, session_id: str) -> None:
        ...
