"""A project's activity for its developers: sessions, one session's timeline, usage — and
nothing of another project's."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from relay_gateway.app import create_app

from gateway_test_support import run_turn

PASSWORD = "correct horse battery"


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _customer(client: TestClient, email: str, host: str) -> dict:
    start = client.post("/v1/auth/device").json()
    form = {"code": start["user_code"], "email": email, "password": PASSWORD, "create": "1"}
    assert client.post("/v1/auth/device/verify", data=form).status_code == 200
    login = client.post("/v1/auth/device/token", json={"device_code": start["device_code"]}).json()
    token, project = login["token"], login["project"]["id"]
    base = f"/v1/projects/{project}"
    key = client.post(f"{base}/keys", json={"kind": "secret"}, headers=_auth(token)).json()["key"]
    client.put(f"{base}/secrets/openai", json={"value": "sk-test-key-123456"}, headers=_auth(token))
    manifest = f"agent_id: orders\ntools_url: https://{host}\nsystem_prompt: You help with orders.\n"
    assert client.post(f"{base}/agents", json={"manifest": manifest}, headers=_auth(token)).status_code == 200
    return {"token": token, "key": key, "base": base, "host": host}


def _talk(client: TestClient, customer: dict, text: str, *, before_turn=None) -> str:
    session = client.post("/v1/sessions", json={"agent_id": "orders"}, headers=_auth(customer["key"])).json()
    if before_turn:
        before_turn()
    run_turn(client, session, text)
    return session["session_id"]


def test_developers_see_their_sessions_timelines_and_usage(client, tenant_world):
    tenant_world.usage = {"model": "gpt-test", "input_tokens": 120, "output_tokens": 30}
    acme = _customer(client, "dev@acme-activity.test", "tools.acme-activity.test")
    session_id = _talk(client, acme, "what orders do I have?")

    (row,) = client.get(f"{acme['base']}/sessions", headers=_auth(acme["token"])).json()["sessions"]
    assert row["session_id"] == session_id and row["agent_id"] == "orders" and row["turns"] == 1
    assert row["errors"] == 0 and "project_id" not in row

    detail = client.get(f"{acme['base']}/sessions/{session_id}", headers=_auth(acme["token"])).json()
    (turn,) = detail["turns"]
    assert turn["user_text"] == "what orders do I have?" and turn["assistant_text"] == "You have one order."
    assert "list_orders" in turn["tool_names"] and detail["errors"] == []
    assert detail["usage"]["model_calls"] == 2 and detail["usage"]["total_tokens"] == 300

    usage = client.get(f"{acme['base']}/usage?days=1", headers=_auth(acme["token"])).json()
    assert usage["truncated"] is False
    assert usage["total"]["sessions"] == 1 and usage["total"]["turns"] == 1
    assert usage["total"]["model"]["total_tokens"] == 300
    assert [a["agent_id"] for a in usage["by_agent"]] == ["orders"]
    assert usage["by_model"][0]["model"] == "gpt-test" and len(usage["by_day"]) == 1
    (tool,) = usage["tools"]
    assert tool["name"] == "list_orders" and tool["calls"] == 1 and tool["failures"] == 0


def test_failed_tool_calls_show_up_as_errors(client, tenant_world):
    acme = _customer(client, "dev@acme-failing.test", "tools.acme-failing.test")
    # The tools service goes down after the session started (discovery runs at session start).
    session_id = _talk(client, acme, "orders?", before_turn=lambda: tenant_world.down_hosts.add(acme["host"]))

    detail = client.get(f"{acme['base']}/sessions/{session_id}", headers=_auth(acme["token"])).json()
    assert any(e["code"] == "tool_failed:list_orders" for e in detail["errors"])
    (tool,) = client.get(f"{acme['base']}/usage", headers=_auth(acme["token"])).json()["tools"]
    assert tool["failures"] == 1


def test_another_projects_activity_looks_missing(client, tenant_world):
    acme = _customer(client, "dev@acme-private.test", "tools.acme-private.test")
    globex = _customer(client, "dev@globex-private.test", "tools.globex-private.test")
    session_id = _talk(client, acme, "orders?")

    for path in ("/sessions", f"/sessions/{session_id}", "/usage"):
        assert client.get(f"{acme['base']}{path}", headers=_auth(globex["token"])).status_code == 404
    # Acme's session id under Globex's own project is just as missing.
    assert client.get(f"{globex['base']}/sessions/{session_id}", headers=_auth(globex["token"])).status_code == 404
    assert client.get(f"{globex['base']}/sessions", headers=_auth(globex["token"])).json()["sessions"] == []
    # Project keys cannot read activity; only the account token can.
    assert client.get(f"{acme['base']}/sessions", headers=_auth(acme["key"])).status_code == 401
