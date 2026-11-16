"""SmallWebRTC signaling for a session's media plane."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from relay_gateway.core.errors import BadRequest, NotFound, Unavailable
from relay_runtime import SessionManager


def _urls(value: str | None) -> tuple[str, ...]:
    return tuple(u.strip() for u in (value or "").split(",") if u.strip())


@dataclass(frozen=True)
class IceConfig:
    """STUN/TURN servers handed to browsers for voice.

    TURN credentials use the TURN REST scheme coturn supports with ``use-auth-secret``: the username
    is ``<expiry unix time>:<session id>`` and the password ``base64(HMAC-SHA1(secret, username))``,
    so they stop working on their own and the shared secret never leaves the gateway.
    """

    stun_urls: tuple[str, ...] = ()
    turn_urls: tuple[str, ...] = ()
    turn_secret: str | None = None
    turn_ttl_seconds: int = 3600

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> IceConfig:
        stun = env.get("RELAY_ICE_STUN_URL", "stun:stun.l.google.com:19302")
        return cls(
            stun_urls=_urls(stun),
            turn_urls=_urls(env.get("RELAY_TURN_URLS")),
            turn_secret=(env.get("RELAY_TURN_SECRET") or "").strip() or None,
            turn_ttl_seconds=max(60, int(env.get("RELAY_TURN_TTL_SECONDS", "3600") or 3600)),
        )

    def servers(self, session_id: str, *, now: float | None = None) -> list[dict[str, Any]]:
        servers: list[dict[str, Any]] = []
        if self.stun_urls:
            servers.append({"urls": list(self.stun_urls)})
        if self.turn_urls and self.turn_secret:
            expiry = int(now if now is not None else time.time()) + self.turn_ttl_seconds
            username = f"{expiry}:{session_id}"
            digest = hmac.new(self.turn_secret.encode(), username.encode(), hashlib.sha1).digest()
            servers.append(
                {"urls": list(self.turn_urls), "username": username, "credential": base64.b64encode(digest).decode()}
            )
        return servers


class RealtimeService:
    def __init__(self, manager: SessionManager, ice: IceConfig | None = None) -> None:
        self._manager = manager
        self._ice = ice or IceConfig()

    def ice_servers(self, session_id: str) -> dict[str, Any]:
        """ICE servers for this session's browser (call after checking the session token)."""
        return {"ice_servers": self._ice.servers(session_id), "ttl_seconds": self._ice.turn_ttl_seconds}

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
