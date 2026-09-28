"""P09 — HITL approval grant over WebSocket commits and verifies."""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from relay_gateway.app import create_app


@pytest.fixture
def app():
    return create_app()


def test_p09_ws_approve_commit_verify(app):
    with TestClient(app) as client:
        created = client.post(
            "/dev/sessions",
            json={"project_id": "proj-mortgage", "agent_id": "agent-ref"},
        )
        body = created.json()
        session_id = body["session_id"]
        token = body["dev_token"]

        types: list[str] = []
        approval_id: str | None = None

        with client.websocket_connect(f"/ws/sessions/{session_id}?token={token}") as ws:
            ws.send_text(json.dumps({"type": "USER_TEXT", "text": "Find Rajesh Sharma"}))
            for _ in range(80):
                event = json.loads(ws.receive_text())
                types.append(str(event.get("type")))
                if event.get("type") == "TURN_COMPLETED":
                    break

            ws.send_text(json.dumps({"type": "USER_TEXT", "text": "Prepare correction draft"}))
            for _ in range(120):
                event = json.loads(ws.receive_text())
                types.append(str(event.get("type")))
                if event.get("type") == "TURN_COMPLETED":
                    break

            ws.send_text(json.dumps({"type": "USER_TEXT", "text": "Submit for approval"}))
            for _ in range(120):
                event = json.loads(ws.receive_text())
                types.append(str(event.get("type")))
                if event.get("type") == "APPROVAL_REQUESTED":
                    approval_id = str((event.get("payload") or {}).get("approval_id") or "")
                if event.get("type") == "TURN_COMPLETED" and approval_id:
                    break

            assert approval_id, f"expected APPROVAL_REQUESTED, saw {types[-20:]}"

            ws.send_text(
                json.dumps(
                    {
                        "type": "APP_EVENT",
                        "name": "approval.grant",
                        "payload": {
                            "approval_id": approval_id,
                            "auth_proof": "dev-approver",
                        },
                    }
                )
            )

            verified = False
            for _ in range(80):
                event = json.loads(ws.receive_text())
                types.append(str(event.get("type")))
                if event.get("type") == "COMMIT_VERIFIED":
                    verified = bool((event.get("payload") or {}).get("verified"))
                    break

        assert "APPROVAL_GRANTED" in types
        assert "COMMIT_STARTED" in types
        assert verified, f"expected verified commit, tail={types[-25:]}"
