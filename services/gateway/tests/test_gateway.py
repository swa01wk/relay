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


def test_metrics_endpoint_is_off_by_default_and_token_protected(app, monkeypatch):
    monkeypatch.delenv("RELAY_METRICS_ENABLED", raising=False)
    monkeypatch.delenv("RELAY_METRICS_TOKEN", raising=False)
    with TestClient(app) as client:
        assert client.get("/metrics").status_code == 404

        monkeypatch.setenv("RELAY_METRICS_TOKEN", "s3cret")
        assert client.get("/metrics").status_code == 401
        assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
        ok = client.get("/metrics", headers={"Authorization": "Bearer s3cret"})
        assert ok.status_code == 200 and "relay_sessions_active" in ok.text

        monkeypatch.delenv("RELAY_METRICS_TOKEN")
        monkeypatch.setenv("RELAY_METRICS_ENABLED", "1")
        client.post("/dev/sessions", json={"project_id": "p", "agent_id": "anything-a-client-sends"})
        text = client.get("/metrics").text
        # Client-supplied agent ids are not used as label values.
        assert 'relay_sessions_total{agent="default",event="started"}' in text
        assert "anything-a-client-sends" not in text


def test_admin_inspector_and_audit_need_the_admin_token(app, monkeypatch):
    monkeypatch.delenv("RELAY_ADMIN_TOKEN", raising=False)
    with TestClient(app) as client:
        assert client.get("/admin").status_code == 404
        assert client.get("/admin/sessions").status_code == 404

        monkeypatch.setenv("RELAY_ADMIN_TOKEN", "adm1n")
        page = client.get("/admin")
        assert page.status_code == 200 and "Relay inspector" in page.text and "adm1n" not in page.text
        assert client.get("/admin/sessions").status_code == 401
        assert client.get("/admin/audit", headers={"Authorization": "Bearer nope"}).status_code == 401

        auth = {"Authorization": "Bearer adm1n"}
        created = client.post("/dev/sessions", json={"project_id": "p", "agent_id": "sales-crm"}).json()
        sessions = client.get("/admin/sessions", headers=auth).json()["sessions"]
        mine = next(s for s in sessions if s["session_id"] == created["session_id"])
        assert mine["agent_id"] == "sales-crm" and mine["live"] is True
        # The admin token reads any session's timeline; no session token involved.
        timeline = client.get(f"/admin/sessions/{created['session_id']}", headers=auth).json()
        assert timeline["event_count"] >= 2 and timeline["audit"] == []
        assert client.get("/admin/sessions/00000000-0000-0000-0000-000000000000", headers=auth).status_code == 404
        assert isinstance(client.get("/admin/audit", headers=auth).json()["entries"], list)
