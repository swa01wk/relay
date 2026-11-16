"""Experience Center sandboxes in the example tools services: each visitor's changes stay theirs."""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

A = "sandbox_" + "a" * 20
B = "sandbox_" + "b" * 20


def _user(sandbox_id: str) -> dict[str, str]:
    return {"X-Relay-User": json.dumps({"id": sandbox_id})}


@pytest.fixture
def crm(tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_DB_PATH", str(tmp_path / "shared.db"))
    monkeypatch.setenv("CRM_SANDBOX_DIR", str(tmp_path / "sandboxes"))
    monkeypatch.delenv("RELAY_TOOLS_SIGNING_SECRET", raising=False)
    from crm_tools_api.main import app

    return TestClient(app)


def _deal_count(client: TestClient, sandbox_id: str | None) -> int:
    headers = {"X-Sandbox-Id": sandbox_id} if sandbox_id else {}
    return len(client.get("/dashboard", headers=headers).json()["deals"])


def _first_account(client: TestClient) -> str:
    return client.post("/tools/list_accounts", json={}).json()["accounts"][0]["id"]


def test_crm_writes_stay_in_the_visitors_sandbox(crm):
    before = _deal_count(crm, None)
    created = crm.post(
        "/tools/create_deal",
        headers=_user(A),
        json={"account_id": _first_account(crm), "product": "Sandbox deal", "amount_usd": 1000, "close_date": "2026-12-01"},
    )
    assert created.status_code == 200, created.text
    assert _deal_count(crm, A) == before + 1
    assert _deal_count(crm, B) == before  # another visitor
    assert _deal_count(crm, None) == before  # the shared database

    assert crm.post("/sandbox/reset", headers={"X-Sandbox-Id": A}).json() == {"reset": True}
    assert _deal_count(crm, A) == before
    assert crm.post("/sandbox/reset", headers={"X-Sandbox-Id": "../etc"}).status_code == 404


def test_crm_ignores_malformed_or_disabled_sandbox_ids(crm, monkeypatch, tmp_path):
    from crm_tools_api import sandbox

    assert sandbox.valid_id("sandbox_short") is None
    assert sandbox.valid_id("sandbox_" + "x" * 20 + "/..") is None
    monkeypatch.delenv("CRM_SANDBOX_DIR")
    assert sandbox.valid_id(A) is None


def test_crm_sweep_drops_expired_sandboxes(crm, monkeypatch):
    import os
    import time

    from crm_tools_api import sandbox

    _deal_count(crm, A)
    _deal_count(crm, B)
    old = time.time() - 3 * 3600
    os.utime(sandbox.path_for(A), (old, old))
    sandbox.sweep(force=True)
    assert not sandbox.path_for(A).exists() and sandbox.path_for(B).exists()


@pytest.fixture
def mortgage(monkeypatch):
    monkeypatch.setenv("MORTGAGE_SANDBOXES", "1")
    from mortgage_tools_api.main import app

    return TestClient(app)


def _rate(client: TestClient, sandbox_id: str | None, mortgage_id: str) -> float:
    headers = _user(sandbox_id) if sandbox_id else {}
    return client.post("/tools/get_mortgage", headers=headers, json={"mortgage_id": mortgage_id}).json()["mortgage"]["current_rate"]


def test_mortgage_corrections_stay_in_the_visitors_sandbox(mortgage):
    from mortgage_tools_api import logic, sandbox

    mortgage_id = next(iter(sandbox.SHARED.mortgages))
    sandbox.reset(A)
    sandbox.reset(B)
    # Sandboxes start from the seed as shipped, even if other tests changed the shared data.
    seed_rate = sandbox._PRISTINE.mortgages[mortgage_id]["current_rate"]
    shared_rate = _rate(mortgage, None, mortgage_id)
    committed = mortgage.post(
        "/tools/commit_correction",
        headers={**_user(A), "X-Mortgage-Commit-Token": logic.expected_commit_token()},
        json={"mortgage_id": mortgage_id, "effective_date": "2026-01-01", "proposed_rate": seed_rate + 1},
    )
    assert committed.status_code == 200, committed.text
    assert _rate(mortgage, A, mortgage_id) == seed_rate + 1
    assert _rate(mortgage, B, mortgage_id) == seed_rate
    assert _rate(mortgage, None, mortgage_id) == shared_rate

    assert mortgage.post("/sandbox/reset", headers={"X-Sandbox-Id": A}).status_code == 200
    assert _rate(mortgage, A, mortgage_id) == seed_rate
