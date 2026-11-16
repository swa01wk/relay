"""End-user identity: the app's server says who a session is for; every tool call carries it, signed."""

from __future__ import annotations

import json

import httpx
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


def _business(client, email: str) -> dict:
    """A business with an agent, a model key, a secret key (server) and a publishable key (browser)."""
    start = client.post("/v1/auth/device").json()
    client.post("/v1/auth/device/verify", data={"code": start["user_code"], "email": email, "password": PASSWORD, "create": "1"})
    login = client.post("/v1/auth/device/token", json={"device_code": start["device_code"]}).json()
    token, base = login["token"], f"/v1/projects/{login['project']['id']}"
    client.put(f"{base}/secrets/openai", json={"value": "sk-test-key-0001"}, headers=_auth(token))
    manifest = "agent_id: meetings\ntools_url: https://tools.meetings.test\nsystem_prompt: Help with meetings.\n"
    assert client.post(f"{base}/agents", json={"manifest": manifest}, headers=_auth(token)).status_code == 200
    keys = {
        kind: client.post(f"{base}/keys", json={"kind": kind}, headers=_auth(token)).json()["key"]
        for kind in ("secret", "publishable")
    }
    signing = client.post(f"{base}/tools-signing-secret", headers=_auth(token)).json()["signing_secret"]
    return {**keys, "signing": signing}


def _session(client, key: str, user=None):
    body = {"agent_id": "meetings", **({"user": user} if user is not None else {})}
    return client.post("/v1/sessions", json=body, headers=_auth(key))


def test_each_users_tool_calls_say_who_is_asking(client, tenant_world):
    business = _business(client, "ops@ident.test")
    alice = _session(client, business["secret"], {"id": "u_alice", "attributes": {"role": "admin", "org": 7}}).json()
    bob = _session(client, business["secret"], {"id": "u_bob"}).json()

    run_turn(client, alice, "my top 10 meetings")
    run_turn(client, bob, "my top 10 meetings")
    alice_call, bob_call = tenant_world.tool_calls("tools.meetings.test")

    assert json.loads(alice_call.headers["X-Relay-User"]) == {"id": "u_alice", "attributes": {"org": 7, "role": "admin"}}
    assert json.loads(bob_call.headers["X-Relay-User"]) == {"id": "u_bob"}
    assert alice_call.headers["X-Relay-Session"] == alice["session_id"]
    for call in (alice_call, bob_call):
        assert tenant_world.signature_v2_is_valid(call, business["signing"])
        assert tenant_world.signature_is_valid(call, business["signing"])  # v1 still sent for existing checks


def test_the_signature_covers_the_user_the_session_and_the_tool(client, tenant_world):
    business = _business(client, "ops@tamper.test")
    run_turn(client, _session(client, business["secret"], {"id": "u_alice"}).json(), "meetings?")
    (call,) = tenant_world.tool_calls("tools.meetings.test")
    secret = business["signing"]

    def tampered(**headers: str) -> httpx.Request:
        return httpx.Request(call.method, call.url, headers={**call.headers, **headers}, content=call.content)

    assert tenant_world.signature_v2_is_valid(call, secret)
    # Someone replaying a captured call cannot change who it is for, which session, or which tool.
    assert not tenant_world.signature_v2_is_valid(tampered(**{"X-Relay-User": '{"id":"u_bob"}'}), secret)
    assert not tenant_world.signature_v2_is_valid(tampered(**{"X-Relay-Session": "other-session"}), secret)
    assert not tenant_world.signature_v2_is_valid(call, secret, operation="tools.call:delete_meeting")
    # The old v1 signature cannot tell these apart — which is why v2 exists.
    assert tenant_world.signature_is_valid(tampered(**{"X-Relay-User": '{"id":"u_bob"}'}), secret)

    discovery = next(r for r in tenant_world.requests if r.method == "GET")
    assert tenant_world.signature_v2_is_valid(discovery, secret, operation="tools.list")


