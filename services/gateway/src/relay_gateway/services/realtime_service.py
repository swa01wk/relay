"""SmallWebRTC signaling for a session's media plane."""

from __future__ import annotations

from typing import Any

from relay_gateway.core.errors import BadRequest, NotFound, Unavailable
from relay_runtime import SessionManager


class RealtimeService:
    def __init__(self, manager: SessionManager) -> None:
        self._manager = manager

    def _require_transport(self) -> None:
        if self._manager.realtime_transport is None:
            raise Unavailable("realtime transport unavailable")

    async def offer(self, session_id: str, offer: dict[str, Any]) -> dict[str, Any]:
        self._require_transport()
        try:
            return await self._manager.start_realtime(session_id, offer)
        except KeyError:
            raise NotFound("session not found") from None
        except ValueError as exc:
            raise BadRequest(str(exc)) from exc
        except RuntimeError as exc:
            raise Unavailable(str(exc)) from exc

    async def add_ice_candidates(self, session_id: str, *, pc_id: str, candidates: list[dict[str, Any]]) -> None:
        self._require_transport()
        try:
            await self._manager.patch_realtime_ice(session_id, pc_id=pc_id, candidates=candidates)
        except KeyError:
            raise NotFound("session not found") from None
        except ValueError as exc:
            raise BadRequest(str(exc)) from exc
