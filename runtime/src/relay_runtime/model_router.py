"""Route model requests to a configured ModelProvider."""

from __future__ import annotations

from dataclasses import dataclass

from relay_runtime.ports.model import ModelProvider


@dataclass
class ModelRouter:
    provider: ModelProvider

    def get_provider(self) -> ModelProvider:
        return self.provider
