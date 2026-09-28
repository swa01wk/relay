"""P02-TC-001 / P02-TC-003 — WebRTC offer/answer and session teardown (server-side)."""

from __future__ import annotations

import asyncio
import json

import pytest
from aiortc import RTCPeerConnection, RTCSessionDescription
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from relay_gateway.app import create_app
from relay_gateway import deps

pytest.importorskip("aiortc")


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_p02_tc_001_webrtc_offer_answer(app):
    """Valid SDP offer returns answer with pc_id (SmallWebRTC signaling)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/dev/sessions",
            json={"project_id": "proj-mortgage", "agent_id": "agent-ref"},
        )
        assert created.status_code == 200
        body = created.json()
        session_id = body["session_id"]
        token = body["dev_token"]

        pc = RTCPeerConnection()
        try:
            pc.addTransceiver("audio", direction="sendrecv")
            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)
            resp = await client.post(
                f"/sessions/{session_id}/webrtc/offer",
                params={"token": token},
                json={
                    "sdp": pc.localDescription.sdp,
                    "type": pc.localDescription.type,
                },
            )
            if resp.status_code == 503:
                pytest.skip("realtime transport disabled (RELAY_DISABLE_WEBRTC)")
            assert resp.status_code == 200, resp.text
            answer = resp.json()
            assert answer.get("sdp")
            assert answer.get("type") == "answer"
            assert answer.get("pc_id")
            await pc.setRemoteDescription(
                RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
            )
            for _ in range(50):
                if pc.iceConnectionState in ("connected", "completed"):
                    break
                await asyncio.sleep(0.1)
        finally:
            await pc.close()
            await deps.session_manager.end_session(session_id)


def test_p02_tc_003_websocket_session_survives_webrtc_signaling(app):
    """Text path still works when WebRTC routes are mounted (P02-TC-002 regression)."""
    with TestClient(app) as client:
        created = client.post(
            "/dev/sessions",
            json={"project_id": "proj-mortgage", "agent_id": "agent-ref"},
        )
        body = created.json()
        session_id = body["session_id"]
        token = body["dev_token"]
        with client.websocket_connect(f"/ws/sessions/{session_id}?token={token}") as ws:
            ws.send_text(json.dumps({"type": "USER_TEXT", "text": "hello"}))
            types = []
            for _ in range(30):
                event = json.loads(ws.receive_text())
                types.append(event.get("type"))
                if event.get("type") == "TURN_COMPLETED":
                    break
        assert "TRANSCRIPT_FINAL" in types
