"""Creating sessions and reading one session's own data."""

from __future__ import annotations

from typing import Any

import os

from relay_gateway.core.errors import Disabled, Forbidden, NotFound, Unauthorized
from relay_gateway.models import PUBLISHABLE_KEY
from relay_gateway.services.auth_service import Principal
from relay_gateway.services.project_agent_service import ProjectAgentService
from relay_gateway.services.project_service import ProjectService
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
    ) -> None:
        self._manager = manager
        self._sessions = sessions
        self._events = events
        self._projects = projects
        self._project_agents = project_agents

    async def create_for_key(self, principal: Principal, *, agent_id: str, origin: str | None) -> dict[str, Any]:
        """Start a session in the key's project. The project comes from the key, never the caller."""
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
        created = await self._create(project_id=project.id, agent_id=agent_id)
        self._project_agents.bind_session(created["session_id"], project.id, agent_id)
        return created

    async def create_dev(self, *, project_id: str, agent_id: str) -> dict[str, Any]:
        """Unauthenticated session for local development and tests (``RELAY_DEV_SESSIONS=1``)."""
        if os.environ.get("RELAY_DEV_SESSIONS", "").lower() not in ("1", "true", "yes"):
            raise Disabled("dev sessions are disabled; create sessions with POST /v1/sessions and an API key")
        return await self._create(project_id=project_id, agent_id=agent_id)

    async def _create(self, *, project_id: str, agent_id: str) -> dict[str, Any]:
        """Mint a short-lived session token and emit SESSION_STARTED + SESSION_READY."""
        session, events = await self._manager.create_dev_session(project_id=project_id, agent_id=agent_id)
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
