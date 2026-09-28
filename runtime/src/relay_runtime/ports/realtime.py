"""Realtime media transport port.

POC: ``adapters/realtime/pipecat/small_webrtc.py``
Post-POC: ``adapters/realtime/pipecat/livekit.py``
"""

from abc import ABC, abstractmethod
from typing import Any


class RealtimeTransport(ABC):
    """Browser/client realtime connection (WebRTC, WebSocket, telephony)."""

    @abstractmethod
    async def connect(self, session_id: str, *, offer: dict[str, Any] | None = None) -> dict[str, Any]:
        """Establish transport; return connection metadata (e.g. SDP answer)."""

    @abstractmethod
    async def disconnect(self, session_id: str) -> None:
        """Tear down transport for the session."""

    @abstractmethod
    async def is_connected(self, session_id: str) -> bool:
        """Whether the session transport is active."""

    async def patch_ice(
        self,
        session_id: str,
        *,
        pc_id: str,
        candidates: list[dict[str, Any]],
    ) -> None:
        """Apply remote ICE candidates (WebRTC signaling)."""
        raise NotImplementedError(f"{type(self).__name__} does not support ICE patching")

    async def push_output_pcm(
        self,
        session_id: str,
        *,
        audio: bytes,
        sample_rate: int,
        num_channels: int = 1,
    ) -> None:
        """Enqueue agent PCM for WebRTC egress (Phase 4+)."""

    async def finish_output_pcm(self, session_id: str) -> None:
        """Signal end of agent PCM for this utterance."""

    async def wait_output_drained(self, session_id: str) -> None:
        """Wait until queued agent audio has been sent to the client."""

    async def prepare_output_playout(self, session_id: str) -> None:
        """Reset egress after cancel so the next TTS utterance can play."""

    async def cancel_output(self, session_id: str) -> None:
        """Stop agent audio playout immediately."""
