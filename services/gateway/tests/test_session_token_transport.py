"""Session tokens travel in a header or the WebSocket protocol list, not the URL (URL still accepted)."""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from relay_gateway.app import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _session(client) -> dict:
    return client.post("/dev/sessions", json={"project_id": "p", "agent_id": "a"}).json()


def test_websocket_token_as_a_subprotocol(client):
    s = _session(client)
    with client.websocket_connect(f"/ws/sessions/{s['session_id']}", subprotocols=["relay.v1", f"relay.token.{s['token']}"]) as ws:
        assert ws.accepted_subprotocol == "relay.v1"  # browsers drop the socket unless one is chosen
        ws.send_text(json.dumps({"type": "PING"}))
        assert json.loads(ws.receive_text()) == {"type": "PONG"}


def test_websocket_rejects_a_wrong_or_missing_token(client):
    s = _session(client)
    for protocols in (["relay.v1", "relay.token.wrong"], ["relay.v1"]):
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect(f"/ws/sessions/{s['session_id']}", subprotocols=protocols) as ws:
                ws.receive_text()
        assert closed.value.code == 4401


def test_older_clients_with_the_token_in_the_url_still_work(client):
    s = _session(client)
    with client.websocket_connect(f"/ws/sessions/{s['session_id']}?token={s['token']}") as ws:
        ws.send_text(json.dumps({"type": "PING"}))
        assert json.loads(ws.receive_text()) == {"type": "PONG"}
    assert client.get(f"/dev/sessions/{s['session_id']}?token={s['token']}").status_code == 200


def test_http_endpoints_take_the_token_as_a_bearer_header(client):
    s = _session(client)
    bearer = {"Authorization": f"Bearer {s['token']}"}
    assert client.get(f"/dev/sessions/{s['session_id']}", headers=bearer).status_code == 200
    assert client.get(f"/dev/sessions/{s['session_id']}/timeline", headers=bearer).status_code == 200
    assert client.get(f"/dev/sessions/{s['session_id']}", headers={"Authorization": "Bearer nope"}).status_code == 401
    # WebRTC signalling: the token check passes with the header (503 = no media transport in tests).
    offer = client.post(f"/sessions/{s['session_id']}/webrtc/offer", json={"sdp": "x", "type": "offer"}, headers=bearer)
    assert offer.status_code in (200, 400, 503)
    assert client.post(f"/sessions/{s['session_id']}/webrtc/offer", json={"sdp": "x", "type": "offer"}).status_code == 401
