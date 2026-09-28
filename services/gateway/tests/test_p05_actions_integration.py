"""P05 — WebSocket actions + state + Rajesh search path."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from mortgage_tools_api.main import app as tools_app
from relay_gateway.app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_mortgage_tools_search_rajesh():
    transport = ASGITransport(app=tools_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/tools/search_customer", json={"query": "Rajesh Sharma"})
    assert resp.status_code == 200
    customers = resp.json()["customers"]
    assert any(c["name"] == "Rajesh Sharma" for c in customers)


def test_p05_websocket_search_and_state(app):
    with TestClient(app) as client:
        created = client.post(
            "/dev/sessions",
            json={"project_id": "proj-mortgage", "agent_id": "agent-ref"},
        )
        body = created.json()
        session_id = body["session_id"]
        token = body["dev_token"]

        received: list[dict] = []
        with client.websocket_connect(f"/ws/sessions/{session_id}?token={token}") as ws:
            ws.send_text(json.dumps({"type": "USER_TEXT", "text": "Find Rajesh Sharma"}))
            for _ in range(50):
                event = json.loads(ws.receive_text())
                received.append(event)
                if event.get("type") == "TURN_COMPLETED":
                    break

            ws.send_text(
                json.dumps(
                    {
                        "type": "STATE_SNAPSHOT",
                        "state": {
                            "screen": "mortgage_case",
                            "selected_entity": {"type": "mortgage", "id": "MORT-2931"},
                        },
                    }
                )
            )
            for _ in range(10):
                event = json.loads(ws.receive_text())
                received.append(event)
                if event.get("type") == "STATE_VERSION_ADVANCED":
                    break

            ws.send_text(
                json.dumps(
                    {
                        "type": "ACTION_FAILED",
                        "action": "UNKNOWN_ACTION",
                        "action_id": "test-action-1",
                        "reason": "no_handler_registered",
                    }
                )
            )
            for _ in range(10):
                event = json.loads(ws.receive_text())
                received.append(event)
                if event.get("type") == "ACTION_FAILED" and event.get("payload", {}).get(
                    "action_id"
                ) == "test-action-1":
                    break

    types = [e["type"] for e in received]
    assert "ACTION_REQUESTED" in types
    assert "OPEN_ENTITY" in {e.get("payload", {}).get("action") for e in received if e["type"] == "ACTION_REQUESTED"}
    assert "STATE_VERSION_ADVANCED" in types
    failed = [e for e in received if e["type"] == "ACTION_FAILED"]
    assert any(e["payload"].get("reason") == "no_handler_registered" for e in failed)
