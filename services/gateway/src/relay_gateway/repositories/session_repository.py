"""Live sessions: the ones this gateway process currently holds in memory."""

from __future__ import annotations

from relay_runtime import SessionManager
from relay_runtime.session_manager import SessionRecord


class SessionRepository:
    def __init__(self, manager: SessionManager) -> None:
        self._manager = manager

    def get(self, session_id: str) -> SessionRecord | None:
        return self._manager.get(session_id)

    def is_live(self, session_id: str) -> bool:
        return self._manager.get(session_id) is not None

    def count(self) -> int:
        return len(self._manager._sessions)

    def token_is_valid(self, session_id: str, token: str | None) -> bool:
        return bool(token) and self._manager.validate_dev_token(session_id, token)

    def agent_label(self, session_id: str) -> str | None:
        """Registered agent id or ``default`` — ``agent_id`` is client-supplied text, so it is
        never used raw as a metrics label or log field."""
        session = self._manager.get(session_id)
        if session is None:
            return None
        return session.agent_id if session.agent_id in self._manager.agent_runtimes else "default"