def test_only_the_apps_server_can_say_who_the_user_is(client, tenant_world):
    business = _business(client, "ops@who.test")
    refused = _session(client, business["publishable"], {"id": "u_alice"})
    assert refused.status_code == 403 and "secret key" in refused.json()["detail"]
    # A browser session (publishable key, no user) still works, and its calls carry no user.
    browser = _session(client, business["publishable"]).json()
    run_turn(client, browser, "meetings?")
    (call,) = tenant_world.tool_calls("tools.meetings.test")
    assert "X-Relay-User" not in call.headers and tenant_world.signature_v2_is_valid(call, business["signing"])

    for bad in ({"id": ""}, {"id": "x" * 201}, {"id": "u", "attributes": {"nested": {"a": 1}}},
                {"id": "u", "attributes": {f"k{i}": i for i in range(21)}}):
        assert _session(client, business["secret"], bad).status_code in (400, 422), bad


def test_sessions_per_end_user_are_limited(client, tenant_world):
    business = _business(client, "ops@peruser.test")
    statuses = [_session(client, business["secret"], {"id": "u_busy"}).status_code for _ in range(31)]
    assert statuses[:30] == [200] * 30 and statuses[30] == 429
    assert _session(client, business["secret"], {"id": "u_other"}).status_code == 200


def test_the_example_tools_service_verifier_agrees_with_the_gateway():
    from crm_tools_api.relay_signature import signature_is_valid, signature_v2_is_valid
    from relay_adapter_tools_http import end_user_header, signed_headers

    user = end_user_header({"id": "u_alice", "attributes": {"role": "admin"}})
    body = b'{"limit": 10}'
    h = signed_headers("rts_x", body, operation="tools.call:list_meetings", session_id="s1", user=user)
    common = {"timestamp": h["X-Relay-Timestamp"], "session": "s1", "user": user, "body": body}
    assert signature_v2_is_valid("rts_x", operation="tools.call:list_meetings", signature=h["X-Relay-Signature-V2"], **common)
    assert not signature_v2_is_valid("rts_x", operation="tools.call:delete_meeting", signature=h["X-Relay-Signature-V2"], **common)
    assert not signature_v2_is_valid("rts_x", operation="tools.call:list_meetings", signature=h["X-Relay-Signature-V2"],
                                     **{**common, "user": end_user_header({"id": "u_bob"})})
    assert signature_is_valid("rts_x", timestamp=h["X-Relay-Timestamp"], signature=h["X-Relay-Signature"], body=body)
    old = signed_headers("rts_x", body, operation="tools.list", now=1_000_000)
    assert not signature_v2_is_valid("rts_x", timestamp=old["X-Relay-Timestamp"], operation="tools.list", session="",
                                     user="", signature=old["X-Relay-Signature-V2"], body=body)


def test_secret_key_used_from_a_new_address_emails_the_owner(client, tenant_world, monkeypatch):
    from relay_gateway.core import container
    from relay_gateway.integrations.email import EmailSender

    sent = []

    class Box(EmailSender):
        async def send(self, email):
            sent.append(email)

    monkeypatch.setattr(container.key_alert_service, "_sender", Box())
    monkeypatch.setenv("RELAY_TRUST_PROXY_HEADERS", "1")
    business = _business(client, "owner@alerts.test")

    def start_from(ip: str):
        return client.post("/v1/sessions", json={"agent_id": "meetings"},
                           headers={**_auth(business["secret"]), "X-Forwarded-For": ip})

    start_from("203.0.113.10")  # the business's server: first address, no alert
    start_from("203.0.113.10")
    assert sent == []
    start_from("198.51.100.66")  # somewhere new
    (alert,) = sent
    assert alert.to == "owner@alerts.test" and "198.51.100.66" in alert.text and "relay keys revoke" in alert.text
    start_from("198.51.100.66")  # known now
    assert len(sent) == 1
    # Publishable keys are used from every visitor's browser: never tracked.
    client.post("/v1/sessions", json={"agent_id": "meetings"},
                headers={**_auth(business["publishable"]), "X-Forwarded-For": "192.0.2.99"})
    assert len(sent) == 1
