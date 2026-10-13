"""Hosted auth: `relay login` device flow, projects, API keys, and key-authenticated sessions."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from relay_gateway.app import create_app
from relay_gateway.services.auth_service import hash_password, password_matches

PASSWORD = "correct horse battery"


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _login(client: TestClient, email: str, *, create: bool = True) -> dict:
    """Run the whole device flow the way the CLI and a browser would."""
    start = client.post("/v1/auth/device").json()
    assert start["verification_uri_complete"].endswith(start["user_code"])
    assert client.post("/v1/auth/device/token", json={"device_code": start["device_code"]}).json() == {
        "status": "pending"
    }
    form = {"code": start["user_code"], "email": email, "password": PASSWORD}
    if create:
        form["create"] = "1"
    page = client.post("/v1/auth/device/verify", data=form)
    assert page.status_code == 200 and "Terminal connected" in page.text, page.text
    approved = client.post("/v1/auth/device/token", json={"device_code": start["device_code"]}).json()
    assert approved["status"] == "approved" and approved["token"].startswith("rat_")
    # The token is handed over exactly once.
    assert client.post("/v1/auth/device/token", json={"device_code": start["device_code"]}).status_code == 404
    return approved


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_passwords_are_salted_and_verified():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first != second and PASSWORD not in first
    assert password_matches(PASSWORD, first) and not password_matches("wrong password!", first)
    assert not password_matches(PASSWORD, "not-a-hash")


def test_login_page_and_bad_approvals(client):
    assert "Connect your terminal" in client.get("/v1/auth/device/verify?code=ABCD-1234").text
    # Markup in the query string is escaped, never reflected.
    assert "<script>" not in client.get('/v1/auth/device/verify?code="><script>x</script>').text

    start = client.post("/v1/auth/device").json()
    form = {"code": start["user_code"], "email": "new@example.com", "password": PASSWORD}
    assert client.post("/v1/auth/device/verify", data=form).status_code == 401  # no such account yet
    assert client.post("/v1/auth/device/verify", data={**form, "create": "1", "password": "short"}).status_code == 400
    wrong_code = {**form, "create": "1", "code": "ZZZZ-ZZZZ", "email": "other@example.com"}
    assert client.post("/v1/auth/device/verify", data=wrong_code).status_code == 404
    assert client.post("/v1/auth/device/token", json={"device_code": "made-up"}).status_code == 404


MANIFEST = "agent_id: {agent}\ntools_url: https://tools.example.test\nsystem_prompt: You help with orders.\n"


def _ready_project(client: TestClient, token: str, project_id: str, agent: str = "sales-crm") -> None:
    """Give the project what a session needs: a model key and an agent."""
    assert client.put(f"/v1/projects/{project_id}/secrets/openai", json={"value": "sk-test-key-0001"},
                      headers=_auth(token)).status_code == 200
    pushed = client.post(f"/v1/projects/{project_id}/agents", json={"manifest": MANIFEST.format(agent=agent)},
                         headers=_auth(token))
    assert pushed.status_code == 200, pushed.text


def test_login_then_keys_then_session(client, tenant_world):
    login = _login(client, "dev@example.com")
    token, project_id = login["token"], login["project"]["id"]
    _ready_project(client, token, project_id)
    assert login["email"] == "dev@example.com"

    me = client.get("/v1/me", headers=_auth(token)).json()
    assert me["email"] == "dev@example.com" and [p["id"] for p in me["projects"]] == [project_id]
    assert client.get("/v1/me").status_code == 401

    secret = client.post(f"/v1/projects/{project_id}/keys", json={"kind": "secret", "name": "server"},
                         headers=_auth(token)).json()
    publishable = client.post(f"/v1/projects/{project_id}/keys", json={"kind": "publishable"},
                              headers=_auth(token)).json()
    assert secret["key"].startswith("rsk_") and publishable["key"].startswith("rpk_")
    listed = client.get(f"/v1/projects/{project_id}/keys", headers=_auth(token)).json()["keys"]
    assert len(listed) == 2 and all("key" not in k for k in listed)  # the key text is never shown again
    assert client.post(f"/v1/projects/{project_id}/keys", json={"kind": "account"},
                       headers=_auth(token)).status_code == 400

    # A project key starts sessions in its own project; it cannot manage the account.
    session = client.post("/v1/sessions", json={"agent_id": "sales-crm"}, headers=_auth(secret["key"]))
    assert session.status_code == 200
    body = session.json()
    assert body["token"] == body["dev_token"]
    described = client.get(f"/dev/sessions/{body['session_id']}?token={body['token']}").json()
    assert described["project_id"] == project_id
    assert client.get("/v1/me", headers=_auth(secret["key"])).status_code == 401
    assert client.post("/v1/sessions", json={"agent_id": "x"}, headers=_auth(token)).status_code == 401
    assert client.post("/v1/sessions", json={"agent_id": "x"}).status_code == 401

    # Publishable keys obey the project's allowed origins once any are set.
    assert client.post("/v1/sessions", json={"agent_id": "sales-crm"}, headers=_auth(publishable["key"])).status_code == 200
    origins = client.put(f"/v1/projects/{project_id}/origins", headers=_auth(token),
                         json={"allowed_origins": ["https://App.example.com/"]})
    assert origins.json()["allowed_origins"] == ["https://app.example.com"]
    browser = {**_auth(publishable["key"]), "Origin": "https://app.example.com"}
    assert client.post("/v1/sessions", json={"agent_id": "sales-crm"}, headers=browser).status_code == 200
    evil = {**_auth(publishable["key"]), "Origin": "https://evil.example"}
    assert client.post("/v1/sessions", json={"agent_id": "x"}, headers=evil).status_code == 403
    assert client.post("/v1/sessions", json={"agent_id": "sales-crm"}, headers=_auth(secret["key"])).status_code == 200
    assert client.put(f"/v1/projects/{project_id}/origins", headers=_auth(token),
                      json={"allowed_origins": ["not a url"]}).status_code == 400

    # Revoked keys stop working immediately.
    assert client.delete(f"/v1/projects/{project_id}/keys/{secret['id']}", headers=_auth(token)).status_code == 200
    assert client.post("/v1/sessions", json={"agent_id": "x"}, headers=_auth(secret["key"])).status_code == 401
    assert client.delete(f"/v1/projects/{project_id}/keys/{secret['id']}", headers=_auth(token)).status_code == 404

    assert client.post("/v1/auth/logout", headers=_auth(token)).status_code == 200
    assert client.get("/v1/me", headers=_auth(token)).status_code == 401


def test_accounts_cannot_touch_each_others_projects(client):
    alice = _login(client, "alice@example.com")
    bob = _login(client, "bob@example.com")
    alice_project = alice["project"]["id"]
    assert alice_project != bob["project"]["id"]

    for call in (
        lambda: client.get(f"/v1/projects/{alice_project}/keys", headers=_auth(bob["token"])),
        lambda: client.post(f"/v1/projects/{alice_project}/keys", json={}, headers=_auth(bob["token"])),
        lambda: client.put(f"/v1/projects/{alice_project}/origins", json={"allowed_origins": []},
                           headers=_auth(bob["token"])),
    ):
        assert call().status_code == 404

    # Signing in again (no "create") reuses the account and its project; duplicates are refused.
    again = _login(client, "alice@example.com", create=False)
    assert again["project"]["id"] == alice_project and again["token"] != alice["token"]
    start = client.post("/v1/auth/device").json()
    duplicate = {"code": start["user_code"], "email": "alice@example.com", "password": PASSWORD, "create": "1"}
    assert client.post("/v1/auth/device/verify", data=duplicate).status_code == 409

    second = client.post("/v1/projects", json={"name": "Staging"}, headers=_auth(alice["token"]))
    assert second.status_code == 201
    assert len(client.get("/v1/projects", headers=_auth(alice["token"])).json()["projects"]) == 2


def test_dev_sessions_are_off_unless_enabled(client, monkeypatch):
    monkeypatch.delenv("RELAY_DEV_SESSIONS")
    assert client.post("/dev/sessions", json={"project_id": "p", "agent_id": "a"}).status_code == 404
    monkeypatch.setenv("RELAY_DEV_SESSIONS", "1")
    assert client.post("/dev/sessions", json={"project_id": "p", "agent_id": "a"}).status_code == 200
