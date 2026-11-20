"""The national bank example's tools service (National Bank): signed calls, per-customer data,
sandboxes, the generated site API, and the rules behind the advice — loan eligibility and ranking,
deposits and premature closure, beneficiaries' cooling period and limits, schemes, services, re-KYC."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

REPO = Path(__file__).resolve().parents[3]


def _as(user: str) -> dict[str, str]:
    return {"X-Relay-User": json.dumps({"id": user})}


@pytest.fixture
def vnb(tmp_path, monkeypatch):
    monkeypatch.setenv("VNB_DB_PATH", str(tmp_path / "vnb.db"))
    monkeypatch.setenv("VNB_SANDBOX_DIR", str(tmp_path / "sandboxes"))
    monkeypatch.delenv("RELAY_TOOLS_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("VNB_API_TOKEN", raising=False)
    from vnb_api.main import app

    return TestClient(app)


def call(client: TestClient, tool: str, user: str | None = "alice", **args):
    return client.post(f"/tools/{tool}", headers=_as(user) if user else {}, json=args)


def _balance(client: TestClient, user: str = "alice") -> int:
    return call(client, "get_my_context", user=user).json()["savings_balance"]


def test_every_write_needs_approval_and_schemas_match_functions():
    from vnb_api.tools import TOOL_SPECS

    writes = {"add_beneficiary", "delete_beneficiary", "transfer_funds", "apply_for_loan", "prepay_loan", "open_fixed_deposit",
              "open_recurring_deposit", "close_fixed_deposit", "enroll_in_scheme", "open_ssy_account", "deposit_to_ppf", "request_cheque_book",
              "stop_cheque", "block_debit_card", "update_debit_card_usage", "submit_kyc_declaration", "raise_complaint",
              "open_account", "close_account", "transfer_between_own_accounts", "set_transfer_limit", "add_biller", "pay_bill", "set_bill_autopay",
              "create_standing_instruction", "cancel_standing_instruction", "pay_tax", "submit_form_15g_15h", "invest_in_mutual_fund",
              "redeem_mutual_fund", "open_nps_account", "contribute_to_nps", "apply_for_locker", "update_nominee", "register_positive_pay"}
    assert {n for n, s in TOOL_SPECS.items() if s.classification == "side_effecting"} == writes
    for name, spec in TOOL_SPECS.items():
        params = inspect.signature(spec.fn).parameters
        assert set(spec.properties) <= set(params), name
        assert set(spec.required) <= set(spec.properties), name
        required_args = {p for p, v in params.items() if v.default is inspect.Parameter.empty}
        assert required_args <= set(spec.required), name
        assert len(spec.properties) <= 20 or spec.classification == "read_only", name
        assert spec.per_user or spec.classification == "read_only", name


def test_calls_must_be_signed_and_need_a_customer(vnb, monkeypatch):
    assert call(vnb, "get_my_context", user=None).status_code == 401
    assert call(vnb, "get_deposit_rates", user=None).status_code == 200  # published rates need no customer
    monkeypatch.setenv("RELAY_TOOLS_SIGNING_SECRET", "s3cret")
    assert vnb.get("/tools").status_code == 401
    assert call(vnb, "get_my_context").status_code == 401


def test_every_read_tool_answers(vnb):
    from vnb_api.tools import TOOL_SPECS

    txn = call(vnb, "get_account_statement", last_n=1).json()["transactions"][0]["id"]
    samples = {
        "get_account_details": {"account_id": "PPF-01"},
        "get_transaction": {"transaction_id": txn},
        "get_transfer_quote": {"beneficiary_id": "Amma", "amount": 1000},
        "recommend_loans": {"purpose": "medical", "amount": 200000},
        "calculate_emi": {"amount": 500000, "tenure_months": 60, "product": "car_loan"},
        "get_prepayment_quote": {"loan_id": "LN-01", "amount": 50000},
        "quote_deposit": {"kind": "fd", "amount": 100000, "tenure_months": 12},
        "get_fd_closure_quote": {"deposit_id": "FD-01"},
        "compare_savings_options": {"years": 10, "monthly": 5000},
        "get_cheque_status": {"cheque_number": 512310},
    }
    for name, spec in TOOL_SPECS.items():
        if spec.classification != "read_only":
            continue
        res = call(vnb, name, **samples.get(name, {}))
        assert res.status_code == 200 and "error" not in res.json(), (name, res.text)


def test_statement_narrations_are_cryptic_but_explained(vnb):
    lines = call(vnb, "get_account_statement", query="DECLINED").json()["transactions"]
    assert len(lines) == 1 and lines[0]["amount"] == 590 and "CHGS" in lines[0]["narration"]
    detail = call(vnb, "get_transaction", transaction_id=lines[0]["id"]).json()
    assert any("declined" in p["meaning"].lower() for p in detail["explanation"]["parts"])
    neft = call(vnb, "get_account_statement", query="RAJESH GUPTA").json()["transactions"][0]
    parts = call(vnb, "get_transaction", transaction_id=neft["id"]).json()["explanation"]["parts"]
    assert any(p["code"] == "GGBK0000214" and "Ganga Gramin" in p["meaning"] for p in parts)


def test_loan_advice_prefers_the_cheapest_affordable_option(vnb):
    medical = call(vnb, "recommend_loans", purpose="medical", amount=200000).json()
    assert medical["best"]["product"] == "loan_against_fd"  # FD-01 can be pledged: 7% + 1%
    gold = next(o for o in medical["options"] if o["product"] == "gold_loan")
    assert not gold["eligible"] and medical["ask_for"] == ["gold_grams"]
    personal = next(o for o in medical["options"] if o["product"] == "personal_loan")
    assert personal["rate"] == 11.45  # 750–799 band minus the government-employee discount

    car = call(vnb, "recommend_loans", purpose="vehicle", amount=800000, vehicle_price=950000).json()
    assert car["best"]["product"] == "car_loan"
    lafd = next(o for o in car["options"] if o["product"] == "loan_against_fd")
    assert not lafd["eligible"]  # more than 90% of the FD, and its EMI would be unaffordable

    home = call(vnb, "recommend_loans", purpose="home_purchase", amount=4000000, property_value=4500000).json()
    loan = home["options"][0]
    assert not loan["eligible"] and loan["max_amount"] == 3600000  # 80% LTV above ₹30 lakh
    assert loan["max_tenure_months"] == (70 - 47) * 12  # must end by 70


def test_loan_against_fd_is_instant_and_locks_the_deposit(vnb):
    before = _balance(vnb)
    res = call(vnb, "apply_for_loan", product="loan_against_fd", amount=150000, tenure_months=6, deposit_id="FD-01").json()
    assert res["loan"]["security"] == "FD-01" and _balance(vnb) == before + 150000
    assert "lien" in call(vnb, "close_fixed_deposit", deposit_id="FD-01").json()["error"]
    personal = call(vnb, "apply_for_loan", product="personal_loan", amount=300000, tenure_months=48).json()
    assert "repayment capacity" in personal["error"]  # the new EMI counts against the salary


def test_deposits_and_premature_closure(vnb):
    assert "locked in" in call(vnb, "get_fd_closure_quote", deposit_id="FD-02").json()["error"]  # tax saver
    quote = call(vnb, "get_fd_closure_quote", deposit_id="FD-01").json()
    assert quote["penalty"] == 0.5 and quote["payout"] < quote["if_held_to_maturity"]
    before = _balance(vnb)
    call(vnb, "close_fixed_deposit", deposit_id="FD-01")
    assert _balance(vnb) == before + quote["payout"]
    special = call(vnb, "quote_deposit", kind="special", amount=100000).json()
    assert special["rate"] == 7.25 and special["tenure_days"] == 444
    opened = call(vnb, "open_fixed_deposit", amount=50000, scheme="special").json()
    assert opened["deposit"]["rate"] == 7.25
    assert call(vnb, "quote_deposit", kind="tax_saver", amount=200000).json()["fields"]["amount"]


def test_beneficiary_cooling_period_limits_and_modes(vnb):
    cooling = call(vnb, "get_transfer_quote", beneficiary_id="Mohit", amount=5000).json()
    assert not cooling["can_send"] and "cooling" in cooling["error"]
    assert call(vnb, "transfer_funds", beneficiary_id="Mohit", amount=5000).json()["error"]
    rtgs = call(vnb, "get_transfer_quote", beneficiary_id="Ankit", amount=50000, mode="rtgs").json()
    assert not rtgs["can_send"] and "2 lakh" in rtgs["error"]
    over = call(vnb, "get_transfer_quote", beneficiary_id="House owner", amount=60000).json()
    assert "limit" in over["error"]
    before = _balance(vnb)
    sent = call(vnb, "transfer_funds", beneficiary_id="House owner", amount=14000, remarks="Rent").json()
    assert sent["transfer"]["mode"] == "IMPS" and _balance(vnb) == before - 14000
    added = call(vnb, "add_beneficiary", name="Priya Shah", account_number="123456789012", ifsc="DCBL0000731").json()
    assert added["beneficiary"]["status"] == "cooling"
    assert call(vnb, "add_beneficiary", name="X", account_number="12", ifsc="DCBL0000731").json()["fields"]["account_number"]


def test_schemes_services_and_kyc(vnb):
    schemes = {s["scheme"]: s for s in call(vnb, "list_government_schemes").json()["schemes"]}
    assert schemes["pmjjby"]["eligible"] and not schemes["apy"]["eligible"] and schemes["ssy"]["eligible"]
    assert call(vnb, "enroll_in_scheme", scheme="pmjjby", nominee_name="Sunita Verma", nominee_relation="wife").json()["enrolment"]["premium"] == 436
    assert "already" in call(vnb, "enroll_in_scheme", scheme="pmjjby", nominee_name="S", nominee_relation="wife").json()["error"]
    assert call(vnb, "open_ssy_account", girl_name="Ananya Verma", girl_dob="2017-06-20", initial_deposit=1000).json()["account"]["id"] == "SSY-01"
    assert "under 10" in call(vnb, "open_ssy_account", girl_name="Old", girl_dob="2010-01-01", initial_deposit=1000).json()["error"]
    assert "room left" in call(vnb, "deposit_to_ppf", amount=200000).json()["error"]

    book = call(vnb, "request_cheque_book", leaves=25).json()
    assert book["request"]["charge"] == 71  # 15 chargeable leaves × ₹4 + GST
    assert call(vnb, "stop_cheque", cheque_from=600000, reason="lost").json()["fields"]["cheque_from"]
    blocked = call(vnb, "block_debit_card", reason="lost").json()
    assert "permanently" in blocked["message"] and call(vnb, "get_debit_card").json()["replacement"]["status"] == "dispatched"

    assert call(vnb, "get_my_context").json()["kyc"]["overdue"] is True
    call(vnb, "submit_kyc_declaration", address_changed=False)
    assert call(vnb, "get_my_context").json()["kyc"]["overdue"] is False
    complaint = call(vnb, "raise_complaint", category="wrong_charges", description="Charged at an ATM I did not use").json()
    assert complaint["complaint"]["docket"].startswith("VNB")


def test_customers_and_sandboxes_are_apart_and_site_api(vnb, monkeypatch):
    a, b = "sandbox_" + "a" * 20, "sandbox_" + "b" * 20
    call(vnb, "add_beneficiary", user=a, name="Sandbox Friend", account_number="998877665544", ifsc="DCBL0000731")
    assert len(call(vnb, "list_beneficiaries", user=a).json()["beneficiaries"]) == 7
    assert len(call(vnb, "list_beneficiaries", user=b).json()["beneficiaries"]) == 6
    assert len(vnb.get("/api/list_beneficiaries", headers={"X-Vnb-User": a}).json()["beneficiaries"]) == 7
    assert vnb.post("/sandbox/reset", headers={"X-Sandbox-Id": a}).json() == {"reset": True}
    assert len(call(vnb, "list_beneficiaries", user=a).json()["beneficiaries"]) == 6

    # The site API runs reads with GET and writes with POST, converting form strings like the tools' schemas.
    assert vnb.post("/api/get_my_context", headers={"X-Vnb-User": "carol"}).status_code == 404
    assert vnb.get("/api/transfer_funds", headers={"X-Vnb-User": "carol"}).status_code == 404
    missing = vnb.post("/api/transfer_funds", headers={"X-Vnb-User": "carol"}, json={"beneficiary_id": "BEN-01"})
    assert missing.status_code == 400 and "amount" in missing.json()["fields"]
    ok = vnb.post("/api/transfer_funds", headers={"X-Vnb-User": "carol"}, json={"beneficiary_id": "BEN-01", "amount": "1,200"})
    assert ok.status_code == 200 and ok.json()["transfer"]["amount"] == 1200
    card = vnb.post("/api/update_debit_card_usage", headers={"X-Vnb-User": "carol"}, json={"international": "true"}).json()
    assert card["card"]["international"] is True
    monkeypatch.setenv("VNB_API_TOKEN", "t0ken")
    assert vnb.get("/api/get_my_context", headers={"X-Vnb-User": "carol"}).status_code == 401
    assert vnb.get("/api/get_my_context", headers={"X-Vnb-User": "carol", "Authorization": "Bearer t0ken"}).status_code == 200


def test_national_bank_manifest_parses(monkeypatch):
    from relay_gateway.services.agent_service import parse_manifest

    monkeypatch.setenv("RELAY_VNB_TOOLS_URL", "http://vnb-tools:8096")
    manifest = parse_manifest(REPO / "agents" / "national-bank.yaml")
    assert manifest.agent_id == "national-bank" and manifest.tools_url == "http://vnb-tools:8096"
    assert "National Bank" in manifest.system_prompt and "PMJJBY" in manifest.keyterms


def test_opening_and_closing_accounts(vnb):
    products = {p["product"]: p for p in call(vnb, "list_account_products").json()["products"]}
    assert not products["bsbd"]["eligible"] and not products["senior"]["eligible"] and products["minor"]["eligible"]
    assert "already" in call(vnb, "open_account", product="bsbd").json()["error"]
    before = _balance(vnb)
    minor = call(vnb, "open_account", product="minor", initial_deposit=2000, nominee_name="Sunita Verma", nominee_relation="mother").json()
    assert minor["account"]["holder"] == "Ananya Verma" and minor["account"]["id"] == "SB-02" and _balance(vnb) == before - 2000
    assert call(vnb, "get_account_statement", account_id="SB-02").json()["total_credits"] == 2000
    salary = call(vnb, "open_account", product="salary").json()
    assert salary["account"]["id"] == "SB-01" and "accident" in salary["message"]
    assert call(vnb, "open_account", product="current", business_name="Tuitions", initial_deposit=5000).json()["fields"]["initial_deposit"]
    moved = call(vnb, "transfer_between_own_accounts", from_account="SB-01", to_account="SB-02", amount=500).json()
    assert moved["transfer"]["to"] == "SB-02"
    assert "main account" in call(vnb, "close_account", account_id="SB-01").json()["error"]
    closed = call(vnb, "close_account", account_id="SB-02").json()
    assert "2,500" in closed["message"]


def test_bills_standing_instructions_and_limit(vnb):
    billers = {b["id"]: b for b in call(vnb, "list_billers").json()["billers"]}
    assert billers["BLR-01"]["bill"]["amount"] == 2890
    paid = call(vnb, "pay_bill", biller_id="electricity").json()
    assert paid["payment"]["amount"] == 2890 and paid["payment"]["reference"].startswith("BBPS")
    assert "plans" in call(vnb, "pay_bill", biller_id="My mobile").json()["error"]
    assert "not a plan" in call(vnb, "pay_bill", biller_id="My mobile", amount=250).json()["fields"]["amount"]
    assert "680" in call(vnb, "pay_bill", biller_id="fastag", amount=500).json()["message"]
    assert "prepaid" in call(vnb, "set_bill_autopay", biller_id="fastag", enabled=True).json()["fields"]["biller_id"]
    assert call(vnb, "set_bill_autopay", biller_id="Wi-Fi", enabled=True, max_amount=1000).json()["biller"]["autopay"]["max_amount"] == 1000
    assert "not a registered" in call(vnb, "add_biller", category="dth", provider="Awadh Gas Ltd", consumer_number="12345").json()["fields"]["provider"]

    si = call(vnb, "create_standing_instruction", to="House owner", amount=14000, day_of_month=5, installments=11).json()["standing_instruction"]
    assert si["to"] == "BEN-03" and si["end"]
    assert "limit" in call(vnb, "create_standing_instruction", to="House owner", amount=60000, day_of_month=5).json()["error"]
    assert "deposit" in call(vnb, "cancel_standing_instruction", standing_instruction_id="SI-02").json()["fields"]["standing_instruction_id"]
    assert call(vnb, "cancel_standing_instruction", standing_instruction_id=si["id"]).json()["standing_instruction"]["status"] == "cancelled"

    call(vnb, "set_transfer_limit", daily_limit_amount=20000)
    quote = call(vnb, "get_transfer_quote", beneficiary_id="Ankit", amount=25000).json()
    assert not quote["can_send"] and "daily transfer limit" in quote["error"]


def test_tax_investments_lockers_nominees_and_cheques(vnb):
    guide = call(vnb, "get_tax_payment_guide").json()
    assert guide["advance_tax_needed"] is False and len(guide["due_dates"]) == 4
    assert call(vnb, "pay_tax", tax_type="self_assessment", amount=6200).json()["payment"]["cin"]
    assert "taxable" in call(vnb, "submit_form_15g_15h").json()["error"]

    call(vnb, "invest_in_mutual_fund", scheme="elss", amount=5000, mode="sip", sip_day=5)
    assert "lock-in" in call(vnb, "redeem_mutual_fund", scheme="elss").json()["error"]
    call(vnb, "invest_in_mutual_fund", scheme="liquid", amount=20000)
    assert call(vnb, "redeem_mutual_fund", scheme="liquid", amount=5000).json()["holding"]["redeemable_value"] < 20000
    assert "SIP" in call(vnb, "redeem_mutual_fund", scheme="elss", stop_sip=True).json()["message"]

    assert call(vnb, "open_nps_account", investment_choice="auto_moderate", initial_contribution=5000, nominee_name="Sunita Verma",
                nominee_relation="wife").json()["nps"]["pran"]
    assert "already" in call(vnb, "open_nps_account", investment_choice="auto_moderate", initial_contribution=5000, nominee_name="S",
                             nominee_relation="wife").json()["error"]
    assert call(vnb, "apply_for_locker", size="small").json()["locker"]["status"] == "waitlisted"

    assert "minor" in call(vnb, "update_nominee", account_id="FD-01", nominee_name="Ananya Verma", nominee_relation="daughter",
                              nominee_dob="2017-06-20").json()["fields"]["guardian_name"]
    assert "PPF-01" in call(vnb, "list_nominees").json()["without_nominee"]

    assert call(vnb, "get_cheque_status", cheque_number=512310).json()["status"].startswith("Paid")
    assert "below" in call(vnb, "register_positive_pay", cheque_number=512316, cheque_date="2026-11-25", amount=10000, payee_name="X").json()["fields"]["amount"]
    call(vnb, "stop_cheque", cheque_from=512320, reason="lost")
    assert "stopped" in call(vnb, "register_positive_pay", cheque_number=512320, cheque_date="2026-11-25", amount=75000, payee_name="X").json()["error"]
