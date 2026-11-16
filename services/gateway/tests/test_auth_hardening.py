"""Sign-in protection: rate limits, lockout, sign-up policy, and what a copied CLI token can do."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

from relay_gateway.app import create_app
from relay_gateway.core import container

PASSWORD = "correct horse battery"


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _auth(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def _verify(client, email: str, *, password: str = PASSWORD, create: bool = False, headers=None, start=None):
    """Submit the approval page; pass ``start`` to retry the same `relay login` request."""
    start = start or client.post("/v1/auth/device", headers=headers).json()
    form = {"code": start["user_code"], "email": email, "password": password}
    if create:
        form["create"] = "1"
    return start, client.post("/v1/auth/device/verify", data=form, headers=headers)


def _login(
    client, email: str, *, create: bool = False, device: str = "laptop", headers=None, password: str = PASSWORD
) -> dict:
    start, page = _verify(client, email, create=create, headers=headers, password=password)
    assert page.status_code == 200, page.text
    approved = client.post("/v1/auth/device/token", json={"device_code": start["device_code"], "client_name": device})
    return approved.json()


def _age_reauth(token_id: str, minutes: int) -> None:
    """Pretend the password was last entered ``minutes`` ago on this device."""
    _hash, key = container.api_key_repository._keys[token_id]
    key.reauthenticated_at = datetime.now(timezone.utc) - timedelta(minutes=minutes)


def _token_id(client, token: str) -> str:
    sessions = client.get("/v1/auth/sessions", headers=_auth(token)).json()["sessions"]
    return next(s["id"] for s in sessions if s["current"])


def test_wrong_passwords_lock_the_account_without_revealing_it_exists(client):
    _login(client, "owner@lock.test", create=True)
    start = client.post("/v1/auth/device").json()  # one `relay login`, retried in the browser
    for _ in range(5):
        assert _verify(client, "owner@lock.test", password="wrong password!", start=start)[1].status_code == 401
    locked = _verify(client, "owner@lock.test", start=start)[1]  # even the right password, while locked
    assert locked.status_code == 429 and int(locked.headers["Retry-After"]) > 0
    assert "too many failed sign-ins" in locked.text
    # An unknown email behaves the same way: 401 first, then locked.
    for _ in range(5):
        assert _verify(client, "nobody@lock.test", password="wrong password!", start=start)[1].status_code == 401
    assert _verify(client, "nobody@lock.test", password="wrong password!", start=start)[1].status_code == 429
    # Other accounts are unaffected by one account's lock.
    assert _login(client, "other@lock.test", create=True)["status"] == "approved"


def test_per_address_limits_and_spoofed_forwarding_headers(client, monkeypatch):
    for n in range(5):
        assert _verify(client, f"user{n}@ip.test", create=True)[1].status_code == 200
    assert _verify(client, "user5@ip.test", create=True)[1].status_code == 429  # sign-ups per address
    # Without a trusted proxy, X-Forwarded-For is ignored: a client cannot pick a fresh address.
    spoofed = {"X-Forwarded-For": "203.0.113.9"}
    assert _verify(client, "user6@ip.test", create=True, headers=spoofed)[1].status_code == 429
    # Behind a trusted proxy, each real client address has its own allowance.
    monkeypatch.setenv("RELAY_TRUST_PROXY_HEADERS", "1")
    assert _verify(client, "user7@ip.test", create=True, headers=spoofed)[1].status_code == 200
    assert client.post("/v1/auth/device", headers={"X-Forwarded-For": "198.51.100.4, 203.0.113.9"}).status_code == 200


@pytest.mark.parametrize(
    ("mode", "allowlist", "email", "allowed"),
    [
        ("closed", "", "a@corp.test", False),
        ("allowlist", "boss@corp.test,@team.test", "boss@corp.test", True),
        ("allowlist", "boss@corp.test,@team.test", "dev@team.test", True),
        ("allowlist", "boss@corp.test,@team.test", "dev@other.test", False),
        ("allowlist", "@team.test", "dev@sub.team.test", False),
        ("alowlist", "", "a@corp.test", False),  # a typo in the mode closes sign-up, never opens it
        ("open", "", "anyone@x.test", True),
    ],
)
def test_signup_policy(client, monkeypatch, mode, allowlist, email, allowed):
    monkeypatch.setenv("RELAY_SIGNUP", mode)
    monkeypatch.setenv("RELAY_SIGNUP_ALLOWLIST", allowlist)
    page = _verify(client, email, create=True)[1]
    assert page.status_code == (200 if allowed else 403), page.text
    if not allowed:
        assert "sign-up is restricted" in page.text


def test_a_copied_cli_token_cannot_take_over_the_project(client):
    owner = _login(client, "owner@stolen.test", create=True)
    token, project = owner["token"], owner["project"]["id"]
    base = f"/v1/projects/{project}"
    # Right after login the password is fresh: changes work.
    assert client.post(f"{base}/keys", json={"kind": "publishable"}, headers=_auth(token)).status_code == 201

    # Later, someone uses a copy of the token from the credentials file.
    _age_reauth(_token_id(client, token), minutes=60)
    takeover_attempts = [
        client.post(f"{base}/keys", json={"kind": "secret"}, headers=_auth(token)),
        client.put(f"{base}/secrets/openai", json={"value": "sk-attacker-000000"}, headers=_auth(token)),
        client.post(f"{base}/agents", json={"manifest": "agent_id: a\ntools_url: https://evil.test\nsystem_prompt: x\n"},
                    headers=_auth(token)),
        client.delete(f"{base}/agents/a", headers=_auth(token)),
        client.post(f"{base}/tools-signing-secret", headers=_auth(token)),
        client.put(f"{base}/origins", json={"allowed_origins": ["https://evil.test"]}, headers=_auth(token)),
        client.post("/v1/auth/password", json={"current_password": "guess", "new_password": "new password 123"},
                    headers=_auth(token)),
    ]
    for response in takeover_attempts[:-1]:
        assert response.status_code == 403 and response.headers["X-Relay-Reauth"] == "required", response.text
    assert takeover_attempts[-1].status_code == 401  # changing the password needs the current one
    # Reading and removing access still work with the token alone.
    assert client.get(f"{base}/keys", headers=_auth(token)).status_code == 200
    assert client.get("/v1/me", headers=_auth(token)).status_code == 200

    # Guessing the password to unlock changes is limited too.
    for _ in range(4):  # the wrong current password above already counted once
        assert client.post("/v1/auth/reauth", json={"password": "wrong password!"}, headers=_auth(token)).status_code == 401
    assert client.post("/v1/auth/reauth", json={"password": PASSWORD}, headers=_auth(token)).status_code == 429


def test_the_owner_confirms_with_the_password_and_carries_on(client):
    owner = _login(client, "owner@reauth.test", create=True)
    token, base = owner["token"], f"/v1/projects/{owner['project']['id']}"
    _age_reauth(_token_id(client, token), minutes=16)
    assert client.post(f"{base}/keys", json={"kind": "secret"}, headers=_auth(token)).status_code == 403
    assert client.post("/v1/auth/reauth", json={"password": PASSWORD}, headers=_auth(token)).status_code == 200
    assert client.post(f"{base}/keys", json={"kind": "secret"}, headers=_auth(token)).status_code == 201


def test_devices_can_be_listed_and_signed_out_and_a_password_change_signs_out_the_rest(client):
    laptop = _login(client, "owner@devices.test", create=True, device="work-laptop")["token"]
    desktop = _login(client, "owner@devices.test", device="home-desktop")["token"]
    stolen_copy_of_desktop = desktop

    sessions = client.get("/v1/auth/sessions", headers=_auth(laptop)).json()["sessions"]
    assert {s["name"] for s in sessions} == {"relay CLI on work-laptop", "relay CLI on home-desktop"}
    assert [s["current"] for s in sessions].count(True) == 1 and all(s["expires_at"] for s in sessions)

    # Sign out one device from another.
    desktop_id = next(s["id"] for s in sessions if s["name"].endswith("home-desktop"))
    assert client.delete(f"/v1/auth/sessions/{desktop_id}", headers=_auth(laptop)).status_code == 200
    assert client.get("/v1/me", headers=_auth(stolen_copy_of_desktop)).status_code == 401

    # A password change keeps this device and signs out every other one.
    other = _login(client, "owner@devices.test", device="tablet")["token"]
    changed = client.post("/v1/auth/password", headers=_auth(laptop),
                          json={"current_password": PASSWORD, "new_password": "a brand new password"})
    assert changed.json() == {"status": "ok", "other_devices_signed_out": 1}
    assert client.get("/v1/me", headers=_auth(other)).status_code == 401
    assert client.get("/v1/me", headers=_auth(laptop)).status_code == 200
    assert _verify(client, "owner@devices.test")[1].status_code == 401  # old password no longer works
    assert _verify(client, "owner@devices.test", password="a brand new password")[1].status_code == 200

    # Sign out everywhere, including this device.
    _login(client, "owner@devices.test", device="phone", password="a brand new password")
    out = client.post("/v1/auth/logout", json={"everywhere": True}, headers=_auth(laptop)).json()
    assert out["signed_out"] >= 2 and client.get("/v1/me", headers=_auth(laptop)).status_code == 401


def test_cli_tokens_expire_and_lapse_when_unused(client):
    expiring = _login(client, "owner@expiry.test", create=True)["token"]
    idle = _login(client, "owner@expiry.test")["token"]
    _hash, expiring_key = container.api_key_repository._keys[_token_id(client, expiring)]
    _hash, idle_key = container.api_key_repository._keys[_token_id(client, idle)]
    expiring_key.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    idle_key.last_used_at = datetime.now(timezone.utc) - timedelta(days=15)
    for token in (expiring, idle):
        response = client.get("/v1/me", headers=_auth(token))
        assert response.status_code == 401 and "expired" in response.json()["detail"]


def test_session_and_polling_limits(client, monkeypatch, tenant_world):
    owner = _login(client, "owner@limits.test", create=True)
    token, base = owner["token"], f"/v1/projects/{owner['project']['id']}"
    client.put(f"{base}/secrets/openai", json={"value": "sk-test-key-0001"}, headers=_auth(token))
    client.post(f"{base}/agents", json={"manifest": "agent_id: a\ntools_url: https://tools.limits.test\nsystem_prompt: hi\n"},
                headers=_auth(token))
    publishable = client.post(f"{base}/keys", json={"kind": "publishable"}, headers=_auth(token)).json()["key"]

    monkeypatch.setenv("RELAY_TRUST_PROXY_HEADERS", "1")
    visitor = _auth(publishable, **{"X-Forwarded-For": "198.51.100.7"})
    statuses = [client.post("/v1/sessions", json={"agent_id": "a"}, headers=visitor).status_code for _ in range(31)]
    assert statuses[:30] == [200] * 30 and statuses[30] == 429
    # Another visitor of the same site is not affected.
    other_visitor = _auth(publishable, **{"X-Forwarded-For": "198.51.100.8"})
    assert client.post("/v1/sessions", json={"agent_id": "a"}, headers=other_visitor).status_code == 200

    start = client.post("/v1/auth/device").json()
    polls = [client.post("/v1/auth/device/token", json={"device_code": start["device_code"]}).status_code for _ in range(61)]
    assert polls[-1] == 429 and set(polls[:60]) == {200}


def test_limits_can_be_switched_off_for_load_tests(client, monkeypatch):
    monkeypatch.setenv("RELAY_RATE_LIMITS", "off")
    for n in range(8):
        assert _verify(client, f"load{n}@off.test", create=True)[1].status_code == 200
