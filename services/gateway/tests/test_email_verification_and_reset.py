"""Email confirmation after sign-up, and resetting a forgotten password by email."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

from relay_gateway.app import create_app
from relay_gateway.core import container
from relay_gateway.integrations.email import Email, EmailSender

PASSWORD = "correct horse battery"


class Mailbox(EmailSender):
    def __init__(self) -> None:
        self.sent: list[Email] = []

    async def send(self, email: Email) -> None:
        self.sent.append(email)

    def link(self, to: str, path: str) -> str:
        """The latest link to ``path`` emailed to ``to``, as a path + query."""
        for email in reversed(self.sent):
            match = re.search(rf"https?://[^/\s]+({re.escape(path)}\?token=[\w-]+)", email.text)
            if email.to == to and match:
                return match.group(1)
        raise AssertionError(f"no {path} link sent to {to}")


@pytest.fixture
def mailbox(monkeypatch):
    box = Mailbox()
    monkeypatch.setattr(container.account_email_service, "_sender", box)
    monkeypatch.setenv("RELAY_EMAIL_VERIFICATION", "required")
    return box


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _approve(client, email: str, *, password: str = PASSWORD, create: bool = False, start=None):
    start = start or client.post("/v1/auth/device").json()
    form = {"code": start["user_code"], "email": email, "password": password}
    if create:
        form["create"] = "1"
    return start, client.post("/v1/auth/device/verify", data=form)


def _poll(client, start) -> dict:
    return client.post("/v1/auth/device/token", json={"device_code": start["device_code"]}).json()


def test_signup_needs_the_email_confirmed_before_the_terminal_is_approved(client, mailbox):
    start, page = _approve(client, "new@verify.test", create=True)
    assert page.status_code == 200 and "we sent a confirmation link to new@verify.test" in page.text
    assert _poll(client, start) == {"status": "pending"}  # not signed in yet
    assert mailbox.sent[-1].subject == "Confirm your email for Relay" and PASSWORD not in mailbox.sent[-1].text

    # Signing in before confirming is refused, and a fresh link is sent.
    _start, refused = _approve(client, "new@verify.test", start=start)
    assert refused.status_code == 403 and "confirm your email first" in refused.text
    assert len(mailbox.sent) == 2
    first_link = mailbox.sent[0].text.split("token=")[1].split()[0]

    confirmed = client.get(mailbox.link("new@verify.test", "/v1/auth/verify-email"))
    assert confirmed.status_code == 200 and "Email confirmed" in confirmed.text
    # The earlier link was replaced by the newer one, and a used link cannot be reused.
    assert client.get(f"/v1/auth/verify-email?token={first_link}").status_code == 400
    assert client.get(mailbox.link("new@verify.test", "/v1/auth/verify-email")).status_code == 400

    _start, approved = _approve(client, "new@verify.test", start=start)
    assert approved.status_code == 200 and "Terminal connected" in approved.text
    assert _poll(client, start)["status"] == "approved"


def test_someone_who_registers_your_email_first_cannot_keep_you_out(client, mailbox):
    # An attacker signs up with the victim's address but cannot open the confirmation email.
    _approve(client, "victim@squat.test", password="attacker password 1", create=True)
    # The real owner signs up too: allowed, because nobody proved the address.
    start, page = _approve(client, "victim@squat.test", create=True)
    assert page.status_code == 200 and "confirmation link" in page.text
    client.get(mailbox.link("victim@squat.test", "/v1/auth/verify-email"))
    # The owner's password works; the attacker's does not.
    assert _approve(client, "victim@squat.test", password="attacker password 1")[1].status_code == 401
    assert _approve(client, "victim@squat.test", start=start)[1].status_code == 200
    # Once confirmed, the address can no longer be signed up again.
    assert _approve(client, "victim@squat.test", password="attacker password 2", create=True)[1].status_code == 409


def test_forgot_password_resets_it_and_signs_out_every_device(client, mailbox, monkeypatch):
    monkeypatch.setenv("RELAY_EMAIL_VERIFICATION", "off")  # an established account
    start, _ = _approve(client, "owner@reset.test", create=True)
    token = _poll(client, start)["token"]
    monkeypatch.setenv("RELAY_EMAIL_VERIFICATION", "required")

    assert "Reset your password" in client.get("/v1/auth/forgot-password").text
    sent = client.post("/v1/auth/forgot-password", data={"email": "Owner@Reset.test"})
    assert sent.status_code == 200 and "If an account exists" in sent.text
    # An unknown address gets the same answer, and no email is sent.
    before = len(mailbox.sent)
    assert "If an account exists" in client.post("/v1/auth/forgot-password", data={"email": "ghost@reset.test"}).text
    assert len(mailbox.sent) == before

    link = mailbox.link("owner@reset.test", "/v1/auth/reset-password")
    assert 'type="hidden" name="token"' in client.get(link).text
    reset_token = link.split("token=")[1]
    weak = client.post("/v1/auth/reset-password", data={"token": reset_token, "password": "short"})
    assert weak.status_code == 400  # the link is still usable after a rejected password
    done = client.post("/v1/auth/reset-password", data={"token": reset_token, "password": "my new password!"})
    assert done.status_code == 200 and "Password changed" in done.text

    assert client.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401  # signed out
    assert _approve(client, "owner@reset.test")[1].status_code == 401  # old password gone
    assert _approve(client, "owner@reset.test", password="my new password!")[1].status_code == 200
    again = client.post("/v1/auth/reset-password", data={"token": reset_token, "password": "another password!"})
    assert again.status_code == 400 and "invalid, used or expired" in again.text


def test_a_reset_also_lifts_a_lockout_and_confirms_the_email(client, mailbox):
    _approve(client, "locked@reset.test", create=True)  # never confirmed
    start = client.post("/v1/auth/device").json()
    for _ in range(5):
        _approve(client, "locked@reset.test", password="wrong password!", start=start)
    assert _approve(client, "locked@reset.test", start=start)[1].status_code == 429
    client.post("/v1/auth/forgot-password", data={"email": "locked@reset.test"})
    reset_token = mailbox.link("locked@reset.test", "/v1/auth/reset-password").split("token=")[1]
    client.post("/v1/auth/reset-password", data={"token": reset_token, "password": "fresh password 1"})
    # The reset link proved the inbox, so no separate confirmation is needed.
    assert _approve(client, "locked@reset.test", password="fresh password 1", start=start)[1].status_code == 200


def test_expired_links_and_link_addresses(client, mailbox, monkeypatch):
    client.post("/v1/auth/device/verify", data={})  # warm-up
    _approve(client, "late@links.test", create=True)
    link = mailbox.link("late@links.test", "/v1/auth/verify-email")
    for token in container.email_token_repository._tokens.values():
        token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert client.get(link).status_code == 400

    # Links use RELAY_PUBLIC_URL when it is set…
    monkeypatch.setenv("RELAY_PUBLIC_URL", "https://relay.example.com")
    client.post("/v1/auth/forgot-password", data={"email": "late@links.test"})
    assert "https://relay.example.com/v1/auth/reset-password?token=" in mailbox.sent[-1].text
    # …and a request for another host never gets a link pointing there (Host header injection).
    monkeypatch.delenv("RELAY_PUBLIC_URL")
    monkeypatch.delenv("RELAY_DEV_SESSIONS")
    before = len(mailbox.sent)
    refused = client.post("/v1/auth/forgot-password", data={"email": "late@links.test"}, headers={"Host": "evil.example"})
    assert refused.status_code == 503 and len(mailbox.sent) == before


def test_email_limits(client, mailbox):
    for _ in range(5):
        client.post("/v1/auth/forgot-password", data={"email": "spam@limits.test"})
    _approve(client, "spam@limits.test", create=True)  # 1 confirmation email
    for _ in range(4):
        assert client.post("/v1/auth/forgot-password", data={"email": "spam@limits.test"}).status_code == 200
    # Five emails to one address per hour; the sixth request is refused.
    limited = client.post("/v1/auth/forgot-password", data={"email": "spam@limits.test"})
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) > 0
    assert sum(1 for e in mailbox.sent if e.to == "spam@limits.test") == 5
