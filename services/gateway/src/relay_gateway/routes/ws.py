"""WebSocket session stream for RP events and user text."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from relay_gateway.deps import session_manager

router = APIRouter(tags=["sessions-ws"])
logger = logging.getLogger(__name__)


@router.websocket("/ws/sessions/{session_id}")
async def session_websocket(session_id: str, websocket: WebSocket, token: str) -> None:
    if not session_manager.validate_dev_token(session_id, token):
        await websocket.close(code=4401)
        return
    session = session_manager.get(session_id)
    if session is None:
        await websocket.close(code=4404)
        return

    await websocket.accept()

    outbound: asyncio.Queue[str | None] = asyncio.Queue()

    async def on_event(event) -> None:
        await outbound.put(json.dumps(event.model_dump(mode="json")))

    unsubscribe = session_manager.event_gateway.subscribe(session_id, on_event)

    async def pump_outbound() -> None:
        while True:
            message = await outbound.get()
            if message is None:
                break
            await websocket.send_text(message)

    pump_task = asyncio.create_task(pump_outbound())

    async def run_user_text(text: str) -> None:
        try:
            await session_manager.submit_user_text(session_id, text)
        except RuntimeError as exc:
            await websocket.send_text(json.dumps({"type": "ERROR", "message": str(exc)}))
        except ValueError as exc:
            await websocket.send_text(json.dumps({"type": "ERROR", "message": str(exc)}))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "ERROR", "message": "invalid json"}))
                continue
            if body.get("type") == "USER_TEXT":
                text = str(body.get("text", ""))
                # Do not block the WS read loop — human STATE_SNAPSHOT must apply during long turns.
                asyncio.create_task(run_user_text(text))
            elif body.get("type") == "STATE_SNAPSHOT":
                state = body.get("state")
                if not isinstance(state, dict):
                    await websocket.send_text(
                        json.dumps({"type": "ERROR", "message": "state must be an object"})
                    )
                    continue
                try:
                    await session_manager.submit_client_state_snapshot(session_id, state)
                except KeyError:
                    await websocket.send_text(json.dumps({"type": "ERROR", "message": "session not found"}))
            elif body.get("type") == "ACTION_APPLIED":
                try:
                    await session_manager.submit_client_action_result(
                        session_id,
                        action_id=str(body.get("action_id", "")),
                        name=str(body.get("action", "")),
                        outcome="applied",
                        result=body.get("result") if isinstance(body.get("result"), dict) else None,
                    )
                except KeyError:
                    await websocket.send_text(json.dumps({"type": "ERROR", "message": "session not found"}))
            elif body.get("type") == "ACTION_FAILED":
                try:
                    await session_manager.submit_client_action_result(
                        session_id,
                        action_id=str(body.get("action_id", "")),
                        name=str(body.get("action", "")),
                        outcome="failed",
                        reason=str(body.get("reason", "failed")),
                    )
                except KeyError:
                    await websocket.send_text(json.dumps({"type": "ERROR", "message": "session not found"}))
            elif body.get("type") == "APP_EVENT":
                name = str(body.get("name", "event"))
                payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
                try:
                    await session_manager.submit_client_app_event(session_id, name=name, payload=payload)
                except KeyError:
                    await websocket.send_text(json.dumps({"type": "ERROR", "message": "session not found"}))
            elif body.get("type") == "VOICE_CANCEL":
                await session_manager.cancel_voice_utterance(session_id)
            elif body.get("type") == "PING":
                await websocket.send_text(json.dumps({"type": "PONG"}))
    except WebSocketDisconnect:
        logger.info("websocket disconnected session_id=%s", session_id)
    finally:
        unsubscribe()
        await outbound.put(None)
        await pump_task
