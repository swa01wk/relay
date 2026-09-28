"""P06 — parallel tools over WebSocket."""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from relay_gateway.app import create_app


@pytest.fixture
def app():
    return create_app()


def test_p06_parallel_investigation_events(app):
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
            ws.send_text(
                json.dumps(
                    {
                        "type": "USER_TEXT",
                        "text": "Compare payments and rate history for this mortgage",
                    }
                )
            )
            for _ in range(80):
                event = json.loads(ws.receive_text())
                received.append(event)
                if event.get("type") == "TURN_COMPLETED":
                    break

    types = [e["type"] for e in received]
    assert "ACTIVITY_STARTED" in types
    assert "ACTIVITY_COMPLETED" in types
    assert types.count("TOOL_CALL_COMPLETED") >= 2
    completed = [e for e in received if e["type"] == "RESPONSE_COMPLETED"]
    assert completed
    assert "payment" in completed[-1]["payload"].get("text", "").lower()
