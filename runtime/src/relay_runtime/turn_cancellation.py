"""Cooperative cancel for in-flight model + TTS (Phase 7 extends usage)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class TurnCancellation:
    """Session-scoped cancel token for one agent response / playout."""

    event: asyncio.Event = field(default_factory=asyncio.Event)

    def cancel(self) -> None:
        self.event.set()

    @property
    def is_cancelled(self) -> bool:
        return self.event.is_set()

    def reset(self) -> None:
        self.event.clear()
