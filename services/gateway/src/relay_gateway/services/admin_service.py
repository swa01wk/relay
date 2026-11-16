"""Operator views: recent sessions, one session in full, and the approvals/saves audit trail.

Off unless ``RELAY_ADMIN_TOKEN`` is set; every data call needs that token.
"""

from __future__ import annotations

import os
from typing import Any

from relay_gateway.core.errors import Disabled, NotFound
from relay_gateway.core.security import require_bearer
from relay_gateway.repositories.event_repository import EventRepository
from relay_gateway.repositories.session_repository import SessionRepository
from relay_runtime.session_audit import AUDIT_EVENT_TYPES, build_audit_trail
from relay_runtime.session_timeline import build_session_timeline


class AdminService:
    def __init__(self, sessions: SessionRepository, events: EventRepository) -> None:
        self._sessions = sessions
        self._events = events

    def require_enabled(self) -> str:
        token = os.environ.get("RELAY_ADMIN_TOKEN", "").strip()
        if not token:
            raise Disabled("admin endpoints are disabled")
        return token

    def authorize(self, authorization: str | None) -> None:
        require_bearer(authorization, self.require_enabled(), detail="invalid admin token")

    async def list_sessions(self, *, limit: int) -> list[dict[str, Any]]:
        rows = await self._events.session_summaries(limit=limit)
        for row in rows:
            row["live"] = self._sessions.is_live(row["session_id"])
        return rows

    async def session_detail(self, session_id: str) -> dict[str, Any]:
        events = await self._events.for_session(session_id)
        if not events:
            raise NotFound("session not found")
        timeline = build_session_timeline(events)
        timeline["audit"] = build_audit_trail(events)
        return timeline

    async def audit_trail(self, *, limit: int, session_id: str | None = None) -> list[dict[str, Any]]:
        """Approvals and saves across sessions, newest first."""
        # An entry spans up to three events (request, decision, commit result).
        events = await self._events.newest_of_types(AUDIT_EVENT_TYPES, limit=limit * 4, session_id=session_id)
        return build_audit_trail(events, limit=limit)
