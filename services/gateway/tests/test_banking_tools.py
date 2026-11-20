"""The banking example's tools service: signed calls, per-customer data, sandboxes and the bank's
rules (balances, transfer modes and limits, new-payee cooling, scheduled transfers, bills and
autopay, card controls and replacement, credit card statements, fixed deposits, disputes)."""

from __future__ import annotations

import inspect
import json
from datetime import timedelta
from pathlib import Path

import pytest
from starlette.testclient import TestClient

REPO = Path(__file__).resolve().parents[3]


def _as(user: str) -> dict[str, str]:
    return {"X-Relay-User": json.dumps({"id": user})}


@pytest.fixture
def bank(tmp_path, monkeypatch):
    monkeypatch.setenv("BANK_DB_PATH", str(tmp_path / "bank.db"))
    monkeypatch.setenv("BANK_SANDBOX_DIR", str(tmp_path / "sandboxes"))
    monkeypatch.delenv("RELAY_TOOLS_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("BANK_API_TOKEN", raising=False)
    from bank_api.main import app

    return TestClient(app)


def call(client: TestClient, tool: str, user: str | None = "alice", **args):
    return client.post(f"/tools/{tool}", headers=_as(user) if user else {}, json=args)


def _balance(client: TestClient, account: str = "ACC-01", user: str = "alice") -> int:
    return call(client, "get_account", user=user, account_id=account).json()["account"]["balance"]


def test_every_write_needs_approval_and_schemas_match_functions():
    from bank_api.tools import TOOL_SPECS

    writes = {"add_payee", "remove_payee", "transfer_money", "cancel_scheduled_transfer", "pay_bill", "set_bill_autopay", "set_card_lock",
              "update_card_controls", "report_card_lost", "pay_credit_card", "open_fixed_deposit", "close_fixed_deposit", "raise_dispute"}
    assert {n for n, s in TOOL_SPECS.items() if s.classification == "side_effecting"} == writes
    for name, spec in TOOL_SPECS.items():
        params = inspect.signature(spec.fn).parameters
        assert set(spec.properties) <= set(params), name
        assert set(spec.required) <= set(spec.properties), name
        required_args = {p for p, v in params.items() if v.default is inspect.Parameter.empty}
        assert required_args <= set(spec.required), name
        assert len(spec.properties) <= 20 or spec.classification == "read_only", name  # forms fit Relay's 20 fields
        assert spec.per_user or spec.classification == "read_only", name


def test_calls_must_be_signed_when_a_secret_is_set(bank, monkeypatch):
    monkeypatch.setenv("RELAY_TOOLS_SIGNING_SECRET", "s3cret")
    assert bank.get("/tools").status_code == 401
    assert call(bank, "list_accounts").status_code == 401
    monkeypatch.delenv("RELAY_TOOLS_SIGNING_SECRET")
    assert call(bank, "list_accounts", user=None).status_code == 401  # per-customer without a user
    assert call(bank, "get_fd_rates", user=None).status_code == 200


def test_seeded_customer_balances_history_and_statement(bank):
    ctx = call(bank, "get_my_context").json()
    assert ctx["customer"]["name"] == "Arjun Mehta" and len(ctx["accounts"]) == 2 and ctx["total_balance"] > 100000
    txns = call(bank, "list_transactions", limit=500).json()
    assert txns["total"] > 250
    salary = call(bank, "list_transactions", query="salary", direction="credit").json()
    assert salary["total"] >= 5 and all(t["amount"] == 172000 for t in salary["transactions"])
    # Running balances end at the account balance.
    latest = call(bank, "list_transactions", account_id="ACC-01", limit=1).json()["transactions"][0]
    assert latest["balance_after"] == _balance(bank)
    card = call(bank, "get_card", card_id="credit").json()["card"]
    st = card["statement"]
    assert st["status"] == "due" and st["total_due_now"] > 0 and st["minimum_due"] >= 200
    assert card["available_credit"] == card["credit_limit"] - card["outstanding"]
    assert call(bank, "get_month_summary").json()["top_categories"]
    flow = call(bank, "get_cash_flow", months=6).json()["months"]
    assert len(flow) == 6 and all(m["income"] >= 172000 for m in flow[:-1])


def test_transfers_modes_limits_and_new_payee_cooling(bank):
    before = _balance(bank)
    own = call(bank, "transfer_money", to="joint", amount=5000, note="Groceries").json()["transfer"]
    assert own["mode"] == "own" and _balance(bank) == before - 5000
    upi = call(bank, "get_transfer_quote", to="Rohan", amount=2000).json()
    assert upi["can_send"] and upi["mode"] == "upi"
    too_much_upi = call(bank, "get_transfer_quote", to="Rohan", amount=150000).json()
    assert not too_much_upi["can_send"] and "UPI" in too_much_upi["error"]
    assert "daily transfer limit" in call(bank, "transfer_money", to="Aai", amount=10_000_000).json()["error"]
    assert "balance" in call(bank, "transfer_money", to="Aai", amount=450_000).json()["error"]

    bad = call(bank, "add_payee", name="Priya Shah", account_number="12ab", ifsc="ICIC1234").json()
    assert set(bad["fields"]) == {"account_number", "ifsc"}
    payee = call(bank, "add_payee", name="Priya Shah", account_number="123456789012", ifsc="icic0001234").json()["payee"]
    assert payee["bank"] == "ICICI Bank" and "cooling_until" in payee
    assert "error" in call(bank, "add_payee", name="Priya again", account_number="123456789012", ifsc="ICIC0001234").json()
    assert call(bank, "transfer_money", to="Priya Shah", amount=30000).json()["transfer"]["mode"] == "imps"
    capped = call(bank, "transfer_money", to=payee["id"], amount=25000).json()
    assert capped["fields"] == {"amount": "new payee limit"}
    assert "error" in call(bank, "transfer_money", to="Nobody", amount=100).json()


def test_scheduled_and_standing_transfers(bank):
    from bank_api import logic

    later = (logic._today() + timedelta(days=10)).isoformat()
    s = call(bank, "transfer_money", to="Meera", amount=4000, transfer_date=later).json()["scheduled_transfer"]
    assert s["status"] == "active" and s["next_date"] == later and s["repeat"] == "once"
    monthly = call(bank, "transfer_money", to="Rohan", amount=500, repeat="monthly").json()["scheduled_transfer"]
    assert monthly["last_runs"][0]["ok"] and monthly["next_date"] > logic._today().isoformat()  # ran today, next month next
    active = {x["id"] for x in call(bank, "list_scheduled_transfers").json()["scheduled_transfers"]}
    assert {"SCH-01", "SCH-02", s["id"], monthly["id"]} <= active
    assert call(bank, "cancel_scheduled_transfer", scheduled_id=s["id"]).json()["scheduled_transfer"]["status"] == "cancelled"
    assert "error" in call(bank, "transfer_money", to="Meera", amount=10, transfer_date="2001-01-01").json()
    removed = call(bank, "remove_payee", payee_id="Landlord").json()
    assert removed["cancelled_scheduled_transfers"] == ["SCH-01"]


def test_bills_autopay_and_credit_card_payment(bank):
    bills = call(bank, "list_bills").json()
    electricity = next(b for b in bills["billers"] if b["id"] == "BLR-01")
    before = _balance(bank)
    part = call(bank, "pay_bill", biller_id="electricity", amount=1000).json()
    assert part["biller"]["bill"]["amount"] == electricity["bill"]["amount"] - 1000
    assert call(bank, "pay_bill", biller_id="BLR-01").json()["biller"]["bill"] is None
    assert _balance(bank) == before - electricity["bill"]["amount"]
    assert "nothing due" in call(bank, "pay_bill", biller_id="BLR-01").json()["fields"]["amount"]
    assert "full" in call(bank, "pay_bill", biller_id="LIC", amount=100).json()["error"]
    auto = call(bank, "set_bill_autopay", biller_id="broadband", enabled=True, max_amount=1500).json()
    assert auto["biller"]["autopay"] == {"enabled": True, "from_account": "ACC-01", "max_amount": 1500}

    due = call(bank, "get_credit_card_statement").json()["statement"]
    minimum = call(bank, "pay_credit_card", pay="minimum_due").json()
    assert minimum["statement"]["status"] == "minimum_paid" and minimum["payment"]["amount"] == due["minimum_due_now"]
    paid = call(bank, "pay_credit_card").json()
    assert paid["statement"]["status"] == "paid"
    assert "error" in call(bank, "pay_credit_card").json()


def test_cards_lock_controls_and_replacement(bank):
    locked = call(bank, "set_card_lock", card_id="2207", locked=True).json()["card"]
    assert locked["status"] == "locked"
    assert call(bank, "set_card_lock", card_id="CRD-01", locked=False).json()["card"]["status"] == "active"
    changed = call(bank, "update_card_controls", card_id="debit", international=True, atm_daily_limit=20000).json()["card"]
    assert changed["controls"]["international"] and changed["limits"]["atm_daily"] == 20000
    assert "atm_daily_limit" in call(bank, "update_card_controls", card_id="debit", atm_daily_limit=900000).json()["fields"]
    assert "atm" in call(bank, "update_card_controls", card_id="credit", atm=False).json()["fields"]
    before = _balance(bank)
    report = call(bank, "report_card_lost", card_id="debit", reason="stolen").json()
    assert report["blocked_card"]["status"] == "blocked" and report["replacement"]["status"] == "on_the_way"
    assert report["fee"] == 236 and _balance(bank) == before - 236
    assert report["replacement"]["controls"]["international"] is False
    assert "error" in call(bank, "set_card_lock", card_id="CRD-01", locked=True).json()
    # A replaced credit card keeps the balance and statement.
    owed = call(bank, "get_card", card_id="credit").json()["card"]["outstanding"]
    new = call(bank, "report_card_lost", card_id="credit", reason="damaged").json()["replacement"]
    assert new["outstanding"] == owed and call(bank, "pay_credit_card", card_id=new["id"]).json()["statement"]["status"] == "paid"


def test_fixed_deposits(bank):
    quote = call(bank, "get_fd_quote", user=None, amount=100000, tenure_months=12).json()["quote"]
    assert quote["rate"] == 6.8 and quote["maturity_amount"] > 106800
    assert "error" in call(bank, "get_fd_quote", user=None, amount=5000, tenure_months=12).json()
    before = _balance(bank)
    fd = call(bank, "open_fixed_deposit", amount=50000, tenure_months=24, payout="quarterly").json()["deposit"]
    assert fd["id"] == "FD-03" and fd["rate"] == 7.0 and fd["quarterly_interest"] == 875 and _balance(bank) == before - 50000
    deposits = {d["id"]: d for d in call(bank, "list_fixed_deposits").json()["deposits"]}
    assert deposits["FD-02"]["interest_paid"] == 1750  # one quarterly payout since it opened
    closure = call(bank, "get_fd_closure_quote", deposit_id="FD-01").json()["closure"]
    assert closure["effective_rate"] == closure["rate_for_time_held"] - 1 and closure["payout"] < closure["payout_at_maturity"]
    done = call(bank, "close_fixed_deposit", deposit_id="FD-01").json()
    assert done["deposit"]["status"] == "closed" and _balance(bank) == before - 50000 + closure["payout"]
    assert "error" in call(bank, "close_fixed_deposit", deposit_id="FD-01").json()


def test_disputes(bank):
    zomato = call(bank, "list_transactions", query="zomato", account_id="credit", limit=50).json()["transactions"]
    flagged = [t for t in zomato if t.get("possible_duplicate")]
    assert len(flagged) == 2 and flagged[0]["amount"] == flagged[1]["amount"]
    pair = flagged[0]
    dup = call(bank, "get_transaction", transaction_id=pair["id"]).json()["transaction"]
    assert dup["can_dispute"] and dup["possible_duplicate_of"]
    owed = call(bank, "get_card", card_id="credit").json()["card"]["outstanding"]
    dispute = call(bank, "raise_dispute", transaction_id=dup["id"], reason="charged_twice").json()
    assert dispute["dispute"]["provisional_credit"] == dup["amount"]
    assert call(bank, "get_card", card_id="credit").json()["card"]["outstanding"] == owed - dup["amount"]
    assert "already disputed" in call(bank, "raise_dispute", transaction_id=dup["id"], reason="other", details="Still wrong, please check.").json()["error"]
    salary = call(bank, "list_transactions", query="salary", limit=1).json()["transactions"][0]
    assert "error" in call(bank, "raise_dispute", transaction_id=salary["id"], reason="unauthorized").json()
    uber = call(bank, "list_transactions", query="uber", limit=1).json()["transactions"][0]
    assert "details" in call(bank, "raise_dispute", transaction_id=uber["id"], reason="wrong_amount").json()["fields"]
    assert call(bank, "list_disputes").json()["total"] == 1


def test_every_read_tool_answers(bank):
    from bank_api.tools import TOOL_SPECS

    txn = call(bank, "list_transactions", limit=1).json()["transactions"][0]["id"]
    samples = {
        "get_account": {"account_id": "ACC-02"},
        "get_transaction": {"transaction_id": txn},
        "get_payee": {"payee_id": "PAY-02"},
        "get_transfer_quote": {"to": "Aai", "amount": 1000},
        "get_card": {"card_id": "CRD-02"},
        "get_fd_quote": {"amount": 25000, "tenure_months": 6},
        "get_fd_closure_quote": {"deposit_id": "FD-02"},
        "search_all": {"query": "amazon"},
    }
    for name, spec in TOOL_SPECS.items():
        if spec.classification != "read_only":
            continue
        res = call(bank, name, **samples.get(name, {}))
        assert res.status_code == 200 and "error" not in res.json(), (name, res.text)


def test_customers_and_sandboxes_are_apart_and_site_api(bank, monkeypatch):
    a, b = "sandbox_" + "a" * 20, "sandbox_" + "b" * 20
    call(bank, "add_payee", user=a, name="Sandbox Friend", upi_id="friend@okaxis")
    assert call(bank, "list_payees", user=a).json()["total"] == 6
    assert call(bank, "list_payees", user=b).json()["total"] == 5
    assert bank.get("/api/payees", headers={"X-Bank-User": a}).json()["total"] == 6
    assert bank.post("/sandbox/reset", headers={"X-Sandbox-Id": a}).json() == {"reset": True}
    assert call(bank, "list_payees", user=a).json()["total"] == 5
    call(bank, "transfer_money", user="bob", to="joint", amount=1000)
    assert _balance(bank, "ACC-02", user="bob") == _balance(bank, "ACC-02", user="carol") + 1000

    res = bank.post("/api/transfers", headers={"X-Bank-User": "carol"}, json={"to": "Rohan"})
    assert res.status_code == 400 and "amount" in res.json()["fields"]
    ok = bank.post("/api/transfers", headers={"X-Bank-User": "carol"}, json={"to": "Rohan", "amount": "1,200", "note": "Movie"})
    assert ok.status_code == 200 and ok.json()["transfer"]["amount"] == 1200
    off = bank.patch("/api/cards/CRD-01/controls", headers={"X-Bank-User": "carol"}, json={"online": "false"}).json()
    assert off["card"]["controls"]["online"] is False
    assert bank.get("/api/accounts/ACC-99", headers={"X-Bank-User": "carol"}).status_code == 404
    assert bank.get("/api/transactions", headers={"X-Bank-User": "carol"}, params={"category": "dining", "limit": "5"}).json()["total"] > 5
    monkeypatch.setenv("BANK_API_TOKEN", "t0ken")
    assert bank.get("/api/me", headers={"X-Bank-User": "carol"}).status_code == 401
    assert bank.get("/api/me", headers={"X-Bank-User": "carol", "Authorization": "Bearer t0ken"}).status_code == 200


def test_banking_manifest_parses(monkeypatch):
    from relay_gateway.services.agent_service import parse_manifest

    monkeypatch.setenv("RELAY_BANK_TOOLS_URL", "http://bank-tools:8095")
    manifest = parse_manifest(REPO / "agents" / "banking.yaml")
    assert manifest.agent_id == "banking" and manifest.tools_url == "http://bank-tools:8095"
    assert "Kestrel" in manifest.system_prompt and "IMPS" in manifest.keyterms
