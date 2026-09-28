"""P01-TC-001 — WebSocket text turn."""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from relay_gateway.app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_p00_tc_003_health(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_p00_tc_004_dev_session_ready(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/dev/sessions",
            json={"project_id": "proj-mortgage", "agent_id": "agent-ref"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"]
    assert body["dev_token"]
    types = [e["type"] for e in body["events"]]
    assert "SESSION_READY" in types
    assert body["events"][-1]["metadata"]["session_id"] == body["session_id"]


def test_p01_tc_001_websocket_text_turn(app):
    with TestClient(app) as client:
        created = client.post(
            "/dev/sessions",
            json={"project_id": "proj-mortgage", "agent_id": "agent-ref"},
        )
        assert created.status_code == 200
        body = created.json()
        session_id = body["session_id"]
        token = body["dev_token"]

        received: list[dict] = []
        with client.websocket_connect(f"/ws/sessions/{session_id}?token={token}") as ws:
            ws.send_text(json.dumps({"type": "USER_TEXT", "text": "hello"}))
            for _ in range(30):
                event = json.loads(ws.receive_text())
                received.append(event)
                if event.get("type") == "TURN_COMPLETED":
                    break

    types = [e["type"] for e in received]
    assert "TRANSCRIPT_FINAL" in types
    assert "RESPONSE_COMPLETED" in types
    assert "TURN_COMPLETED" in types
