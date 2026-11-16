"""A client's live connection to its session: events out, client frames in."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from relay_gateway.repositories.session_repository import SessionRepository
from relay_runtime import SessionManager
from relay_sdk import RelayEvent

Reply = Callable[[dict[str, Any]], Awaitable[None]]
EventHandler = Callable[[RelayEvent], Awaitable[None]]


def _error(message: str) -> dict[str, Any]:
    return {"type": "ERROR", "message": message}


class StreamService:
    def __init__(self, manager: SessionManager, sessions: SessionRepository) -> None:
        self._manager = manager
        self._sessions = sessions

    def refusal_code(self, session_id: str, token: str | None) -> int | None:
        """WebSocket close code when the client may not attach (4401 bad token, 4404 no session)."""
        if not self._sessions.token_is_valid(session_id, token):
            return 4401
        if not self._sessions.is_live(session_id):
            return 4404
        return None

    def attach(self, session_id: str, on_event: EventHandler) -> Callable[[], None]:
        """Start delivering the session's events; the returned function detaches the client."""
        unsubscribe = self._manager.event_gateway.subscribe(session_id, on_event)
        self._manager.client_attached(session_id)

        def detach() -> None:
            unsubscribe()
            self._manager.client_detached(session_id)

        return detach

    async def handle_frame(self, session_id: str, body: dict[str, Any], reply: Reply) -> None:
        """Apply one frame from the client. Must return quickly: anything queued behind the
        session actor (a turn, an app event) runs as a task, or acks and human edits would
        stall behind a running turn."""
        kind = body.get("type")
        if kind == "USER_TEXT":
            asyncio.create_task(self._user_text(session_id, str(body.get("text", "")), reply))
        elif kind == "STATE_SNAPSHOT":
            state = body.get("state")
            if not isinstance(state, dict):
                await reply(_error("state must be an object"))
                return
            try:
                await self._manager.submit_client_state_snapshot(session_id, state)
            except KeyError:
                await reply(_error("session not found"))
        elif kind in ("ACTION_APPLIED", "ACTION_FAILED"):
            applied = kind == "ACTION_APPLIED"
            result = body.get("result") if applied and isinstance(body.get("result"), dict) else None
            try:
                await self._manager.submit_client_action_result(
                    session_id,
                    action_id=str(body.get("action_id", "")),
                    name=str(body.get("action", "")),
                    outcome="applied" if applied else "failed",
                    **({"result": result} if applied else {"reason": str(body.get("reason", "failed"))}),
                )
            except KeyError:
                await reply(_error("session not found"))
        elif kind == "APP_EVENT":
            payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
            asyncio.create_task(self._app_event(session_id, str(body.get("name", "event")), payload, reply))
        elif kind == "VOICE_CANCEL":
            await self._manager.cancel_voice_utterance(session_id)
        elif kind == "PING":
            await reply({"type": "PONG"})

    async def _user_text(self, session_id: str, text: str, reply: Reply) -> None:
        try:
            await self._manager.submit_user_text(session_id, text)
        except (RuntimeError, ValueError) as exc:
            await reply(_error(str(exc)))

    async def _app_event(self, session_id: str, name: str, payload: dict[str, Any], reply: Reply) -> None:
        try:
            await self._manager.submit_client_app_event(session_id, name=name, payload=payload)
        except KeyError:
            await reply(_error("session not found"))
