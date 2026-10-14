"""WebSocket session stream for RP events and client frames."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from relay_gateway.core.container import stream_service
from relay_gateway.core.http import offered_session_protocol, session_token

router = APIRouter(tags=["sessions-ws"])
logger = logging.getLogger(__name__)


@router.websocket("/ws/sessions/{session_id}")
async def session_websocket(session_id: str, websocket: WebSocket, token: str | None = None) -> None:
    refusal = stream_service.refusal_code(session_id, session_token(websocket, token))
    if refusal is not None:
        await websocket.close(code=refusal)
        return

    await websocket.accept(subprotocol=offered_session_protocol(websocket))

    outbound: asyncio.Queue[str | None] = asyncio.Queue()

    async def on_event(event) -> None:
        await outbound.put(json.dumps(event.model_dump(mode="json")))

    async def reply(message: dict[str, Any]) -> None:
        await websocket.send_text(json.dumps(message))

    async def pump_outbound() -> None:
        while True:
            message = await outbound.get()
            if message is None:
                break
            await websocket.send_text(message)

    detach = stream_service.attach(session_id, on_event)
    pump_task = asyncio.create_task(pump_outbound())

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                await reply({"type": "ERROR", "message": "invalid json"})
                continue
            # Never awaits work queued on the session actor (see StreamService.handle_frame).
            await stream_service.handle_frame(session_id, body, reply)
    except WebSocketDisconnect:
        logger.info("websocket disconnected session_id=%s", session_id)
    finally:
        detach()
        await outbound.put(None)
        await pump_task
