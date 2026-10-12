"""P08-TC-002 — human snapshot during slow prepare_correction emits STATE_CONFLICT on WS."""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from relay_gateway.app import create_app


@pytest.fixture
def app():
    return create_app()


def test_p08_tc_002_ws_conflict_during_slow_prepare(app):
    with TestClient(app) as client:
        created = client.post(
            "/dev/sessions",
            json={"project_id": "proj-mortgage", "agent_id": "agent-ref"},
        )
        body = created.json()
        session_id = body["session_id"]
        token = body["dev_token"]

        received: list[dict] = []
        human_edit_payload = {
            "type": "STATE_SNAPSHOT",
            "state": {
                "screen": "correction_draft",
                "workflow": "correction_draft",
                "correction_draft": {
                    "mortgage_id": "MORT-2931",
                    "effective_date": "2025-08-01",
                    "status": "draft",
                },
            },
        }

        with client.websocket_connect(f"/ws/sessions/{session_id}?token={token}") as ws:
            ws.send_text(json.dumps({"type": "USER_TEXT", "text": "Find Rajesh Sharma"}))
            for _ in range(80):
                event = json.loads(ws.receive_text())
                received.append(event)
                if event.get("type") == "TURN_COMPLETED":
                    break

            ws.send_text(json.dumps({"type": "USER_TEXT", "text": "Prepare correction draft race"}))

            saw_tool = False
            conflict = False
            for _ in range(120):
                event = json.loads(ws.receive_text())
                received.append(event)
                if event.get("type") == "TOOL_CALL_STARTED" and (
                    event.get("payload") or {}
                ).get("name") == "prepare_correction":
                    saw_tool = True
                    ws.send_text(json.dumps(human_edit_payload))
                if event.get("type") == "STATE_CONFLICT":
                    conflict = True
                if event.get("type") == "TURN_COMPLETED":
                    break

        assert saw_tool, "prepare_correction tool was not started"
        assert conflict, f"expected STATE_CONFLICT, tail types: {[e.get('type') for e in received[-15:]]}"


def test_p08_browser_frame_order_app_event_before_ack_does_not_stall(app):
    """Web SDK sends APP_EVENT before ACTION_APPLIED; the awaited slow draft ack must still land."""
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
            for _ in range(80):
                event = json.loads(ws.receive_text())
                if event.get("type") == "TURN_COMPLETED":
                    break

            ws.send_text(json.dumps({"type": "USER_TEXT", "text": "Prepare correction draft slow"}))
            for _ in range(120):
                event = json.loads(ws.receive_text())
                received.append(event)
                payload = event.get("payload") or {}
                if event.get("type") == "ACTION_REQUESTED" and payload.get("action") == "SHOW_CORRECTION_DRAFT":
                    draft = dict(payload["params"]["draft"])
                    ws.send_text(json.dumps({"type": "STATE_SNAPSHOT", "state": {
                        "screen": "correction_draft", "correction_draft": draft}}))
                    ws.send_text(json.dumps({"type": "APP_EVENT", "name": "ui.correction_draft",
                                             "payload": {"mortgage_id": "MORT-2931"}}))
                    ws.send_text(json.dumps({"type": "ACTION_APPLIED", "action": "SHOW_CORRECTION_DRAFT",
                                             "action_id": payload["action_id"], "result": {"ok": True}}))
                    ws.send_text(json.dumps({"type": "STATE_SNAPSHOT", "state": {
                        "screen": "correction_draft",
                        "correction_draft": {**draft, "effective_date": "2025-08-01"}}}))
                if event.get("type") == "TURN_COMPLETED":
                    break

    types = [e.get("type") for e in received]
    assert "ACTION_APPLIED" in types
    assert "STATE_CONFLICT" in types, f"tail types: {types[-15:]}"
    assert types.index("ACTION_APPLIED") < types.index("TOOL_CALL_STARTED")
