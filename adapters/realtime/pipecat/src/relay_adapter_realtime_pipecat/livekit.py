"""LiveKit ``RealtimeTransport`` stub — post-POC migration target (PRD §5.4).

Replace ``PipecatSmallWebRtcTransport`` with this adapter when any §5.4 trigger applies:
- multi-party or server-side recording requirements
- TURN/STUN ops owned by a managed SFU
- telephony bridge into the same session fabric
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from relay_runtime.ports.realtime import RealtimeTransport


@dataclass
class LiveKitRealtimeTransport(RealtimeTransport):
    """Placeholder; not wired in the POC gateway."""

    async def connect(self, session_id: str, *, offer: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError("LiveKit transport is post-POC — see adapters/realtime/pipecat/livekit.py")

    async def disconnect(self, session_id: str) -> None:
        raise NotImplementedError("LiveKit transport is post-POC")

    async def is_connected(self, session_id: str) -> bool:
        return False

    async def patch_ice(
        self,
        session_id: str,
        *,
        pc_id: str,
        candidates: list[dict[str, Any]],
    ) -> None:
        raise NotImplementedError("LiveKit transport is post-POC")
