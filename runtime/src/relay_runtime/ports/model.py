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
        """Stream model output chunks.

        ``{"type": "token", "text"}`` for text, at most one ``{"type": "tool_calls", "calls":
        [{"id", "name", "arguments"}]}``, and optionally one ``{"type": "usage", "model",
        "input_tokens", "output_tokens", "cached_input_tokens"}`` (see ``relay_runtime.model_usage``).
        """

    @abstractmethod
    async def cancel(self, session_id: str) -> None:
        ...
