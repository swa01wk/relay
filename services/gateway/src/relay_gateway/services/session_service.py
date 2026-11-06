"""Creating sessions and reading one session's own data."""

from __future__ import annotations

from typing import Any

import json
import os

from relay_gateway.core.errors import BadRequest, Disabled, Forbidden, NotFound, Unauthorized
from relay_gateway.models import PUBLISHABLE_KEY, SECRET_KEY
from relay_gateway.services.auth_service import Principal
from relay_gateway.services.key_alert_service import KeyAlertService
from relay_gateway.services.project_agent_service import ProjectAgentService
from relay_gateway.services.project_service import ProjectService
from relay_gateway.services.rate_limit_service import (
    SESSIONS_PER_END_USER,
    SESSIONS_PER_IP,
    SESSIONS_PER_KEY,
    RateLimitService,
)
from relay_gateway.repositories.event_repository import EventRepository
from relay_gateway.repositories.session_repository import SessionRepository
from relay_runtime import SessionManager
from relay_runtime.session_timeline import build_session_timeline


class SessionService:
    def __init__(
        self,
        manager: SessionManager,
        sessions: SessionRepository,
        events: EventRepository,
        projects: ProjectService,
        project_agents: ProjectAgentService,
        limits: RateLimitService,
        key_alerts: KeyAlertService | None = None,
    ) -> None:
        self._manager = manager
        self._sessions = sessions
        self._events = events
        self._projects = projects
        self._project_agents = project_agents
        self._limits = limits
        self._key_alerts = key_alerts

    async def create_for_key(
        self,
        principal: Principal,
        *,
        agent_id: str,
        origin: str | None,
        ip: str | None = None,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Start a session in the key's project. The project comes from the key, never the caller.

        ``user`` says which of the app's own users the session is for. Only a secret key may set
        it: the app's server has checked who is signed in, while a browser could claim anyone.
        """
        if user is not None and principal.kind != SECRET_KEY:
            raise Forbidden("only a secret key (from your server) can say which user a session is for")
        end_user = _clean_end_user(user) if user is not None else None
        await self._limits.take(SESSIONS_PER_KEY, principal.key_id)
        if end_user:
            await self._limits.take(SESSIONS_PER_END_USER, f"{principal.key_id}:{end_user['id']}")
        if principal.kind == PUBLISHABLE_KEY:
            # A publishable key is public: also limit each visitor's address.
            await self._limits.take(SESSIONS_PER_IP, f"{principal.key_id}:{ip}" if ip else None)
        project = await self._projects.get(principal.project_id) if principal.project_id else None
        if project is None:
            raise Unauthorized("this key does not belong to a project")
        # Publishable keys live in browsers; when origins are listed, only those pages may use them.
        if principal.kind == PUBLISHABLE_KEY and project.allowed_origins:
            if (origin or "").rstrip("/").lower() not in project.allowed_origins:
                raise Forbidden("this origin is not allowed for the project's publishable key")
        # Build (or reuse) the project's own runtime first: an unknown agent or a missing model
        # key is reported here, before any session exists.
        await self._project_agents.runtime_for(project.id, agent_id)
        if self._key_alerts is not None:
            await self._key_alerts.key_used(principal, ip)
        created = await self._create(project_id=project.id, agent_id=agent_id, end_user=end_user)
        self._project_agents.bind_session(created["session_id"], project.id, agent_id)
        return created

    async def create_dev(
        self, *, project_id: str, agent_id: str, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Unauthenticated session for local development and tests (``RELAY_DEV_SESSIONS=1``).

        ``user`` lets a local app's server exercise per-user tools without a secret key; it is
        trusted only because dev sessions are never enabled on a public gateway.
        """
        if os.environ.get("RELAY_DEV_SESSIONS", "").lower() not in ("1", "true", "yes"):
            raise Disabled("dev sessions are disabled; create sessions with POST /v1/sessions and an API key")
        end_user = _clean_end_user(user) if user is not None else None
        return await self._create(project_id=project_id, agent_id=agent_id, end_user=end_user)

    async def _create(
        self, *, project_id: str, agent_id: str, end_user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Mint a short-lived session token and emit SESSION_STARTED + SESSION_READY."""
        session, events = await self._manager.create_dev_session(
            project_id=project_id, agent_id=agent_id, end_user=end_user
        )
        return {
            "session_id": session.session_id,
            "token": session.dev_token,
            "dev_token": session.dev_token,  # earlier name, kept for existing clients
            "token_expires_at": session.token_expires_at.isoformat(),
            "events": [e.model_dump(mode="json") for e in events],
        }

    def require_token(self, session_id: str, token: str | None, *, detail: str = "invalid or expired dev token") -> None:
        if not self._sessions.token_is_valid(session_id, token):
            raise Unauthorized(detail)

    def describe(self, session_id: str, token: str) -> dict[str, Any]:
        self.require_token(session_id, token)
        session = self._sessions.get(session_id)
        if session is None:
            raise NotFound("session not found")
        return {
            "session_id": session.session_id,
            "project_id": session.project_id,
            "agent_id": session.agent_id,
            "trace_id": session.trace_id,
        }

    async def timeline(self, session_id: str, token: str) -> dict[str, Any]:
        """Ordered RP events + metrics/spans waterfall for the session's own token."""
        self.require_token(session_id, token)
        return build_session_timeline(await self._events.for_session(session_id))


_MAX_ATTRIBUTES = 20
_MAX_USER_HEADER = 4000


def _clean_end_user(user: dict[str, Any]) -> dict[str, Any]:
    """``{"id": "...", "attributes": {...}}`` with plain values only, small enough for a header."""
    user_id = str(user.get("id") or "").strip()
    if not user_id or len(user_id) > 200 or not user_id.isprintable():
        raise BadRequest("user.id must be 1–200 printable characters")
    attributes = user.get("attributes") or {}
    if not isinstance(attributes, dict) or len(attributes) > _MAX_ATTRIBUTES:
        raise BadRequest(f"user.attributes must be an object with at most {_MAX_ATTRIBUTES} entries")
    clean: dict[str, Any] = {}
    for key, value in attributes.items():
        if not isinstance(value, (str, int, float, bool)) or value is None:
            raise BadRequest(f"user.attributes.{key} must be a string, number or boolean")
        clean[str(key)[:64]] = value[:200] if isinstance(value, str) else value
    end_user: dict[str, Any] = {"id": user_id}
    if clean:
        end_user["attributes"] = clean
    if len(json.dumps(end_user, ensure_ascii=True)) > _MAX_USER_HEADER:
        raise BadRequest("user is too large")
    return end_user

