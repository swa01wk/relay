"""Per-project agents, tools URLs and model keys: two customers on one gateway stay separate."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from relay_gateway.app import create_app
from relay_gateway.core import container

from gateway_test_support import run_turn

PASSWORD = "correct horse battery"


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _customer(client: TestClient, email: str) -> dict:
    """Sign up through the device flow and create a secret key: what a new customer has."""
    start = client.post("/v1/auth/device").json()
    form = {"code": start["user_code"], "email": email, "password": PASSWORD, "create": "1"}
    assert client.post("/v1/auth/device/verify", data=form).status_code == 200
    login = client.post("/v1/auth/device/token", json={"device_code": start["device_code"]}).json()
    project = login["project"]["id"]
    key = client.post(f"/v1/projects/{project}/keys", json={"kind": "secret"}, headers=_auth(login["token"])).json()
    return {"token": login["token"], "project": project, "key": key["key"], "base": f"/v1/projects/{project}"}


def _manifest(agent_id: str, host: str, **extra: str) -> str:
    lines = [f"agent_id: {agent_id}", f"tools_url: https://{host}", "system_prompt: You help with orders."]
    return "\n".join([*lines, *(f"{k}: {v}" for k, v in extra.items())]) + "\n"


def _push(client, customer, manifest: str, **body):
    return client.post(f"{customer['base']}/agents", json={"manifest": manifest, **body}, headers=_auth(customer["token"]))


def _session(client, customer, agent_id: str):
    return client.post("/v1/sessions", json={"agent_id": agent_id}, headers=_auth(customer["key"]))


def test_a_project_needs_its_own_agent_and_model_key(client, tenant_world):
    acme = _customer(client, "ops@acme.test")

    # Nothing is inherited from the gateway: not its agents, not its model key.
    missing = _session(client, acme, "sales-crm")
    assert missing.status_code == 404 and "relay agents push" in missing.json()["detail"]

    pushed = _push(client, acme, _manifest("orders", "tools.acme.test"))
    assert pushed.status_code == 200 and pushed.json()["tools"] == ["list_orders"]
    no_key = _session(client, acme, "orders")
    assert no_key.status_code == 409 and "relay secrets set openai" in no_key.json()["detail"]

    saved = client.put(f"{acme['base']}/secrets/openai", json={"value": "sk-acme-secret-1234"}, headers=_auth(acme["token"]))
    assert saved.json() == {"name": "openai", "hint": "…1234"}
    listed = client.get(f"{acme['base']}/secrets", headers=_auth(acme["token"])).json()["secrets"]
    assert listed[0]["set"] is True and listed[0]["hint"] == "…1234" and "sk-acme" not in str(listed)
    # Encrypted at rest: the repository never holds the key itself.
    stored = container.project_secret_repository._secrets[(acme["project"], "openai_api_key")]
    assert "sk-acme" not in stored.ciphertext

    session = _session(client, acme, "orders")
    assert session.status_code == 200
    events = run_turn(client, session.json(), "what orders do I have?")
    assert "SESSION_ERROR" not in [e["type"] for e in events]
    assert next(e for e in events if e["type"] == "RESPONSE_COMPLETED")["payload"]["text"] == "You have one order."
    assert tenant_world.model_keys[-1] == "sk-acme-secret-1234"

    # The tool call went to Acme's tools service, signed with Acme's signing secret.
    (call,) = tenant_world.tool_calls("tools.acme.test")
    assert call.url.path == "/tools/list_orders" and call.headers["X-Relay-Session"] == session.json()["session_id"]
    secret = client.post(f"{acme['base']}/tools-signing-secret", headers=_auth(acme["token"])).json()["signing_secret"]
    assert secret.startswith("rts_") and tenant_world.signature_is_valid(call, secret)
    assert not tenant_world.signature_is_valid(call, "rts_someone-elses-secret")
    discovery = next(r for r in tenant_world.requests if r.method == "GET" and r.url.host == "tools.acme.test")
    assert tenant_world.signature_is_valid(discovery, secret)


def test_two_customers_with_the_same_agent_id_never_cross(client, tenant_world):
    acme, globex = _customer(client, "a@acme-two.test"), _customer(client, "g@globex.test")
    for customer, host, key in ((acme, "tools.acme2.test", "sk-acme-two-0000"), (globex, "tools.globex.test", "sk-globex-1111")):
        client.put(f"{customer['base']}/secrets/openai", json={"value": key}, headers=_auth(customer["token"]))
        assert _push(client, customer, _manifest("assistant", host)).status_code == 200

    run_turn(client, _session(client, globex, "assistant").json(), "orders?")
    assert tenant_world.model_keys[-1] == "sk-globex-1111"
    assert len(tenant_world.tool_calls("tools.globex.test")) == 1 and tenant_world.tool_calls("tools.acme2.test") == []

    run_turn(client, _session(client, acme, "assistant").json(), "orders?")
    assert tenant_world.model_keys[-1] == "sk-acme-two-0000"
    assert len(tenant_world.tool_calls("tools.acme2.test")) == 1 and len(tenant_world.tool_calls("tools.globex.test")) == 1

    # Globex cannot see, replace, delete or read the secrets of Acme's project.
    theirs = f"/v1/projects/{acme['project']}"
    for response in (
        client.get(f"{theirs}/agents", headers=_auth(globex["token"])),
        client.post(f"{theirs}/agents", json={"manifest": _manifest("assistant", "evil.test")}, headers=_auth(globex["token"])),
        client.delete(f"{theirs}/agents/assistant", headers=_auth(globex["token"])),
        client.get(f"{theirs}/secrets", headers=_auth(globex["token"])),
        client.put(f"{theirs}/secrets/openai", json={"value": "sk-hijack-00000"}, headers=_auth(globex["token"])),
        client.post(f"{theirs}/tools-signing-secret", headers=_auth(globex["token"])),
    ):
        assert response.status_code == 404
    # Project keys cannot manage agents or secrets at all.
    assert client.get(f"{acme['base']}/agents", headers=_auth(acme["key"])).status_code == 401
    assert [a["agent_id"] for a in client.get(f"{acme['base']}/agents", headers=_auth(acme["token"])).json()["agents"]] == ["assistant"]


def test_changing_the_key_or_agent_applies_to_new_sessions_only(client, tenant_world):
    acme = _customer(client, "ops@acme-three.test")
    client.put(f"{acme['base']}/secrets/openai", json={"value": "sk-old-key-000001"}, headers=_auth(acme["token"]))
    _push(client, acme, _manifest("orders", "tools.old.test"))
    running = _session(client, acme, "orders").json()

    client.put(f"{acme['base']}/secrets/openai", json={"value": "sk-new-key-000002"}, headers=_auth(acme["token"]))
    _push(client, acme, _manifest("orders", "tools.new.test"))

    # The conversation already running keeps the agent it started with…
    run_turn(client, running, "orders?")
    assert len(tenant_world.tool_calls("tools.old.test")) == 1 and tenant_world.tool_calls("tools.new.test") == []
    # …and the next session picks up the new key and tools URL.
    run_turn(client, _session(client, acme, "orders").json(), "orders?")
    assert tenant_world.model_keys[-1] == "sk-new-key-000002" and len(tenant_world.tool_calls("tools.new.test")) == 1

    assert client.delete(f"{acme['base']}/secrets/openai", headers=_auth(acme["token"])).status_code == 200
    assert _session(client, acme, "orders").status_code == 409
    assert client.delete(f"{acme['base']}/agents/orders", headers=_auth(acme["token"])).status_code == 200
    assert client.delete(f"{acme['base']}/agents/orders", headers=_auth(acme["token"])).status_code == 404

    first = client.post(f"{acme['base']}/tools-signing-secret", headers=_auth(acme["token"])).json()["signing_secret"]
    again = client.post(f"{acme['base']}/tools-signing-secret", headers=_auth(acme["token"])).json()["signing_secret"]
    rotated = client.post(f"{acme['base']}/tools-signing-secret?rotate=true", headers=_auth(acme["token"])).json()
    assert first == again and rotated["signing_secret"] != first


def test_manifests_are_validated_and_cannot_reach_into_the_gateway(client, tenant_world, monkeypatch):
    acme = _customer(client, "ops@acme-four.test")

    def rejected(manifest: str, **body) -> str:
        response = _push(client, acme, manifest, **body)
        assert response.status_code == 400, response.text
        return response.json()["detail"]

    assert "missing tools_url" in rejected("agent_id: a\nsystem_prompt: hi\n")
    assert "system_prompt" in rejected("agent_id: a\ntools_url: https://tools.acme.test\n")
    assert "invalid YAML" in rejected("agent_id: [unclosed")
    assert "agent_id may use" in rejected(_manifest("../etc", "tools.acme.test"))
    assert "unknown secret" in client.put(f"{acme['base']}/secrets/aws", json={"value": "x" * 20},
                                          headers=_auth(acme["token"])).json()["detail"]
    # The operator's environment is never expanded into a customer's manifest…
    monkeypatch.setenv("RELAY_CRM_TOOLS_URL", "http://crm-tools:8091")
    assert "literal URL" in rejected("agent_id: a\ntools_url: ${RELAY_CRM_TOOLS_URL}\nsystem_prompt: hi\n")
    # …and prompt files on the gateway are never read: the client sends the text.
    assert "system_prompt" in rejected("agent_id: a\ntools_url: https://tools.acme.test\nsystem_prompt_file: /etc/passwd\n")
    ok = _push(client, acme, "agent_id: a\ntools_url: https://tools.acme.test\nsystem_prompt_file: prompt.md\n",
               system_prompt="Sent by the CLI.")
    assert ok.status_code == 200

    tenant_world.down_hosts.add("tools.down.test")
    assert "must answer GET" in rejected(_manifest("b", "tools.down.test"))

    # Outside local development, a tools URL must be public https — not the gateway's own network.
    monkeypatch.delenv("RELAY_ALLOW_PRIVATE_TOOLS_URLS")
    assert "https" in rejected("agent_id: c\ntools_url: http://example.com\nsystem_prompt: hi\n")
    for private in ("https://127.0.0.1:5432", "https://10.0.0.5", "https://169.254.169.254", "https://[::1]"):
        assert "private address" in rejected(f"agent_id: c\ntools_url: {private}\nsystem_prompt: hi\n"), private
    assert "credentials" in rejected("agent_id: c\ntools_url: https://user:pw@example.com\nsystem_prompt: hi\n")


def test_secrets_need_a_configured_encryption_key(client, tenant_world, monkeypatch):
    acme = _customer(client, "ops@acme-five.test")
    monkeypatch.delenv("RELAY_SECRETS_KEY")
    refused = client.put(f"{acme['base']}/secrets/openai", json={"value": "sk-acme-secret-1234"}, headers=_auth(acme["token"]))
    assert refused.status_code == 503 and "RELAY_SECRETS_KEY" in refused.json()["detail"]
