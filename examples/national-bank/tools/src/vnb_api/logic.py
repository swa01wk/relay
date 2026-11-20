"""Vasundhara National Bank's business logic — the one implementation behind both the net banking
site's API and the Relay tools.

Every rule lives here once: the passbook-style statement and what its narrations mean, beneficiaries
(4-hour cooling, per-beneficiary limits) and transfers (within VNB, IMPS, NEFT, RTGS), the loan
catalogue with eligibility (CIBIL band, FOIR, age at the end, security) and a ranked recommendation,
EMIs and prepayment, fixed and recurring deposits (slab rates, quarterly compounding, premature
closure penalty, TDS), PPF / SSY / SCSS, the government insurance and pension schemes, cheque books,
stop-payment, debit card blocking and limits, re-KYC, interest certificates and complaints.

Money is whole rupees; dates are IST. Everything belongs to the signed-in customer (``current_user()``);
only the published rates and rules work without one.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from typing import Any

from vnb_api import db
from vnb_api.seeds import (
    BANK,
    BENEFICIARIES,
    CAR_EMI,
    DEBIT_CARD,
    DEFAULT_CUSTOMER,
    FD_SLABS,
    GOLD_RATE_PER_GRAM_22K,
    GOVT_SCHEMES,
    GST,
    LOAN_PRODUCTS,
    LOAN_PURPOSES,
    SB_RATE,
    SENIOR_EXTRA,
    SMALL_SAVINGS,
    SPECIAL_FD,
    TAX_SAVER,
    add_months,
    billers_for,
    build_history,
    car_loan_for,
    deposits_for,
    emi,
    ppf_for,
    standing_for,
)

IST = timezone(timedelta(hours=5, minutes=30))

# Transfers
DAILY_THIRD_PARTY_LIMIT = 1000000  # all transfers to beneficiaries in a day
BENEFICIARY_MAX_LIMIT = 1000000
COOLING_HOURS = 4
MODES = {
    "within_vnb": {"label": "Within VNB", "arrives": "instantly", "min": 1, "max": None},
    "imps": {"label": "IMPS", "arrives": "instantly, 24x7", "min": 1, "max": 500000},
    "neft": {"label": "NEFT", "arrives": "within 30 minutes (half-hourly batches, 24x7)", "min": 1, "max": None},
    "rtgs": {"label": "RTGS", "arrives": "within 30 minutes, 24x7", "min": 200000, "max": None},
}
# Deposits
FD_MIN, FD_MAX = 1000, 20000000
RD_MIN_MONTHLY, RD_MONTHS = 100, (12, 120)
PREMATURE_PENALTY = (0.50, 1.00)  # percentage points: below ₹5 lakh, ₹5 lakh and above
TDS_THRESHOLD = {"general": 40000, "senior": 50000}
TDS_RATE = 10
# Services
CHEQUE_FREE_LEAVES_PER_FY = 10
CHEQUE_CHARGE_PER_LEAF = 4  # + GST, beyond the free leaves
STOP_CHEQUE_FEE = 100  # + GST per instruction
CARD_REISSUE_FEE = 300  # + GST (not for a damaged card)
CARD_LIMITS_MAX = {"atm_daily_limit": 100000, "pos_daily_limit": 200000}
KYC_PERIOD_YEARS = {"high": 2, "medium": 8, "low": 10}
COMPLAINT_CATEGORIES = {
    "atm_cash_not_dispensed": ("ATM: account debited but cash not dispensed", 5),
    "upi_failed_debited": ("UPI / IMPS: failed but money debited", 1),
    "wrong_charges": ("Charges I don't understand or agree with", 15),
    "unauthorized_transaction": ("A transaction I did not do", 10),
    "card_issue": ("Debit card problem", 7),
    "loan_issue": ("Loan or EMI problem", 15),
    "kyc_issue": ("KYC / account restriction", 7),
    "other": ("Something else", 30),
}
BLOCK_REASONS = {"lost": "Lost", "stolen": "Stolen", "damaged": "Damaged", "suspected_misuse": "Suspected misuse"}
STOP_REASONS = {"lost": "Cheque lost", "stolen": "Cheque stolen", "wrong_details": "Issued with wrong details", "dispute": "Dispute with payee"}
CATEGORIES = {
    "salary": "Salary", "rent": "Rent", "loan_emi": "Loan EMI", "savings_investment": "Savings & investments", "utilities": "Bills & recharges",
    "education": "Education", "family": "Family", "groceries": "Groceries", "shopping": "Shopping", "fuel": "Fuel", "health": "Health",
    "cash": "Cash withdrawal", "charges": "Bank charges", "interest": "Interest", "insurance": "Insurance", "transfer": "Transfers",
    "refund": "Refunds", "other": "Other",
}
CHANNELS = {"salary": "Salary credit", "neft": "NEFT", "imps": "IMPS", "rtgs": "RTGS", "intra_bank": "Within VNB", "upi": "UPI",
            "atm": "ATM", "pos": "Debit card (shop)", "bill_pay": "Bill payment (BBPS)", "auto_debit": "Auto debit / standing instruction",
            "interest": "Interest", "charges": "Charges", "fd": "Deposit", "loan": "Loan"}
DISPUTABLE = ("upi", "pos", "atm", "bill_pay", "auto_debit", "charges", "imps", "neft")
BANK_BY_IFSC = {"VNBA": BANK, "GGBK": "Ganga Gramin Bank", "DCBL": "Deccan Commercial Bank", "PUCB": "Purvanchal Urban Co-op Bank",
                "YBLX": "a UPI app (PhonePe-style handle)"}
NARRATION_CODES = [
    ("BY TRANSFER", "Money came in by transfer"),
    ("TO TRANSFER", "Money went out by transfer"),
    ("SAL/", "Salary credit from your employer"),
    ("NEFT", "NEFT — bank-to-bank transfer settled in half-hourly batches"),
    ("IMPS", "IMPS — instant bank-to-bank transfer"),
    ("P2A", "person-to-account: sent using account number and IFSC"),
    ("UPI/DR", "UPI payment you made (the 12-digit number is the UPI reference / UTR)"),
    ("UPI/CR", "UPI money you received (the 12-digit number is the UPI reference / UTR)"),
    ("INB", "Net banking transfer to another VNB account"),
    ("BBPS", "Bill paid through Bharat Bill Payment System"),
    ("ACH DR", "Auto-debit mandate (NACH / ECS) you gave a company — e.g. an insurance premium"),
    ("LOAN RECOVERY", "Your loan EMI, recovered automatically"),
    ("RD INSTL", "Your recurring deposit instalment, debited automatically"),
    ("PPF A/C", "Deposit into your PPF account"),
    ("ATM WDL", "Cash withdrawn at an ATM"),
    ("POS", "Debit card used at a shop's card machine (point of sale)"),
    ("CREDIT INTEREST", f"Savings account interest ({SB_RATE}% p.a.), credited quarterly"),
    ("SMS ALERT CHGS", "Quarterly fee for SMS alerts (incl. 18% GST)"),
    ("AMC CHGS", "Debit card annual maintenance charge (₹200 + 18% GST)"),
    ("DECLINED TXN CHGS", "Fee for a transaction declined for insufficient balance at another bank's ATM (₹500 + GST)"),
]
_IFSC = re.compile(r"[A-Z]{4}0[A-Z0-9]{6}")
_ACCOUNT_NO = re.compile(r"\d{9,18}")
_user: ContextVar[str | None] = ContextVar("vnb_user", default=None)


class NoUser(Exception):
    """A per-customer call without a customer (the tools service answers 401)."""


@contextmanager
def as_user(user_id: str | None) -> Iterator[None]:
    token = _user.set(user_id or None)
    try:
        yield
    finally:
        _user.reset(token)


def current_user() -> str:
    user_id = _user.get()
    if not user_id:
        raise NoUser()
    _ensure_customer(user_id)
    return user_id


# ---------------------------------------------------------------- helpers


def _now() -> datetime:
    return datetime.now(IST)


def _today() -> date:
    return _now().date()


def _error(message: str, **fields: str) -> dict[str, Any]:
    return {"error": message, **({"fields": fields} if fields else {})}


def rupees(value: float) -> str:
    """₹1,23,456 — Indian digit grouping."""
    n = int(round(value))
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = f"{head},{tail}"
    return f"{sign}₹{s}"


def _amount(value: Any, field: str = "amount") -> int | dict[str, Any]:
    try:
        number = float(str(value).replace(",", "").replace("₹", "").strip())
    except (TypeError, ValueError):
        return _error(f"{field} must be a number of rupees", **{field: "not a number"})
    if not math.isfinite(number) or number <= 0:
        return _error(f"{field} must be more than ₹0", **{field: "must be positive"})
    return int(round(number))


def _int(value: Any, field: str) -> int | dict[str, Any]:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return _error(f"{field} must be a whole number", **{field: "not a number"})


def _parse_date(value: Any, field: str) -> date | dict[str, Any]:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return _error(f"{field} must be a date like 2026-10-01", **{field: "not a date"})


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _age(dob: str, on: date | None = None) -> int:
    born = date.fromisoformat(dob)
    on = on or _today()
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def _fy(on: date | None = None) -> tuple[date, date, str]:
    on = on or _today()
    start_year = on.year if on.month >= 4 else on.year - 1
    return date(start_year, 4, 1), date(start_year + 1, 3, 31), f"{start_year}-{str(start_year + 1)[2:]}"


def _mask(number: str) -> str:
    return f"XXXXXXX{number[-4:]}"


def _ref(prefix: str = "") -> str:
    return prefix + str(random.randint(10**10, 10**11 - 1))


def _next_id(kind: str, user: str, prefix: str, width: int = 2) -> str:
    numbers = [int(r["id"].split("-")[-1]) for r in db.rows(kind, user) if r["id"].startswith(prefix)]
    return f"{prefix}{(max(numbers) + 1 if numbers else 1):0{width}d}"


def _match(row_id: str, text: str, *names: str) -> bool:
    t = text.strip().lower()
    return bool(t) and (row_id.lower() == t or any(t == (n or "").lower() or (len(t) >= 3 and t in (n or "").lower()) for n in names))


# ---------------------------------------------------------------- seeding


def _ensure_customer(user: str) -> None:
    cust = db.get("customers", user, "me")
    if cust is not None:
        if not cust.get("extras_seeded"):
            _seed_extras(user)
        return
    with db.transaction():
        if db.get("customers", user, "me") is not None:
            return
        today = _today()
        opening, lines = build_history(today)
        balance = opening
        txns = []
        for index, line in enumerate(lines):
            balance += line["amount"] if line["direction"] == "credit" else -line["amount"]
            txns.append({**line, "user_id": user, "id": f"TXN-{100001 + index}", "account_id": "SB-01", "balance_after": balance})
        db.put_many("transactions", txns)
        db.put("customers", {**DEFAULT_CUSTOMER, "user_id": user, "id": "me", "kyc_declarations": []})
        db.put("accounts", {"user_id": user, "id": "SB-01", "kind": "savings", "product": "regular",
                            "product_name": "Savings Account (Regular)", "name": "Savings Bank — Regular", "number": "30214457824821",
                            "balance": balance, "lien": 0, "rate": SB_RATE, "opened": "2004-07-19", "mode": "Single",
                            "nominee": "Sunita Verma (wife)", "micr": "226017004", "status": "active",
                            "cheque_series": {"from": 512301, "to": 512325, "used_to": 512314, "issued": "2025-06-02"},
                            "cheque_leaves_this_fy": 0})
        db.put("accounts", {**ppf_for(today), "user_id": user})
        for dep in deposits_for(today):
            db.put("deposits", {**dep, "user_id": user})
        loan = car_loan_for(today)
        loan["outstanding"] = _balance_after(loan["sanctioned"], loan["rate"], loan["emi"], loan["emis_paid"])
        loan["next_emi_date"] = _next_day_of_month(today, loan["emi_day"]).isoformat()
        db.put("loans", {**loan, "user_id": user})
        db.put("cards", {**DEBIT_CARD, "user_id": user, "linked_account": "SB-01"})
        for ben in BENEFICIARIES:
            added = _now() - timedelta(days=ben["added_days_ago"])
            row = {k: v for k, v in ben.items() if k != "added_days_ago"}
            db.put("beneficiaries", {**row, "user_id": user, "added_at": added.isoformat()})
        _seed_extras(user)


def _seed_extras(user: str) -> None:
    """Billers and standing instructions (added after the first release: also backfilled for existing customers)."""
    with db.transaction():
        cust = db.get("customers", user, "me")
        if cust is None or cust.get("extras_seeded"):
            return
        today = _today()
        for biller in billers_for(today):
            db.put("billers", {**biller, "user_id": user})
        for si in standing_for(today):
            db.put("standing", {**si, "user_id": user})
        cust["extras_seeded"] = True
        db.put("customers", cust)


def _next_day_of_month(today: date, day: int) -> date:
    candidate = today.replace(day=min(day, 28))
    return candidate if candidate > today else add_months(candidate, 1)


def _balance_after(principal: float, rate: float, instalment: int, paid: int) -> int:
    r = rate / 1200
    balance = float(principal)
    for _ in range(paid):
        balance = balance * (1 + r) - instalment
    return max(0, int(round(balance)))


def _months_to_repay(balance: float, rate: float, instalment: int) -> int:
    r = rate / 1200
    if balance <= 0:
        return 0
    if instalment <= balance * r:
        return 10**4
    return math.ceil(-math.log(1 - balance * r / instalment) / math.log(1 + r))


def _pv(instalment: float, rate: float, months: int) -> int:
    r = rate / 1200
    if instalment <= 0 or months <= 0:
        return 0
    return int(instalment * (1 - (1 + r) ** -months) / r)


def _customer(user: str) -> dict[str, Any]:
    row = db.get("customers", user, "me")
    assert row is not None
    return row


TRANSACTIONAL = ("savings", "current")


def _savings(user: str, account_id: str = "SB-01") -> dict[str, Any]:
    """A savings or current account (SB-01, the customer's main account, by default)."""
    row = db.get("accounts", user, account_id)
    assert row is not None and row["kind"] in TRANSACTIONAL, account_id
    return row


def transactional_account(user: str, account_id: str | None) -> dict[str, Any] | None:
    """The customer's open savings / current account with this id (or None)."""
    row = db.get("accounts", user, (account_id or "SB-01").strip().upper())
    return row if row and row["kind"] in TRANSACTIONAL and row["status"] == "active" else None


def daily_limit(user: str) -> int:
    return int(_customer(user).get("daily_transfer_limit", DAILY_THIRD_PARTY_LIMIT))


def _post(user: str, *, amount: int, direction: str, narration: str, category: str, counterparty: str, channel: str,
          account_id: str = "SB-01") -> dict[str, Any]:
    """Credit or debit a savings / current account (SB-01 by default) and write the statement line."""
    account = _savings(user, account_id)
    account["balance"] += amount if direction == "credit" else -amount
    db.put("accounts", account)
    txn = {"user_id": user, "id": _next_txn_id(user), "account_id": account_id,
           "date": _today().isoformat(), "amount": amount, "direction": direction, "narration": narration, "category": category,
           "counterparty": counterparty, "channel": channel, "ref": _ref(), "balance_after": account["balance"]}
    db.put("transactions", txn)
    return txn


def _next_txn_id(user: str) -> str:
    numbers = [int(r["id"].split("-")[1]) for r in db.rows("transactions", user)]
    return f"TXN-{(max(numbers) + 1) if numbers else 100001}"


def _available(user: str, account_id: str = "SB-01") -> int:
    account = _savings(user, account_id)
    return account["balance"] - account.get("lien", 0)


def _debit_or_error(user: str, amount: int, account_id: str = "SB-01") -> dict[str, Any] | None:
    if amount > _available(user, account_id):
        return _error(f"Not enough balance: {rupees(_available(user, account_id))} available in account XXXXXXX{_savings(user, account_id)['number'][-4:]}",
                      amount="more than the available balance")
    return None


def _with_gst(amount: float) -> int:
    return int(round(amount * (1 + GST)))


# ---------------------------------------------------------------- customer and accounts


def _kyc_status(cust: dict[str, Any]) -> dict[str, Any]:
    last = date.fromisoformat(cust["kyc_last_updated"])
    due = last.replace(year=last.year + KYC_PERIOD_YEARS[cust["risk_category"]])
    today = _today()
    overdue = today > due
    restrict = due + timedelta(days=180)
    return {
        "last_updated": last.isoformat(), "due_date": due.isoformat(), "overdue": overdue,
        "status": "Re-KYC overdue" if overdue else ("Due within 90 days" if (due - today).days <= 90 else "Up to date"),
        "restriction_date": restrict.isoformat() if overdue else None,
        "how": "If nothing changed: submit the self-declaration online (submit_kyc_declaration). If the address changed: declare the new "
               "address online, then show proof of the new address at the branch within 90 days.",
    }


def _deposit_value(dep: dict[str, Any], on: date | None = None) -> int:
    on = on or _today()
    if dep["kind"] == "rd":
        return _rd_value(dep["monthly"], dep["rate"], dep["installments_paid"], date.fromisoformat(dep["opened"]), on)
    opened = date.fromisoformat(dep["opened"])
    days = max(0, (min(on, date.fromisoformat(dep["maturity"])) - opened).days)
    return _fd_amount(dep["principal"], dep["rate"], days, dep.get("payout", "cumulative"))


def _fd_amount(principal: int, rate: float, days: int, payout: str = "cumulative") -> int:
    """Value with interest: simple below 180 days, otherwise compounded quarterly (cumulative)."""
    if payout != "cumulative" or days < 180:
        return int(round(principal * (1 + rate / 100 * days / 365)))
    return int(round(principal * (1 + rate / 400) ** (4 * days / 365)))


def _rd_value(monthly: int, rate: float, paid: int, opened: date, on: date) -> int:
    total = 0.0
    for i in range(paid):
        start = add_months(opened, i)
        if start > on:
            break
        total += monthly * (1 + rate / 400) ** (4 * (on - start).days / 365)
    return int(round(total))


def _rd_maturity(monthly: int, rate: float, months: int) -> int:
    return int(round(sum(monthly * (1 + rate / 400) ** (4 * (months - i) / 12) for i in range(months))))


def _family_with_ages(cust: dict[str, Any]) -> list[dict[str, Any]]:
    return [{**m, "age": _age(m["dob"])} for m in cust.get("family", [])]


def _existing_emi(user: str) -> int:
    return sum(l.get("emi", 0) for l in db.rows("loans", user) if l["status"] == "active")


def get_my_context() -> dict[str, Any]:
    user = current_user()
    cust = _customer(user)
    sb = _savings(user)
    age = _age(cust["dob"])
    deps = [d for d in db.rows("deposits", user) if d["status"] == "active"]
    loans = [l for l in db.rows("loans", user) if l["status"] == "active"]
    alerts = []
    kyc = _kyc_status(cust)
    if kyc["overdue"]:
        alerts.append(f"Re-KYC was due on {kyc['due_date']} — update it or debits may be stopped from {kyc['restriction_date']}.")
    for d in deps:
        left = (date.fromisoformat(d["maturity"]) - _today()).days
        if 0 <= left <= 45:
            alerts.append(f"{d['id']} matures in {left} days ({d['maturity']}).")
    for b in db.rows("beneficiaries", user):
        status = _ben_status(b)
        if status["status"] == "cooling":
            alerts.append(f"Beneficiary {b['name']} can be paid from {status['active_from_display']} (4-hour cooling period).")
    card = db.get("cards", user, "CARD-01")
    if card and card["status"] != "active":
        alerts.append(f"Debit card ••{card['number_masked'][-4:]} is {card['status']}.")
    for b in db.rows("billers", user):
        bill = b.get("bill")
        if bill and 0 <= (date.fromisoformat(bill["due"]) - _today()).days <= 7 and not b.get("autopay"):
            alerts.append(f"{b['provider']} bill of {rupees(bill['amount'])} is due on {bill['due']}.")
        if b["category"] == "fastag" and b.get("balance", 1000) < 300:
            alerts.append(f"FASTag ({b['consumer_number']}) balance is low: {rupees(b['balance'])}.")
    daughter = next((m for m in _family_with_ages(cust) if m["relation"] == "daughter"), None)
    return {
        "bank": BANK,
        "today": _today().isoformat(),
        "customer": {k: cust[k] for k in ("name", "cif", "username", "dob", "mobile", "email", "address", "branch", "branch_code", "ifsc",
                                           "occupation", "net_monthly_income", "cibil_score", "income_tax_slab_percent", "tax_regime")},
        "age": age,
        "senior_citizen": age >= 60,
        "family": _family_with_ages(cust),
        "kyc": kyc,
        "savings_balance": sb["balance"],
        "deposits_total": sum(_deposit_value(d) for d in deps),
        "ppf_balance": (db.get("accounts", user, "PPF-01") or {}).get("balance", 0),
        "loans_outstanding": sum(l["outstanding"] for l in loans),
        "monthly_emis": _existing_emi(user),
        "alerts": alerts,
        "hints": ([f"Daughter {daughter['name']} is {daughter['age']}: SSY can be opened only before she turns 10."]
                  if daughter and daughter["age"] < 10 and not db.rows("enrolments", user) else []),
    }


def get_account_summary() -> dict[str, Any]:
    """All the customer's accounts as the Account Summary page lists them."""
    user = current_user()
    rows: list[dict[str, Any]] = []
    for acc in db.rows("accounts", user):
        if acc["kind"] in TRANSACTIONAL and acc["status"] == "active":
            rows.append({"id": acc["id"], "type": acc.get("product_name") or "Savings Account", "number": acc["number"], "masked": _mask(acc["number"]),
                         "branch": _customer(user)["branch"] + (f" · for {acc['holder']}" if acc.get("holder") else ""),
                         "balance": acc["balance"], "available": acc["balance"] - acc.get("lien", 0), "status": acc["status"]})
    for acc in db.rows("accounts", user):
        if acc["kind"] == "ppf":
            rows.append({"id": acc["id"], "type": "PPF Account", "number": acc["number"], "masked": _mask(acc["number"]), "balance": acc["balance"],
                         "status": acc["status"], "maturity": acc["maturity"]})
        elif acc["kind"] == "ssy":
            rows.append({"id": acc["id"], "type": f"Sukanya Samriddhi ({acc['girl_name']})", "number": acc["number"], "masked": _mask(acc["number"]),
                         "balance": acc["balance"], "status": acc["status"], "maturity": acc["maturity"]})
    for d in db.rows("deposits", user):
        if d["status"] != "active":
            continue
        rows.append({"id": d["id"], "type": {"fd": "Term Deposit (e-TDR/STDR)", "tax_saver": "Tax Saver Term Deposit", "rd": "Recurring Deposit"}[d["kind"]],
                     "number": d["number"], "masked": _mask(d["number"]), "balance": _deposit_value(d),
                     "principal": d.get("principal") or d.get("monthly", 0) * d.get("installments_paid", 0), "rate": d["rate"], "maturity": d["maturity"],
                     "lien": d.get("lien", 0), "status": d["status"]})
    for l in db.rows("loans", user):
        if l["status"] == "active":
            rows.append({"id": l["id"], "type": l["name"], "number": l["number"], "masked": _mask(l["number"]), "balance": -l["outstanding"],
                         "emi": l["emi"], "next_emi_date": l["next_emi_date"], "rate": l["rate"], "status": l["status"]})
    return {"accounts": rows, "as_of": _now().strftime("%d-%m-%Y %H:%M IST")}


def get_account_details(account_id: str) -> dict[str, Any]:
    user = current_user()
    key = account_id.strip().upper()
    acc = db.get("accounts", user, key)
    if acc is None:
        dep = db.get("deposits", user, key)
        if dep:
            return {"deposit": _deposit_view(dep)}
        loan = db.get("loans", user, key)
        if loan:
            return {"loan": _loan_view(loan)}
        return _error(f"not_found: no account {account_id} — use get_account_summary")
    cust = _customer(user)
    if acc["kind"] in TRANSACTIONAL:
        card = next((c for c in db.rows("cards", user) if c.get("linked_account", "SB-01") == acc["id"] and c["status"] != "blocked"), None)
        return {"account": {**{k: acc.get(k) for k in ("id", "name", "product", "product_name", "number", "balance", "lien", "rate", "opened", "mode",
                                                        "nominee", "micr", "status", "holder", "guardian", "minimum_balance", "features")},
                            "available": acc["balance"] - acc.get("lien", 0), "ifsc": cust["ifsc"], "branch": cust["branch"],
                            "holder": acc.get("holder") or cust["name"],
                            "minimum_balance": acc.get("minimum_balance") or "None (no minimum balance charge)",
                            "interest_credited": "Quarterly (Feb, May, Aug, Nov)" if acc["kind"] == "savings" else "No interest on current accounts",
                            "debit_card": card and {k: card[k] for k in ("number_masked", "network", "status")},
                            "cheque_book": acc.get("cheque_series")}}
    if acc["kind"] == "ppf":
        opened = date.fromisoformat(acc["opened"])
        _, _, fy_label = _fy()
        years = _today().year - opened.year
        return {"account": {**acc, "rate": SMALL_SAVINGS["ppf"]["rate"], "fy": fy_label,
                            "deposit_room_this_fy": SMALL_SAVINGS["ppf"]["max_year"] - acc["this_fy_deposits"],
                            "partial_withdrawal": "Allowed once a year from the 7th financial year: up to 50% of the balance at the end of the 4th year before."
                            if years >= 6 else "Not yet (from the 7th financial year)",
                            "loan_against_ppf": "Only in years 3 to 6 — not available now" if years > 6 else "Available (years 3–6)",
                            "tax": SMALL_SAVINGS["ppf"]["tax"]}}
    return {"account": acc}


def _explain(txn: dict[str, Any]) -> dict[str, Any]:
    narration = txn["narration"]
    parts = [{"code": code, "meaning": meaning} for code, meaning in NARRATION_CODES if code in narration]
    ifsc = _IFSC.search(narration)
    if ifsc:
        parts.append({"code": ifsc.group(0), "meaning": f"IFSC of the other bank's branch — {BANK_BY_IFSC.get(ifsc.group(0)[:4], 'another bank')}"})
    vpa = re.search(r"[a-z0-9.]+@[a-z]+", narration)
    if vpa:
        parts.append({"code": vpa.group(0), "meaning": "UPI ID of the person or shop"})
    return {"plain": f"{CATEGORIES.get(txn['category'], 'Other')} — {txn['counterparty']}", "parts": parts}


def _txn_view(txn: dict[str, Any]) -> dict[str, Any]:
    return {k: txn[k] for k in ("id", "date", "narration", "ref", "amount", "direction", "balance_after", "category", "counterparty", "channel")} | {
        "debit": txn["amount"] if txn["direction"] == "debit" else None,
        "credit": txn["amount"] if txn["direction"] == "credit" else None,
    }


def get_account_statement(
    account_id: str = "SB-01",
    from_date: str | None = None,
    to_date: str | None = None,
    last_n: int | None = None,
    direction: str | None = None,
    category: str | None = None,
    query: str | None = None,
    min_amount: int | None = None,
    max_amount: int | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    user = current_user()
    key = account_id.strip().upper()
    if transactional_account(user, key) is None:
        return _error(f"Statements are for savings and current accounts (like SB-01); {account_id} isn't one — deposits and loans show their own details",
                      account_id="not a savings or current account")
    rows = [t for t in db.rows("transactions", user) if t.get("account_id", "SB-01") == key]
    start = end = None
    if from_date:
        start = _parse_date(from_date, "from_date")
        if isinstance(start, dict):
            return start
    if to_date:
        end = _parse_date(to_date, "to_date")
        if isinstance(end, dict):
            return end
    if start and end and start > end:
        return _error("from_date is after to_date", from_date="after to_date")
    out = []
    for t in rows:
        d = date.fromisoformat(t["date"])
        if start and d < start or end and d > end:
            continue
        if direction and t["direction"] != direction:
            continue
        if category and t["category"] != category:
            continue
        if query and query.lower() not in f"{t['narration']} {t['counterparty']} {t['ref']}".lower():
            continue
        if min_amount is not None and t["amount"] < int(min_amount) or max_amount is not None and t["amount"] > int(max_amount):
            continue
        out.append(t)
    out.sort(key=lambda t: (t["date"], t["id"]))
    if last_n:
        out = out[-int(last_n):]
    total_in = sum(t["amount"] for t in out if t["direction"] == "credit")
    total_out = sum(t["amount"] for t in out if t["direction"] == "debit")
    shown = out[-int(limit):] if limit else out
    return {
        "account": key, "from_date": start.isoformat() if start else (out[0]["date"] if out else None),
        "to_date": end.isoformat() if end else _today().isoformat(), "count": len(out), "total_credits": total_in, "total_debits": total_out,
        "transactions": [_txn_view(t) | {"explained": _explain(t)["plain"]} for t in reversed(shown)],
        "note": "Newest first. `explained` is what the cryptic narration means.",
    }


def get_transaction(transaction_id: str) -> dict[str, Any]:
    user = current_user()
    key = transaction_id.strip().upper()
    txn = db.get("transactions", user, key) or next((t for t in db.rows("transactions", user) if t["ref"] == transaction_id.strip()), None)
    if txn is None:
        return _error(f"not_found: no transaction {transaction_id}")
    age_days = (_today() - date.fromisoformat(txn["date"])).days
    can_complain = txn["direction"] == "debit" and txn["channel"] in DISPUTABLE and age_days <= 90
    return {"transaction": _txn_view(txn), "explanation": _explain(txn), "category_label": CATEGORIES.get(txn["category"]),
            "channel_label": CHANNELS.get(txn["channel"]), "can_raise_complaint": can_complain,
            "complaint_hint": "raise_complaint with this transaction_id" if can_complain else "Older than 90 days or not a disputable debit"}


def summarize_spending(from_date: str | None = None, to_date: str | None = None, group_by: str = "category", direction: str = "debit") -> dict[str, Any]:
    user = current_user()
    end = _parse_date(to_date, "to_date") if to_date else _today()
    start = _parse_date(from_date, "from_date") if from_date else end - timedelta(days=90)
    if isinstance(start, dict):
        return start
    if isinstance(end, dict):
        return end
    groups: dict[str, dict[str, Any]] = {}
    for t in db.rows("transactions", user):
        d = date.fromisoformat(t["date"])
        if not start <= d <= end or t["direction"] != direction:
            continue
        key = {"category": CATEGORIES.get(t["category"], "Other"), "counterparty": t["counterparty"], "month": t["date"][:7],
               "channel": CHANNELS.get(t["channel"], t["channel"])}.get(group_by)
        if key is None:
            return _error("group_by must be category, counterparty, month or channel", group_by="unknown")
        g = groups.setdefault(key, {"group": key, "total": 0, "count": 0})
        g["total"] += t["amount"]
        g["count"] += 1
    rows = sorted(groups.values(), key=lambda g: g["group"] if group_by == "month" else -g["total"])
    return {"from_date": start.isoformat(), "to_date": end.isoformat(), "direction": direction, "group_by": group_by,
            "groups": rows, "total": sum(g["total"] for g in rows)}


# ---------------------------------------------------------------- beneficiaries and transfers


def _ben_status(ben: dict[str, Any]) -> dict[str, Any]:
    active_from = datetime.fromisoformat(ben["added_at"]) + timedelta(hours=COOLING_HOURS)
    cooling = _now() < active_from
    return {"status": "cooling" if cooling else "active", "active_from": active_from.isoformat(),
            "active_from_display": active_from.strftime("%d-%m-%Y %I:%M %p")}


def _find_beneficiary(user: str, text: str) -> dict[str, Any] | None:
    rows = db.rows("beneficiaries", user)
    return next((b for b in rows if _match(b["id"], text, b["name"], b.get("nickname", ""), b["account_number"])), None)


def _sent_today(user: str) -> int:
    today = _today().isoformat()
    return sum(t["amount"] for t in db.rows("transactions", user)
               if t["date"] == today and t["direction"] == "debit" and t.get("to_beneficiary"))


def list_beneficiaries(query: str | None = None) -> dict[str, Any]:
    user = current_user()
    rows = db.rows("beneficiaries", user)
    if query:
        rows = [b for b in rows if _match(b["id"], query, b["name"], b.get("nickname", ""))]
    return {"beneficiaries": [{**{k: b[k] for k in ("id", "name", "nickname", "bank", "branch", "ifsc", "limit")},
                               "account_masked": _mask(b["account_number"]), "within_vnb": b["ifsc"].startswith("VNBA"), **_ben_status(b)}
                              for b in rows],
            "daily_limit": daily_limit(user), "sent_today": _sent_today(user)}


def add_beneficiary(name: str, account_number: str, ifsc: str, limit: int = 100000, nickname: str = "", confirm_account_number: str | None = None) -> dict[str, Any]:
    user = current_user()
    name = " ".join(str(name).split())
    number = str(account_number).replace(" ", "")
    code = str(ifsc).strip().upper()
    if not name:
        return _error("Give the beneficiary's name as in their bank account", name="required")
    if not _ACCOUNT_NO.fullmatch(number):
        return _error("Account number must be 9 to 18 digits", account_number="9–18 digits")
    if confirm_account_number is not None and str(confirm_account_number).replace(" ", "") != number:
        return _error("The two account numbers don't match", confirm_account_number="doesn't match")
    if not _IFSC.fullmatch(code):
        return _error("IFSC must be 11 characters like GGBK0000214 (5th character is zero)", ifsc="like GGBK0000214")
    amount = _amount(limit, "limit")
    if isinstance(amount, dict):
        return amount
    if amount > BENEFICIARY_MAX_LIMIT:
        return _error(f"The highest limit per beneficiary is {rupees(BENEFICIARY_MAX_LIMIT)}", limit="too high")
    if any(b["account_number"] == number for b in db.rows("beneficiaries", user)):
        return _error("This account is already a beneficiary", account_number="already added")
    ben = {"user_id": user, "id": _next_id("beneficiaries", user, "BEN-"), "name": name, "nickname": nickname.strip(), "account_number": number,
           "ifsc": code, "bank": BANK_BY_IFSC.get(code[:4], f"{code[:4]} bank"), "branch": "As per IFSC", "limit": amount,
           "added_at": _now().isoformat()}
    db.put("beneficiaries", ben)
    status = _ben_status(ben)
    return {"beneficiary": {**ben, **status}, "message": f"{name} added. You can send money from {status['active_from_display']} (4-hour cooling period)."}


def delete_beneficiary(beneficiary_id: str) -> dict[str, Any]:
    user = current_user()
    ben = _find_beneficiary(user, beneficiary_id)
    if ben is None:
        return _error(f"not_found: no beneficiary {beneficiary_id}")
    db.delete("beneficiaries", user, ben["id"])
    return {"deleted": ben["id"], "message": f"{ben['name']} removed from your beneficiaries."}


def get_transfer_quote(beneficiary_id: str, amount: int, mode: str | None = None) -> dict[str, Any]:
    user = current_user()
    ben = _find_beneficiary(user, beneficiary_id)
    if ben is None:
        return _error(f"not_found: no beneficiary {beneficiary_id} — add them first (add_beneficiary)", beneficiary_id="not found")
    value = _amount(amount)
    if isinstance(value, dict):
        return value
    within = ben["ifsc"].startswith("VNBA")
    options = ["within_vnb"] if within else [m for m in ("imps", "neft", "rtgs") if value >= MODES[m]["min"] and (MODES[m]["max"] is None or value <= MODES[m]["max"])]
    chosen = (mode or "").strip().lower() or options[0]
    result: dict[str, Any] = {"beneficiary": {"id": ben["id"], "name": ben["name"], "bank": ben["bank"], "account_masked": _mask(ben["account_number"])},
                              "amount": value, "modes_available": options, "mode": chosen, "charges": 0}
    if chosen not in MODES:
        return result | _error("mode must be within_vnb, imps, neft or rtgs", mode="unknown") | {"can_send": False}
    if within and chosen != "within_vnb" or not within and chosen == "within_vnb":
        return result | _error(f"{ben['name']} banks with {ben['bank']}: use {', '.join(o.upper() for o in options)}", mode="not for this beneficiary") | {"can_send": False}
    spec = MODES[chosen]
    problems = []
    if value < spec["min"]:
        problems.append(f"{spec['label']} is for ₹2 lakh and above — use NEFT or IMPS")
    if spec["max"] and value > spec["max"]:
        problems.append(f"{spec['label']} allows up to {rupees(spec['max'])} — use NEFT or RTGS")
    status = _ben_status(ben)
    if status["status"] == "cooling":
        problems.append(f"{ben['name']} was added recently and can be paid from {status['active_from_display']} (4-hour cooling period)")
    if value > ben["limit"]:
        problems.append(f"More than this beneficiary's limit of {rupees(ben['limit'])}")
    sent = _sent_today(user)
    if sent + value > daily_limit(user):
        problems.append(f"Over your daily transfer limit of {rupees(daily_limit(user))}: {rupees(max(0, daily_limit(user) - sent))} left today")
    if value > _available(user):
        problems.append(f"Not enough balance ({rupees(_available(user))} available)")
    result.update({"mode_label": spec["label"], "arrives": spec["arrives"], "balance_after": _available(user) - value,
                   "daily_limit_left_after": daily_limit(user) - sent - value, "can_send": not problems})
    if problems:
        result["error"] = problems[0]
        result["problems"] = problems
    return result


def transfer_funds(beneficiary_id: str, amount: int, mode: str | None = None, remarks: str = "") -> dict[str, Any]:
    user = current_user()
    with db.transaction():
        quote = get_transfer_quote(beneficiary_id, amount, mode)
        if not quote.get("can_send"):
            return _error(quote.get("error", "This transfer can't be made"), **quote.get("fields", {}))
        ben = _find_beneficiary(user, beneficiary_id)
        assert ben is not None
        m = quote["mode"]
        ref = _ref("N" if m == "neft" else "")
        note = re.sub(r"[^A-Za-z0-9 ]", "", remarks)[:20]
        narration = {"within_vnb": f"TO TRANSFER-INB {ben['name'].upper()} {ben['account_number']}{(' ' + note) if note else ''}--",
                     "imps": f"TO TRANSFER-IMPS/P2A/{ref}/{ben['name'].upper()[:12]}/{ben['ifsc'][:4]}/{note or 'Transfer'}--",
                     "neft": f"TO TRANSFER-NEFT*{ben['ifsc']}*{ref}*{ben['name'].upper()[:16]}--",
                     "rtgs": f"TO TRANSFER-RTGS*{ben['ifsc']}*VNBAR{ref}*{ben['name'].upper()[:16]}--"}[m]
        txn = _post(user, amount=quote["amount"], direction="debit", narration=narration, category="transfer",
                    counterparty=f"{ben['name']} ({ben['bank']})", channel={"within_vnb": "intra_bank"}.get(m, m))
        txn["to_beneficiary"] = ben["id"]
        db.put("transactions", txn)
    return {"transfer": {"reference": txn["ref"], "transaction_id": txn["id"], "amount": txn["amount"], "to": ben["name"], "mode": MODES[m]["label"],
                         "arrives": MODES[m]["arrives"], "balance_after": txn["balance_after"]},
            "message": f"{rupees(txn['amount'])} sent to {ben['name']} by {MODES[m]['label']} (ref {txn['ref']}) — arrives {MODES[m]['arrives']}."}


# ---------------------------------------------------------------- loans


def _band(cibil: int) -> int:
    return 0 if cibil >= 800 else 1 if cibil >= 750 else 2 if cibil >= 700 else 3


def _processing_fee(product: dict[str, Any], amount: int) -> int:
    p = product["processing"]
    if not p["percent"]:
        return 0
    return _with_gst(min(max(amount * p["percent"] / 100, p["min"]), p["max"]))


def _lafd_deposits(user: str) -> list[dict[str, Any]]:
    return [d for d in db.rows("deposits", user) if d["kind"] == "fd" and d["status"] == "active" and not d.get("lien")]


def _product_rate(pid: str, cust: dict[str, Any], *, for_girl_student: bool = False, user: str | None = None) -> float | None:
    product = LOAN_PRODUCTS[pid]
    if pid == "loan_against_fd":
        deps = _lafd_deposits(user) if user else []
        return round(max(d["rate"] for d in deps) + product["rate_over_fd"], 2) if deps else None
    rate = product["rates"][_band(cust["cibil_score"])]
    if pid == "personal_loan" and cust.get("employer_type") == "government":
        rate -= product["govt_employee_discount"]
    if pid == "education_loan" and for_girl_student:
        rate -= product["girl_discount"]
    return round(rate, 2)


MAX_EMI_SHARE = 0.60  # all EMIs together, as a share of net salary
DEFAULT_TENURE = {"home_loan": 240, "home_improvement": 120, "car_loan": 60, "personal_loan": 48, "education_loan": 84, "gold_loan": 12, "loan_against_fd": 12}


def _evaluate(user: str, pid: str, *, amount: int | None, tenure: int | None, property_value: int | None, vehicle_price: int | None,
              gold_grams: float | None, for_girl_student: bool) -> dict[str, Any]:
    cust = _customer(user)
    product = LOAN_PRODUCTS[pid]
    age = _age(cust["dob"])
    income = cust["net_monthly_income"]
    existing = _existing_emi(user)
    reasons: list[str] = []
    needs: list[str] = []
    rate = _product_rate(pid, cust, for_girl_student=for_girl_student, user=user)
    max_tenure = product["max_tenure_months"] or 120
    age_end = product["max_age_at_end"]
    if pid == "personal_loan" and cust.get("has_pension"):
        age_end = 60  # salaried: must be repaid by retirement
    max_tenure = min(max_tenure, max(0, (age_end - age) * 12))
    caps: list[tuple[str, int]] = [("product maximum", product["max_amount"])]
    deps = _lafd_deposits(user) if pid == "loan_against_fd" else []
    if pid == "loan_against_fd":
        if not deps:
            reasons.append("No free fixed deposit to pledge (tax-saver FDs can't be pledged)")
        else:
            soonest = min(date.fromisoformat(d["maturity"]) for d in deps)
            max_tenure = max(1, (soonest.year - _today().year) * 12 + soonest.month - _today().month)
            caps.append(("90% of your fixed deposits", int(sum(_deposit_value(d) for d in deps) * 0.9)))
    t = min(int(tenure or DEFAULT_TENURE[pid]), max_tenure) if max_tenure else 0
    if not tenure and rate and t and amount and existing + emi(int(amount), rate, t) > income * MAX_EMI_SHARE:
        t = max_tenure  # the usual tenure is unaffordable: spread it as long as the product allows
    if tenure and int(tenure) > max_tenure:
        reasons.append(f"Longest tenure for you is {max_tenure} months" + (" (until your FD matures)" if pid == "loan_against_fd" else f" (must end by age {age_end})"))
    if rate is not None and t > 0 and product.get("foir"):
        room = income * product["foir"] - existing
        caps.append((f"repayment capacity ({int(product['foir'] * 100)}% of salary minus current EMIs {rupees(existing)})", _pv(room, rate, t)))
    if pid == "personal_loan":
        caps.append(("24 × net monthly salary", income * product["income_multiple"]))
    if pid == "home_loan":
        if property_value:
            ltv = 0.9 if property_value <= 3000000 else 0.8 if property_value <= 7500000 else 0.75
            caps.append((f"{int(ltv * 100)}% of the property value", int(property_value * ltv)))
        else:
            needs.append("property_value")
    if pid == "car_loan":
        if vehicle_price:
            caps.append(("90% of the on-road price", int(vehicle_price * 0.9)))
        else:
            needs.append("vehicle_price")
    if pid == "education_loan":
        caps.append(("₹7.5 lakh without collateral", 750000))
    if pid == "gold_loan":
        if gold_grams:
            caps.append(("75% of the gold's value", int(float(gold_grams) * GOLD_RATE_PER_GRAM_22K * 0.75)))
        else:
            needs.append("gold_grams")
            reasons.append("Depends on how much gold you can pledge — tell me the grams (22 carat)")
    max_amount = max(0, min(c[1] for c in caps))
    limiting = min(caps, key=lambda c: c[1])[0]
    want = int(amount) if amount else max_amount
    if amount and want > max_amount:
        reasons.append(f"You can get up to {rupees(max_amount)} (limited by {limiting})")
    if want < product["min_amount"]:
        reasons.append(f"Minimum loan is {rupees(product['min_amount'])}")
    if rate is None:
        reasons.append("Not available")
    instalment = emi(want, rate, t) if rate and t else 0
    fee = _processing_fee(product, want)
    interest = instalment * t - want if instalment else 0
    if instalment and existing + instalment > income * MAX_EMI_SHARE:
        reasons.append(f"EMI of {rupees(instalment)} would take your EMIs to {round((existing + instalment) / income * 100)}% of salary — too much")
    eligible = not reasons and rate is not None and t > 0
    after_emis = existing + (instalment if eligible else 0)
    yearly_cost = round((rate or 0) + (fee / want * 100 * 12 / t if want and t else 0), 2)
    return {
        "product": pid, "name": product["name"], "eligible": eligible, "reasons": reasons, "needs_info": needs,
        "rate": rate, "tenure_months": t, "max_tenure_months": max_tenure, "amount": want, "max_amount": max_amount, "limited_by": limiting,
        "emi": instalment, "total_interest": interest, "processing_fee_incl_gst": fee, "total_cost": interest + fee, "yearly_cost_percent": yearly_cost,
        "emi_to_income_after": round(after_emis / income * 100, 1),
        "collateral": product["collateral"], "turnaround": product["turnaround"], "prepayment": product["prepayment"],
        "notes": product["notes"] + ([f"Pledges {', '.join(d['id'] for d in deps)} — it keeps earning {max(d['rate'] for d in deps)}%"] if deps else []),
    }


def list_loan_products(product: str | None = None) -> dict[str, Any]:
    user = current_user()
    cust = _customer(user)
    out = []
    for pid, p in LOAN_PRODUCTS.items():
        if product and pid != product:
            continue
        your_rate = _product_rate(pid, cust, user=user)
        out.append({"product": pid, "name": p["name"], "for": [LOAN_PURPOSES[x] for x in p["purposes"]],
                    "rates_by_cibil": None if pid == "loan_against_fd" else dict(zip(["800+", "750–799", "700–749", "below 700"], p["rates"])),
                    "your_rate": your_rate, "max_tenure_months": p["max_tenure_months"], "amount": p["ltv"],
                    "processing_fee": "Nil" if not p["processing"]["percent"] else f"{p['processing']['percent']}% (min {rupees(p['processing']['min'])}, max {rupees(p['processing']['max'])}) + 18% GST",
                    "prepayment": p["prepayment"], "collateral": p["collateral"], "turnaround": p["turnaround"], "notes": p["notes"]})
    if product and not out:
        return _error(f"not_found: no loan product {product}", product="unknown")
    return {"products": out, "your_cibil": cust["cibil_score"], "purposes": LOAN_PURPOSES}


def recommend_loans(purpose: str, amount: int | None = None, tenure_months: int | None = None, property_value: int | None = None,
                    vehicle_price: int | None = None, gold_grams: float | None = None, for_girl_student: bool = False) -> dict[str, Any]:
    user = current_user()
    if purpose not in LOAN_PURPOSES:
        return _error(f"purpose must be one of: {', '.join(LOAN_PURPOSES)}", purpose="unknown")
    if amount is not None:
        value = _amount(amount)
        if isinstance(value, dict):
            return value
        amount = value
    cust = _customer(user)
    options = [_evaluate(user, pid, amount=amount, tenure=tenure_months, property_value=property_value, vehicle_price=vehicle_price,
                         gold_grams=gold_grams, for_girl_student=_bool(for_girl_student))
               for pid, p in LOAN_PRODUCTS.items() if purpose in p["purposes"]]
    ranked = sorted([o for o in options if o["eligible"]], key=lambda o: o["yearly_cost_percent"]) + [o for o in options if not o["eligible"]]
    best = ranked[0] if ranked and ranked[0]["eligible"] else None
    why = None
    if best:
        others = [o for o in ranked[1:] if o["eligible"]]
        why = (f"{best['name']} is cheapest per year: {best['rate']}% interest"
               + (f" + fee ≈ {best['yearly_cost_percent']}% a year" if best["processing_fee_incl_gst"] else ", no processing fee")
               + f"; EMI {rupees(best['emi'])} for {best['tenure_months']} months"
               + (f" (next: {others[0]['name']} at ≈ {others[0]['yearly_cost_percent']}%)" if others else "") + ".")
    return {
        "purpose": LOAN_PURPOSES[purpose],
        "profile_used": {"age": _age(cust["dob"]), "net_monthly_income": cust["net_monthly_income"], "current_emis": _existing_emi(user),
                         "cibil_score": cust["cibil_score"], "employer": cust["employer_type"]},
        "options": ranked, "best": best and {"product": best["product"], "name": best["name"], "why": why},
        "ask_for": sorted({n for o in options for n in o["needs_info"]}),
        "note": "Ranked by yearly cost (interest rate + processing fee spread over the tenure) among options whose EMI keeps all EMIs within 60% of salary. "
                "total_cost = interest + fee over that option's own tenure (a shorter tenure always costs less in total).",
    }


def calculate_emi(amount: int, tenure_months: int, rate: float | None = None, product: str | None = None) -> dict[str, Any]:
    user = current_user()
    value = _amount(amount)
    if isinstance(value, dict):
        return value
    months = _int(tenure_months, "tenure_months")
    if isinstance(months, dict):
        return months
    if not 1 <= months <= 360:
        return _error("tenure_months must be between 1 and 360", tenure_months="1–360")
    if rate is None:
        if not product or product not in LOAN_PRODUCTS:
            return _error("Give a rate or a product", rate="required")
        rate = _product_rate(product, _customer(user), user=user)
        if rate is None:
            return _error("No rate for that product (no FD to pledge)")
    rate = float(rate)
    instalment = emi(value, rate, months)
    schedule = []
    balance = float(value)
    r = rate / 1200
    for year in range(1, math.ceil(months / 12) + 1):
        paid_p = paid_i = 0.0
        for _ in range(min(12, months - (year - 1) * 12)):
            interest = balance * r
            principal = min(balance, instalment - interest)
            balance -= principal
            paid_i += interest
            paid_p += principal
        schedule.append({"year": year, "principal": int(paid_p), "interest": int(paid_i), "balance": max(0, int(balance))})
    return {"amount": value, "rate": rate, "tenure_months": months, "emi": instalment, "total_interest": instalment * months - value,
            "total_payable": instalment * months, "yearly_schedule": schedule}


def apply_for_loan(product: str, amount: int, tenure_months: int, purpose: str = "personal_need", deposit_id: str | None = None,
                   gold_grams: float | None = None, property_value: int | None = None, vehicle_price: int | None = None) -> dict[str, Any]:
    user = current_user()
    if product not in LOAN_PRODUCTS:
        return _error(f"product must be one of: {', '.join(LOAN_PRODUCTS)}", product="unknown")
    value = _amount(amount)
    if isinstance(value, dict):
        return value
    months = _int(tenure_months, "tenure_months")
    if isinstance(months, dict):
        return months
    option = _evaluate(user, product, amount=value, tenure=months, property_value=property_value, vehicle_price=vehicle_price,
                       gold_grams=gold_grams, for_girl_student=False)
    if not option["eligible"]:
        return _error("; ".join(option["reasons"]) or "Not eligible for this loan", amount="not eligible")
    p = LOAN_PRODUCTS[product]
    if product == "loan_against_fd":
        deps = _lafd_deposits(user)
        dep = next((d for d in deps if not deposit_id or d["id"] == deposit_id.strip().upper()), None)
        if dep is None:
            return _error(f"No free fixed deposit {deposit_id or ''} to pledge".strip(), deposit_id="not available")
        with db.transaction():
            loan_id = _next_id("loans", user, "LN-")
            loan = {"user_id": user, "id": loan_id, "product": product, "name": p["name"], "number": _ref("4")[:11], "sanctioned": value,
                    "rate": option["rate"], "tenure_months": option["tenure_months"], "emi": option["emi"], "start": _today().isoformat(),
                    "emi_day": _today().day if _today().day <= 28 else 28, "status": "active", "emis_paid": 0, "outstanding": value,
                    "next_emi_date": add_months(_today(), 1).isoformat(), "security": dep["id"]}
            db.put("loans", loan)
            dep["lien"] = value
            db.put("deposits", dep)
            _post(user, amount=value, direction="credit", narration=f"BY TRANSFER-LOAN DISB {loan['number']} AGST FD {dep['number']}--",
                  category="transfer", counterparty=f"Loan against FD ({loan_id})", channel="loan")
        return {"loan": _loan_view(loan), "message": f"{rupees(value)} credited to your savings account. {dep['id']} is marked with a lien and keeps earning {dep['rate']}%."}
    app_id = _next_id("applications", user, "APP-", 3)
    application = {"user_id": user, "id": app_id, "product": product, "name": p["name"], "amount": value, "tenure_months": option["tenure_months"],
                   "rate": option["rate"], "emi": option["emi"], "purpose": LOAN_PURPOSES.get(purpose, purpose), "submitted": _today().isoformat(),
                   "status": "Submitted — branch will call within 2 working days",
                   "documents": _loan_documents(product)}
    db.put("applications", application)
    return {"application": application,
            "message": f"Application {app_id} for {p['name']} ({rupees(value)}) submitted. Keep these ready: {', '.join(application['documents'])}."}


def _loan_documents(product: str) -> list[str]:
    base = ["PAN and Aadhaar", "Last 3 salary slips", "Form 16 / last 2 years' ITR"]
    extra = {"home_loan": ["Sale agreement and title papers", "Approved building plan"], "home_improvement": ["House title papers", "Contractor's estimate"],
             "car_loan": ["Proforma invoice from the dealer"], "education_loan": ["Admission letter", "Fee structure", "Student's marksheets"],
             "gold_loan": ["The gold ornaments (at the branch)"], "personal_loan": []}
    return (base if product != "gold_loan" else ["PAN and Aadhaar"]) + extra.get(product, [])


def _loan_view(loan: dict[str, Any]) -> dict[str, Any]:
    months_left = _months_to_repay(loan["outstanding"], loan["rate"], loan["emi"])
    return {k: loan.get(k) for k in ("id", "name", "number", "sanctioned", "rate", "tenure_months", "emi", "start", "outstanding", "next_emi_date",
                                      "emis_paid", "vehicle", "security", "status")} | {
        "emis_left": months_left, "ends": add_months(_today(), months_left).isoformat() if months_left < 10**4 else None}


def list_my_loans() -> dict[str, Any]:
    user = current_user()
    return {"loans": [_loan_view(l) for l in db.rows("loans", user)], "applications": db.rows("applications", user),
            "monthly_emis": _existing_emi(user)}


def get_prepayment_quote(loan_id: str, amount: int) -> dict[str, Any]:
    user = current_user()
    loan = db.get("loans", user, loan_id.strip().upper())
    if loan is None or loan["status"] != "active":
        return _error(f"not_found: no active loan {loan_id}")
    value = _amount(amount)
    if isinstance(value, dict):
        return value
    value = min(value, loan["outstanding"])
    months_now = _months_to_repay(loan["outstanding"], loan["rate"], loan["emi"])
    months_after = _months_to_repay(loan["outstanding"] - value, loan["rate"], loan["emi"])
    interest_now = loan["emi"] * months_now - loan["outstanding"]
    last_emi_after = loan["outstanding"] - value
    interest_after = max(0, loan["emi"] * months_after - last_emi_after)
    started = date.fromisoformat(loan["start"])
    charge = 0
    if loan["product"] == "car_loan" and (_today() - started).days < 730:
        charge = int(value * 0.02)
    if loan["product"] == "personal_loan":
        charge = int(value * 0.03)
    cust = _customer(user)
    fd_rate = max((d["rate"] for d in _lafd_deposits(user)), default=0)
    post_tax = round(fd_rate * (1 - cust["income_tax_slab_percent"] / 100), 2)
    return {"loan": loan["id"], "prepay": value, "charge": charge, "outstanding_after": loan["outstanding"] - value, "emi": loan["emi"],
            "emis_left_now": months_now, "emis_left_after": months_after, "months_saved": months_now - months_after,
            "interest_saved": max(0, interest_now - interest_after) - charge, "balance_after": _available(user) - value - charge,
            "comparison": f"The loan costs {loan['rate']}% a year; your best FD earns {fd_rate}% ({post_tax}% after {cust['income_tax_slab_percent']}% tax) — "
                          + ("prepaying saves more than the FD earns." if loan["rate"] > post_tax else "the FD earns more after tax.")}


def prepay_loan(loan_id: str, amount: int) -> dict[str, Any]:
    user = current_user()
    with db.transaction():
        quote = get_prepayment_quote(loan_id, amount)
        if "error" in quote:
            return quote
        problem = _debit_or_error(user, quote["prepay"] + quote["charge"])
        if problem:
            return problem
        loan = db.get("loans", user, quote["loan"])
        assert loan is not None
        loan["outstanding"] -= quote["prepay"]
        if loan["outstanding"] <= 0:
            loan["status"] = "closed"
        db.put("loans", loan)
        _post(user, amount=quote["prepay"], direction="debit", narration=f"TO TRANSFER-LOAN PREPAYMENT {loan['number']}--", category="loan_emi",
              counterparty=f"Prepayment of {loan['name']} ({loan['id']})", channel="loan")
        if quote["charge"]:
            _post(user, amount=quote["charge"], direction="debit", narration=f"PREPAYMENT CHGS {loan['number']}--", category="charges",
                  counterparty="Loan prepayment charge", channel="charges")
    return {"loan": _loan_view(loan), "message": f"Prepaid {rupees(quote['prepay'])}: {quote['months_saved']} fewer EMIs, about {rupees(quote['interest_saved'])} less interest."}


# ---------------------------------------------------------------- deposits


def _fd_rate(days: int, senior: bool, scheme: str = "regular") -> float | None:
    if scheme == "special":
        rate = SPECIAL_FD["rate"]
    elif scheme == "tax_saver":
        rate = TAX_SAVER["rate"]
    else:
        slab = next((s for s in FD_SLABS if s["min_days"] <= days <= s["max_days"]), None)
        if slab is None:
            return None
        rate = slab["rate"]
    return round(rate + (SENIOR_EXTRA if senior else 0), 2)


def get_deposit_rates() -> dict[str, Any]:
    return {
        "fixed_deposit_slabs": [{"tenure": s["label"], "general": s["rate"], "senior_citizen": round(s["rate"] + SENIOR_EXTRA, 2)} for s in FD_SLABS],
        "special_scheme": SPECIAL_FD | {"senior_citizen": SPECIAL_FD["rate"] + SENIOR_EXTRA},
        "tax_saver": TAX_SAVER | {"lock_in": "5 years, no premature closure or loan", "senior_citizen": TAX_SAVER["rate"] + SENIOR_EXTRA},
        "recurring_deposit": "Same as the FD slab for the RD's tenure (12–120 months), minimum ₹100 a month",
        "savings_bank": SB_RATE,
        "small_savings": {k: {"name": v["name"], "rate": v["rate"], "tax": v["tax"]} for k, v in SMALL_SAVINGS.items()},
        "premature_closure": "Rate for the period actually held minus 0.50% (below ₹5 lakh) or 1.00% (₹5 lakh and above); no interest if held under 7 days",
        "tds": f"{TDS_RATE}% when interest from all your deposits in a financial year is above ₹40,000 (₹50,000 for senior citizens); submit Form 15G/15H if your income is below the taxable limit",
        "compounding": "Quarterly for 6 months and more; simple interest below 6 months",
    }


def _days_for(tenure_months: Any, tenure_days: Any) -> int | dict[str, Any]:
    if tenure_days not in (None, ""):
        return _int(tenure_days, "tenure_days")
    if tenure_months not in (None, ""):
        months = _int(tenure_months, "tenure_months")
        if isinstance(months, dict):
            return months
        return (add_months(_today(), months) - _today()).days
    return _error("Give tenure_months or tenure_days", tenure_months="required")


def quote_deposit(kind: str = "fd", amount: int | None = None, tenure_months: int | None = None, tenure_days: int | None = None,
                  payout: str = "cumulative", monthly_amount: int | None = None) -> dict[str, Any]:
    user = current_user()
    cust = _customer(user)
    senior = _age(cust["dob"]) >= 60
    slab = cust["income_tax_slab_percent"]
    if kind == "rd":
        value = _amount(monthly_amount or amount, "monthly_amount")
        if isinstance(value, dict):
            return value
        months = _int(tenure_months, "tenure_months") if tenure_months else _error("tenure_months is required for an RD", tenure_months="required")
        if isinstance(months, dict):
            return months
        if not RD_MONTHS[0] <= months <= RD_MONTHS[1] or value < RD_MIN_MONTHLY:
            return _error("RDs run 12–120 months with at least ₹100 a month", tenure_months="12–120")
        rate = _fd_rate(months * 30 + 5, senior)
        maturity = _rd_maturity(value, rate, months)
        interest = maturity - value * months
        return {"kind": "rd", "monthly_amount": value, "tenure_months": months, "rate": rate, "deposited": value * months, "maturity_amount": maturity,
                "interest": interest, "interest_after_tax": int(interest * (1 - slab / 100)), "maturity_date": add_months(_today(), months).isoformat()}
    value = _amount(amount)
    if isinstance(value, dict):
        return value
    scheme = {"fd": "regular", "special": "special", "tax_saver": "tax_saver"}.get(kind)
    if scheme is None:
        return _error("kind must be fd, special, tax_saver or rd", kind="unknown")
    days = SPECIAL_FD["days"] if scheme == "special" else 1826 if scheme == "tax_saver" else _days_for(tenure_months, tenure_days)
    if isinstance(days, dict):
        return days
    if not 7 <= days <= 3650:
        return _error("FDs run from 7 days to 10 years", tenure_days="7–3650 days")
    if not FD_MIN <= value <= FD_MAX:
        return _error(f"FD amount must be {rupees(FD_MIN)}–{rupees(FD_MAX)}", amount="out of range")
    if scheme == "tax_saver" and value > TAX_SAVER["max_per_year"]:
        return _error("Tax saver FDs take up to ₹1,50,000 a year", amount="max ₹1,50,000")
    rate = _fd_rate(days, senior, scheme)
    if rate is None:
        return _error("No rate for that tenure")
    if payout not in ("cumulative", "quarterly", "monthly"):
        return _error("payout must be cumulative, quarterly or monthly", payout="unknown")
    maturity = _fd_amount(value, rate, days, payout)
    interest = maturity - value if payout == "cumulative" else int(value * rate / 100 * days / 365)
    per_payout = None
    if payout == "quarterly":
        per_payout = int(value * rate / 400)
    elif payout == "monthly":
        per_payout = int(value * rate / 1200)
    yearly_interest = interest * 365 / days
    threshold = TDS_THRESHOLD["senior" if senior else "general"]
    tax_benefit = int(value * slab / 100) if scheme == "tax_saver" else 0
    return {"kind": kind, "scheme": {"regular": "Regular FD", "special": SPECIAL_FD["name"], "tax_saver": TAX_SAVER["name"]}[scheme],
            "amount": value, "tenure_days": days, "rate": rate, "payout": payout, "per_payout": per_payout,
            "maturity_amount": maturity if payout == "cumulative" else value, "interest": interest,
            "interest_after_tax": int(interest * (1 - slab / 100)), "maturity_date": (_today() + timedelta(days=days)).isoformat(),
            "tds_likely": yearly_interest > threshold, "tax_saving_80c": tax_benefit,
            "notes": (["Locked in for 5 years; can't be pledged or closed early", f"Saves about {rupees(tax_benefit)} tax under 80C (old regime)"]
                      if scheme == "tax_saver" else [])}


def _deposit_view(dep: dict[str, Any]) -> dict[str, Any]:
    view = {k: dep.get(k) for k in ("id", "kind", "scheme", "number", "principal", "monthly", "rate", "opened", "maturity", "payout", "auto_renew",
                                     "installments_paid", "months", "lien", "status")}
    view["current_value"] = _deposit_value(dep)
    if dep["kind"] == "rd":
        view["maturity_amount"] = _rd_maturity(dep["monthly"], dep["rate"], dep["months"])
    else:
        view["maturity_amount"] = _fd_amount(dep["principal"], dep["rate"], (date.fromisoformat(dep["maturity"]) - date.fromisoformat(dep["opened"])).days,
                                             dep.get("payout", "cumulative"))
    view["days_to_maturity"] = (date.fromisoformat(dep["maturity"]) - _today()).days
    return view


def list_deposits() -> dict[str, Any]:
    user = current_user()
    deps = [_deposit_view(d) for d in db.rows("deposits", user)]
    ppf = db.get("accounts", user, "PPF-01")
    return {"deposits": deps, "ppf": ppf, "total_current_value": sum(d["current_value"] for d in deps if d["status"] == "active")}


def open_fixed_deposit(amount: int, tenure_months: int | None = None, tenure_days: int | None = None, scheme: str = "fd",
                       payout: str = "cumulative", auto_renew: bool = True) -> dict[str, Any]:
    user = current_user()
    quote = quote_deposit(scheme, amount, tenure_months, tenure_days, payout)
    if "error" in quote:
        return quote
    with db.transaction():
        problem = _debit_or_error(user, quote["amount"])
        if problem:
            return problem
        dep_id = _next_id("deposits", user, "FD-")
        number = "3987" + _ref()[:7]
        dep = {"user_id": user, "id": dep_id, "kind": "tax_saver" if scheme == "tax_saver" else "fd", "scheme": quote["scheme"], "number": number,
               "principal": quote["amount"], "rate": quote["rate"], "opened": _today().isoformat(), "tenure_days": quote["tenure_days"],
               "maturity": quote["maturity_date"], "payout": payout, "auto_renew": _bool(auto_renew) and scheme != "tax_saver", "status": "active", "lien": 0}
        db.put("deposits", dep)
        _post(user, amount=quote["amount"], direction="debit", narration=f"TO TRANSFER-E-TDR {number} OPENED--", category="savings_investment",
              counterparty=f"Fixed deposit {dep_id}", channel="fd")
    return {"deposit": _deposit_view(dep), "message": f"{dep_id} opened: {rupees(quote['amount'])} at {quote['rate']}% till {quote['maturity_date']} (receipt no. {number})."}


def open_recurring_deposit(monthly_amount: int, tenure_months: int) -> dict[str, Any]:
    user = current_user()
    quote = quote_deposit("rd", monthly_amount=monthly_amount, tenure_months=tenure_months)
    if "error" in quote:
        return quote
    with db.transaction():
        problem = _debit_or_error(user, quote["monthly_amount"])
        if problem:
            return problem
        dep_id = _next_id("deposits", user, "RD-")
        number = "3987" + _ref()[:7]
        dep = {"user_id": user, "id": dep_id, "kind": "rd", "scheme": "Recurring deposit", "number": number, "monthly": quote["monthly_amount"],
               "rate": quote["rate"], "opened": _today().isoformat(), "months": quote["tenure_months"], "maturity": quote["maturity_date"],
               "installments_paid": 1, "status": "active"}
        db.put("deposits", dep)
        _post(user, amount=quote["monthly_amount"], direction="debit", narration=f"TO TRANSFER-RD INSTL {number}--", category="savings_investment",
              counterparty=f"Recurring deposit {dep_id}", channel="fd")
    return {"deposit": _deposit_view(dep), "message": f"{dep_id} opened: {rupees(quote['monthly_amount'])} a month for {quote['tenure_months']} months at {quote['rate']}% — "
                                                      f"about {rupees(quote['maturity_amount'])} at maturity. Instalments are debited on the {_today().day}th."}


def get_fd_closure_quote(deposit_id: str) -> dict[str, Any]:
    user = current_user()
    dep = db.get("deposits", user, deposit_id.strip().upper())
    if dep is None or dep["status"] != "active" or dep["kind"] == "rd":
        return _error(f"not_found: no active fixed deposit {deposit_id}")
    if dep["kind"] == "tax_saver" and _today() < date.fromisoformat(dep["maturity"]):
        return {"deposit": dep["id"], "can_close": False, "error": f"Tax saver FDs are locked in until {dep['maturity']}"}
    if dep.get("lien"):
        return {"deposit": dep["id"], "can_close": False, "error": f"{dep['id']} secures a loan ({rupees(dep['lien'])} lien) — repay the loan first"}
    opened = date.fromisoformat(dep["opened"])
    held = (_today() - opened).days
    senior = _age(_customer(user)["dob"]) >= 60
    applicable = _fd_rate(max(held, 7), senior) or 0
    penalty = PREMATURE_PENALTY[0 if dep["principal"] < 500000 else 1]
    rate = 0.0 if held < 7 else max(0.0, round(applicable - penalty, 2))
    payout = _fd_amount(dep["principal"], rate, held)
    full = _deposit_view(dep)["maturity_amount"]
    return {"deposit": dep["id"], "can_close": True, "held_days": held, "booked_rate": dep["rate"], "rate_for_period_held": applicable,
            "penalty": penalty, "rate_paid": rate, "payout": payout, "interest": payout - dep["principal"],
            "if_held_to_maturity": full, "you_give_up": full - payout,
            "alternative": "Need money for a short while? A loan against this FD (FD rate + 1%) keeps it earning — see recommend_loans."}


def close_fixed_deposit(deposit_id: str) -> dict[str, Any]:
    user = current_user()
    with db.transaction():
        quote = get_fd_closure_quote(deposit_id)
        if not quote.get("can_close"):
            return _error(quote.get("error", "This deposit can't be closed"))
        dep = db.get("deposits", user, quote["deposit"])
        assert dep is not None
        dep["status"] = "closed"
        dep["closed"] = _today().isoformat()
        db.put("deposits", dep)
        _post(user, amount=quote["payout"], direction="credit", narration=f"BY TRANSFER-TDR CLOSED PREMAT {dep['number']}--", category="savings_investment",
              counterparty=f"Fixed deposit {dep['id']} closed early", channel="fd")
    return {"closed": dep["id"], "payout": quote["payout"], "message": f"{dep['id']} closed: {rupees(quote['payout'])} credited to your savings account."}


def compare_savings_options(years: int, lump_sum: int | None = None, monthly: int | None = None) -> dict[str, Any]:
    user = current_user()
    cust = _customer(user)
    y = _int(years, "years")
    if isinstance(y, dict):
        return y
    if not 1 <= y <= 25:
        return _error("years must be 1–25", years="1–25")
    if not lump_sum and not monthly:
        return _error("Give a lump_sum, a monthly amount, or both", lump_sum="required")
    slab = cust["income_tax_slab_percent"] / 100
    age = _age(cust["dob"])
    lump = int(lump_sum or 0)
    month = int(monthly or 0)
    yearly = lump / max(y, 1) + month * 12
    ppf = db.get("accounts", user, "PPF-01")
    family = _family_with_ages(cust)
    daughter = next((m for m in family if m["relation"] == "daughter"), None)
    options: list[dict[str, Any]] = []

    def grow(rate: float, years_: int, *, lump_: int, monthly_: int) -> int:
        total = lump_ * (1 + rate / 100) ** years_
        total += sum(monthly_ * 12 * (1 + rate / 100) ** (years_ - k - 0.5) for k in range(years_))
        return int(total)

    invested = lump + month * 12 * y
    days = min(3650, 365 * y)
    fd_rate = _fd_rate(days, age >= 60) or 6.5
    fd_value = _fd_amount(lump, fd_rate, days) + (_rd_maturity(month, fd_rate, 12 * y) if month else 0)
    fd_after_tax = int(invested + (fd_value - invested) * (1 - slab))
    options.append({"option": "Fixed deposit" + (" + recurring deposit" if month and lump else " (RD for monthly)" if month else ""), "rate": fd_rate,
                    "invested": invested, "value": fd_value, "value_after_tax": fd_after_tax, "lock_in": "None (penalty 0.5–1% if closed early)",
                    "tax": "Interest taxed at your slab; TDS above ₹40,000 a year", "eligible": True})
    if ppf:
        room = SMALL_SAVINGS["ppf"]["max_year"] - ppf["this_fy_deposits"]
        ppf_years_left = max(1, date.fromisoformat(ppf["maturity"]).year - _today().year)
        value = grow(7.1, y, lump_=lump, monthly_=month)
        options.append({"option": "Top up your PPF (PPF-01)", "rate": 7.1, "invested": invested, "value": value, "value_after_tax": value,
                        "tax_saving_80c": int(min(yearly, 150000) * slab) * y,
                        "lock_in": f"Matures {ppf['maturity']} ({ppf_years_left} years); partial withdrawal allowed now", "tax": SMALL_SAVINGS["ppf"]["tax"],
                        "eligible": yearly <= 150000, "limit_note": f"Max ₹1,50,000 a financial year — {rupees(room)} room left this year"})
    if daughter and daughter["age"] < 10:
        has_ssy = any(a["kind"] == "ssy" for a in db.rows("accounts", user))
        value = grow(8.2, y, lump_=lump, monthly_=month)
        options.append({"option": f"Sukanya Samriddhi for {daughter['name']}", "rate": 8.2, "invested": invested, "value": value, "value_after_tax": value,
                        "tax_saving_80c": int(min(yearly, 150000) * slab) * y,
                        "lock_in": f"Until she is 21 ({int(daughter['dob'][:4]) + 21}); 50% for education after 18",
                        "tax": SMALL_SAVINGS["ssy"]["tax"], "eligible": yearly <= 150000,
                        "limit_note": ("Already opened" if has_ssy else f"Must be opened before she turns 10 ({int(daughter['dob'][:4]) + 10}-{daughter['dob'][5:]})")})
    if lump:
        ts = quote_deposit("tax_saver", min(lump, 150000))
        if "error" not in ts:
            value = _fd_amount(min(lump, 150000), ts["rate"], 1826)
            options.append({"option": "Tax saver FD (5 years)", "rate": ts["rate"], "invested": min(lump, 150000), "value": value,
                            "value_after_tax": int(min(lump, 150000) + (value - min(lump, 150000)) * (1 - slab)),
                            "tax_saving_80c": ts["tax_saving_80c"], "lock_in": "5 years, no early closure", "tax": "80C on the deposit; interest taxable",
                            "eligible": y >= 5})
    nps = next(iter(db.rows("nps", user)), None)
    options.append({"option": "NPS Tier I" + (" (top up yours)" if nps else ""), "rate": None, "eligible": age < 60 and y <= 60 - age,
                    "tax_saving_80ccd_1b": int(min(yearly, 50000) * slab * 1.04) * y,
                    "lock_in": f"Until 60 ({60 - age} years); 40% must buy a pension", "tax": "Extra ₹50,000 deduction over 80C (80CCD(1B)); market-linked returns",
                    "limit_note": "Market-linked — no guaranteed value; good only if the money can stay till 60"})
    options.append({"option": "Senior Citizens' Savings Scheme", "rate": 8.2, "eligible": age >= 60,
                    "lock_in": "5 years", "tax": SMALL_SAVINGS["scss"]["tax"],
                    "limit_note": "Only for 60+" + ("; your mother " + next((m["name"] for m in family if m["relation"] == "mother"), "") + " can open her own at the branch"
                                                    if any(m["relation"] == "mother" and m["age"] >= 60 for m in family) else "")})
    ranked = sorted([o for o in options if o.get("value_after_tax") and o["eligible"]], key=lambda o: -(o["value_after_tax"] + o.get("tax_saving_80c", 0)))
    return {"years": y, "lump_sum": lump, "monthly": month, "tax_slab_percent": cust["income_tax_slab_percent"], "tax_regime": cust["tax_regime"],
            "options": ranked + [o for o in options if o not in ranked],
            "note": "value_after_tax assumes your slab on taxable interest; tax_saving_80c applies in the old regime within the ₹1.5 lakh 80C limit (shared across PPF, SSY, tax saver FD, insurance premiums)."}


# ---------------------------------------------------------------- government schemes


def list_government_schemes() -> dict[str, Any]:
    user = current_user()
    cust = _customer(user)
    age = _age(cust["dob"])
    enrolled = {e["scheme"] for e in db.rows("enrolments", user)}
    rows = []
    for key, s in GOVT_SCHEMES.items():
        lo, hi = s["join_age"]
        eligible = lo <= age <= hi and not (s.get("taxpayer_excluded") and cust["income_tax_slab_percent"] > 0)
        why = None if eligible else (f"Joining age is {lo}–{hi}; you are {age}" if not lo <= age <= hi else "Not open to income-tax payers")
        rows.append({"scheme": key, "name": s["name"], "kind": s["kind"], "summary": s["summary"], "premium_per_year": s.get("premium"),
                     "cover": s.get("cover"), "eligible": eligible, "why_not": why, "enrolled": key in enrolled})
    family = _family_with_ages(cust)
    daughter = next((m for m in family if m["relation"] == "daughter"), None)
    has_ssy = any(a["kind"] == "ssy" for a in db.rows("accounts", user))
    rows.append({"scheme": "ssy", "name": SMALL_SAVINGS["ssy"]["name"], "kind": "Girl child savings", "summary": f"{SMALL_SAVINGS['ssy']['rate']}% tax-free; ₹250–₹1,50,000 a year for 15 years, matures at 21.",
                 "eligible": bool(daughter and daughter["age"] < 10) and not has_ssy, "enrolled": has_ssy,
                 "why_not": None if daughter and daughter["age"] < 10 else "Only for a daughter under 10"})
    rows.append({"scheme": "ppf", "name": SMALL_SAVINGS["ppf"]["name"], "kind": "Long-term savings", "summary": f"{SMALL_SAVINGS['ppf']['rate']}% tax-free, 15 years.",
                 "eligible": True, "enrolled": db.get("accounts", user, "PPF-01") is not None})
    rows.append({"scheme": "scss", "name": SMALL_SAVINGS["scss"]["name"], "kind": "Senior citizens", "summary": f"{SMALL_SAVINGS['scss']['rate']}%, interest paid quarterly, 5 years, up to ₹30 lakh.",
                 "eligible": age >= 60, "enrolled": False, "why_not": None if age >= 60 else f"Only for 60+ (you are {age}); open at the branch for a parent"})
    return {"age": age, "schemes": rows}


def enroll_in_scheme(scheme: str, nominee_name: str, nominee_relation: str) -> dict[str, Any]:
    user = current_user()
    key = scheme.strip().lower()
    if key not in ("pmjjby", "pmsby"):
        return _error("Online enrolment is for pmjjby or pmsby; APY, SSY and PPF have their own steps", scheme="pmjjby or pmsby")
    info = GOVT_SCHEMES[key]
    cust = _customer(user)
    age = _age(cust["dob"])
    lo, hi = info["join_age"]
    if not lo <= age <= hi:
        return _error(f"{info['name']} is for ages {lo}–{hi}", scheme="not eligible")
    if any(e["scheme"] == key for e in db.rows("enrolments", user)):
        return _error(f"You are already enrolled in {info['name']}", scheme="already enrolled")
    if not str(nominee_name).strip():
        return _error("Give a nominee", nominee_name="required")
    with db.transaction():
        problem = _debit_or_error(user, info["premium"])
        if problem:
            return problem
        enrolment = {"user_id": user, "id": _next_id("enrolments", user, "ENR-"), "scheme": key, "name": info["name"], "cover": info["cover"],
                     "premium": info["premium"], "nominee": f"{nominee_name.strip()} ({nominee_relation.strip()})", "enrolled": _today().isoformat(),
                     "renews": f"{_today().year + (1 if _today().month >= 6 else 0)}-06-01", "certificate": "COI-" + _ref()[:8]}
        db.put("enrolments", enrolment)
        _post(user, amount=info["premium"], direction="debit", narration=f"TO TRANSFER-{key.upper()} PREMIUM COI {enrolment['certificate']}--",
              category="insurance", counterparty=info["name"], channel="auto_debit")
    return {"enrolment": enrolment, "message": f"Enrolled in {info['name']}: {rupees(info['cover'])} cover for {rupees(info['premium'])} a year, renewed automatically every 1 June."}


def open_ssy_account(girl_name: str, girl_dob: str, initial_deposit: int) -> dict[str, Any]:
    user = current_user()
    born = _parse_date(girl_dob, "girl_dob")
    if isinstance(born, dict):
        return born
    age = _age(born.isoformat())
    if age >= 10:
        return _error("SSY can be opened only for a girl under 10", girl_dob="10 or older")
    value = _amount(initial_deposit, "initial_deposit")
    if isinstance(value, dict):
        return value
    if not 250 <= value <= 150000:
        return _error("The first deposit must be ₹250–₹1,50,000", initial_deposit="₹250–₹1,50,000")
    if any(a["kind"] == "ssy" and a["girl_name"].lower() == girl_name.strip().lower() for a in db.rows("accounts", user)):
        return _error(f"{girl_name} already has an SSY account", girl_name="already has one")
    with db.transaction():
        problem = _debit_or_error(user, value)
        if problem:
            return problem
        acc_id = _next_id("accounts", user, "SSY-")
        acc = {"user_id": user, "id": acc_id, "kind": "ssy", "name": "Sukanya Samriddhi account", "girl_name": girl_name.strip(), "girl_dob": born.isoformat(),
               "number": "3301" + _ref()[:7], "opened": _today().isoformat(), "balance": value, "this_fy_deposits": value,
               "maturity": born.replace(year=born.year + 21).isoformat() if not (born.month == 2 and born.day == 29) else date(born.year + 21, 3, 1).isoformat(),
               "deposits_until": add_months(_today(), 180).isoformat(), "status": "active"}
        db.put("accounts", acc)
        _post(user, amount=value, direction="debit", narration=f"TO TRANSFER-SSY A/C {acc['number']} DEP--", category="savings_investment",
              counterparty=f"Sukanya Samriddhi for {acc['girl_name']} ({acc_id})", channel="intra_bank")
    return {"account": acc, "message": f"SSY account {acc_id} opened for {acc['girl_name']} with {rupees(value)}. Bring her birth certificate to the branch within 30 days to complete it."}


def deposit_to_ppf(amount: int) -> dict[str, Any]:
    user = current_user()
    value = _amount(amount)
    if isinstance(value, dict):
        return value
    ppf = db.get("accounts", user, "PPF-01")
    if ppf is None:
        return _error("not_found: no PPF account")
    room = SMALL_SAVINGS["ppf"]["max_year"] - ppf["this_fy_deposits"]
    if value > room:
        return _error(f"PPF takes {rupees(SMALL_SAVINGS['ppf']['max_year'])} a financial year — {rupees(room)} room left", amount="over the yearly limit")
    with db.transaction():
        problem = _debit_or_error(user, value)
        if problem:
            return problem
        ppf["balance"] += value
        ppf["this_fy_deposits"] += value
        db.put("accounts", ppf)
        _post(user, amount=value, direction="debit", narration=f"TO TRANSFER-PPF A/C {ppf['number']} DEP--", category="savings_investment",
              counterparty="PPF deposit (PPF-01)", channel="intra_bank")
    return {"ppf": ppf, "message": f"{rupees(value)} deposited to PPF. {rupees(room - value)} room left this financial year."}


# ---------------------------------------------------------------- services


def _request(user: str, kind: str, summary: str, *, charge: int = 0, eta_days: int = 0, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    req = {"user_id": user, "id": _next_id("requests", user, "SR-", 4), "kind": kind, "summary": summary, "raised": _today().isoformat(),
           "status": "Completed" if not eta_days else "In process", "expected_by": (_today() + timedelta(days=eta_days)).isoformat() if eta_days else None,
           "charge": charge, **(extra or {})}
    db.put("requests", req)
    return req


def request_cheque_book(leaves: int = 25, deliver_to: str = "registered_address") -> dict[str, Any]:
    user = current_user()
    n = _int(leaves, "leaves")
    if isinstance(n, dict):
        return n
    if n not in (10, 25, 50, 100):
        return _error("A cheque book has 10, 25, 50 or 100 leaves", leaves="10, 25, 50 or 100")
    if deliver_to not in ("registered_address", "branch"):
        return _error("deliver_to must be registered_address or branch", deliver_to="unknown")
    sb = _savings(user)
    free_left = max(0, CHEQUE_FREE_LEAVES_PER_FY - sb.get("cheque_leaves_this_fy", 0))
    charge = _with_gst(max(0, n - free_left) * CHEQUE_CHARGE_PER_LEAF)
    with db.transaction():
        if charge:
            problem = _debit_or_error(user, charge)
            if problem:
                return problem
        sb = _savings(user)
        sb["cheque_leaves_this_fy"] = sb.get("cheque_leaves_this_fy", 0) + n
        db.put("accounts", sb)
        if charge:
            _post(user, amount=charge, direction="debit", narration=f"CHQ BOOK ISSUE CHGS {n} LVS INCL GST--", category="charges",
                  counterparty="Cheque book charges", channel="charges")
        where = _customer(user)["address"] if deliver_to == "registered_address" else f"{_customer(user)['branch']} branch"
        req = _request(user, "cheque_book", f"Cheque book, {n} leaves, to {where}", charge=charge, eta_days=7 if deliver_to == "registered_address" else 3)
    return {"request": req, "message": f"Cheque book ({n} leaves) requested — {'arrives by speed post' if deliver_to == 'registered_address' else 'collect at the branch'} by {req['expected_by']}"
                                       + (f"; {rupees(charge)} charged (first {CHEQUE_FREE_LEAVES_PER_FY} leaves a year are free)." if charge else " — free.")}


def stop_cheque(cheque_from: int, cheque_to: int | None = None, reason: str = "lost") -> dict[str, Any]:
    user = current_user()
    first = _int(cheque_from, "cheque_from")
    if isinstance(first, dict):
        return first
    last = _int(cheque_to, "cheque_to") if cheque_to not in (None, "") else first
    if isinstance(last, dict):
        return last
    if reason not in STOP_REASONS:
        return _error(f"reason must be one of: {', '.join(STOP_REASONS)}", reason="unknown")
    series = _savings(user)["cheque_series"]
    if not series["from"] <= first <= last <= series["to"]:
        return _error(f"Your cheque book has leaves {series['from']}–{series['to']}", cheque_from="not in your cheque book")
    stopped = {n for r in db.rows("requests", user) if r["kind"] == "stop_cheque" for n in range(r["cheque_from"], r["cheque_to"] + 1)}
    if any(n in stopped for n in range(first, last + 1)):
        return _error("Some of these cheques are already stopped", cheque_from="already stopped")
    charge = _with_gst(STOP_CHEQUE_FEE)
    with db.transaction():
        problem = _debit_or_error(user, charge)
        if problem:
            return problem
        _post(user, amount=charge, direction="debit", narration=f"STOP PAYMENT CHGS CHQ {first}{'-' + str(last) if last != first else ''} INCL GST--",
              category="charges", counterparty="Stop payment charges", channel="charges")
        req = _request(user, "stop_cheque", f"Stop payment of cheque{'s' if last != first else ''} {first}{'–' + str(last) if last != first else ''} ({STOP_REASONS[reason]})",
                       charge=charge, extra={"cheque_from": first, "cheque_to": last})
    return {"request": req, "message": f"Payment stopped for cheque{'s' if last != first else ''} {first}{'–' + str(last) if last != first else ''}; {rupees(charge)} charged."}


def get_debit_card() -> dict[str, Any]:
    user = current_user()
    card = db.get("cards", user, "CARD-01")
    replacement = next((c for c in db.rows("cards", user) if c["id"] != "CARD-01" and c["status"] != "blocked"), None)
    return {"card": card, "replacement": replacement, "limits_max": CARD_LIMITS_MAX}


def block_debit_card(reason: str, reissue: bool = True) -> dict[str, Any]:
    user = current_user()
    if reason not in BLOCK_REASONS:
        return _error(f"reason must be one of: {', '.join(BLOCK_REASONS)}", reason="unknown")
    card = next((c for c in db.rows("cards", user) if c["status"] == "active"), None)
    if card is None:
        return _error("You have no active debit card to block")
    with db.transaction():
        card["status"] = "blocked"
        card["blocked_reason"] = BLOCK_REASONS[reason]
        db.put("cards", card)
        fee = 0
        req_extra = ""
        if _bool(reissue):
            fee = 0 if reason == "damaged" else _with_gst(CARD_REISSUE_FEE)
            if fee:
                _post(user, amount=fee, direction="debit", narration="DEBIT CARD REISSUE CHGS INCL GST--", category="charges",
                      counterparty="Debit card replacement fee", channel="charges")
            new = {**DEBIT_CARD, "user_id": user, "id": _next_id("cards", user, "CARD-"), "number_masked": f"6078 XXXX XXXX {random.randint(1000, 9999)}",
                   "status": "dispatched", "linked_account": "SB-01", "expected_by": (_today() + timedelta(days=7)).isoformat()}
            db.put("cards", new)
            req_extra = f" A new card is on its way (arrives by {new['expected_by']}); {rupees(fee)} charged." if fee else f" A new card is on its way (arrives by {new['expected_by']}), free."
        req = _request(user, "block_card", f"Debit card {card['number_masked'][-4:]} blocked ({BLOCK_REASONS[reason]})", charge=fee)
    return {"request": req, "message": f"Debit card ••{card['number_masked'][-4:]} is blocked permanently.{req_extra}"
            + (" If someone used it, raise a complaint for each transaction within 3 days for zero liability." if reason in ("stolen", "suspected_misuse") else "")}


def update_debit_card_usage(atm_daily_limit: int | None = None, pos_daily_limit: int | None = None, international: bool | None = None) -> dict[str, Any]:
    user = current_user()
    card = next((c for c in db.rows("cards", user) if c["status"] == "active"), None)
    if card is None:
        return _error("You have no active debit card")
    changes = []
    for key, value in (("atm_daily_limit", atm_daily_limit), ("pos_daily_limit", pos_daily_limit)):
        if value in (None, ""):
            continue
        n = _int(value, key)
        if isinstance(n, dict):
            return n
        if not 0 <= n <= CARD_LIMITS_MAX[key]:
            return _error(f"{key.replace('_', ' ')} can be ₹0–{rupees(CARD_LIMITS_MAX[key])[1:]}", **{key: "out of range"})
        card[key] = n
        changes.append(f"{'ATM' if key.startswith('atm') else 'Shop & online'} limit {rupees(n)} a day")
    if international not in (None, ""):
        card["international"] = _bool(international)
        changes.append("international use " + ("on" if card["international"] else "off"))
    if not changes:
        return _error("Nothing to change")
    db.put("cards", card)
    _request(user, "card_limits", "Debit card: " + ", ".join(changes))
    return {"card": card, "message": "Debit card updated: " + ", ".join(changes) + "."}


def submit_kyc_declaration(address_changed: bool = False, new_address: str | None = None) -> dict[str, Any]:
    user = current_user()
    cust = _customer(user)
    changed = _bool(address_changed)
    if changed and not str(new_address or "").strip():
        return _error("Give the new address", new_address="required")
    with db.transaction():
        if not changed:
            cust["kyc_last_updated"] = _today().isoformat()
            req = _request(user, "re_kyc", "Re-KYC self-declaration: no change in details")
            message = f"Re-KYC done. Next due {_kyc_status(cust)['due_date']}."
        else:
            req = _request(user, "re_kyc", f"Re-KYC with new address: {str(new_address).strip()[:120]}", eta_days=90,
                           extra={"next_step": "Show proof of the new address (Aadhaar, passport, utility bill under 2 months old) at any branch within 90 days"})
            cust["pending_address"] = str(new_address).strip()
            cust["kyc_last_updated"] = _today().isoformat()
            message = "Re-KYC recorded with your new address. Show proof of the new address at any branch within 90 days to complete it."
        cust.setdefault("kyc_declarations", []).append({"date": _today().isoformat(), "address_changed": changed})
        db.put("customers", cust)
    return {"request": req, "kyc": _kyc_status(cust), "message": message}


def get_interest_certificate(financial_year: str | None = None) -> dict[str, Any]:
    user = current_user()
    cust = _customer(user)
    if financial_year:
        m = re.fullmatch(r"(\d{4})-(\d{2})", financial_year.strip())
        if not m:
            return _error("financial_year looks like 2025-26", financial_year="like 2025-26")
        start = date(int(m.group(1)), 4, 1)
    else:
        start = _fy()[0]
    end = date(start.year + 1, 3, 31)
    label = f"{start.year}-{str(start.year + 1)[2:]}"
    upto = min(end, _today())
    sb_interest = sum(t["amount"] for t in db.rows("transactions", user)
                      if t["category"] == "interest" and start <= date.fromisoformat(t["date"]) <= upto)
    rows = []
    for dep in db.rows("deposits", user):
        opened = date.fromisoformat(dep["opened"])
        a = max(start, opened)
        b = min(upto, date.fromisoformat(dep["maturity"]), date.fromisoformat(dep.get("closed", upto.isoformat())))
        if b <= a:
            continue
        accrued = _deposit_value(dep, b) - _deposit_value(dep, a)
        if dep["kind"] == "rd":
            accrued = max(0, accrued - dep["monthly"] * len([i for i in range(dep["installments_paid"]) if a <= add_months(opened, i) <= b]))
        rows.append({"deposit": dep["id"], "scheme": dep["scheme"], "interest": max(0, accrued)})
    deposit_interest = sum(r["interest"] for r in rows)
    senior = _age(cust["dob"]) >= 60
    threshold = TDS_THRESHOLD["senior" if senior else "general"]
    projected = deposit_interest * (365 / max(1, (upto - start).days + 1)) if upto < end else deposit_interest
    tds = int(deposit_interest * TDS_RATE / 100) if projected > threshold else 0
    return {"financial_year": label, "period": f"{start.isoformat()} to {upto.isoformat()}" + (" (so far)" if upto < end else ""),
            "savings_interest": sb_interest, "deposit_interest": rows, "deposit_interest_total": deposit_interest,
            "tds_deducted_or_due": tds, "tds_threshold": threshold, "projected_deposit_interest_full_year": int(projected),
            "deduction_80tta": min(sb_interest, 10000) if not senior else 0,
            "notes": [f"Savings interest up to ₹10,000 is deductible under 80TTA (old regime).",
                      f"TDS of {TDS_RATE}% applies when deposit interest for the year is above {rupees(threshold)}; Form 15G/15H avoids it only if your total income is below the taxable limit — not your case on a ₹{cust['net_monthly_income'] * 12:,} salary.",
                      "Tax saver FD interest is taxable; only the deposit qualifies under 80C."]}


def raise_complaint(category: str, description: str, transaction_id: str | None = None) -> dict[str, Any]:
    user = current_user()
    if category not in COMPLAINT_CATEGORIES:
        return _error(f"category must be one of: {', '.join(COMPLAINT_CATEGORIES)}", category="unknown")
    text = " ".join(str(description).split())
    if len(text) < 10:
        return _error("Describe what happened in a sentence or two", description="too short")
    txn = None
    if transaction_id:
        txn = get_transaction(transaction_id)
        if "error" in txn:
            return _error(f"No transaction {transaction_id}", transaction_id="not found")
    label, tat = COMPLAINT_CATEGORIES[category]
    complaint = {"user_id": user, "id": _next_id("complaints", user, "CMP-", 4), "category": category, "category_label": label,
                 "description": text[:1000], "transaction_id": txn["transaction"]["id"] if txn else None,
                 "amount": txn["transaction"]["amount"] if txn else None, "raised": _today().isoformat(), "status": "Registered",
                 "resolve_by": (_today() + timedelta(days=tat)).isoformat(), "docket": "VNB" + _ref()[:9],
                 "escalation": "If unresolved by the date or you disagree: the bank's Principal Nodal Officer, then the RBI Ombudsman (cms.rbi.org.in) after 30 days."}
    db.put("complaints", complaint)
    return {"complaint": complaint, "message": f"Complaint {complaint['id']} registered (docket {complaint['docket']}); resolution by {complaint['resolve_by']}."}


def list_service_requests() -> dict[str, Any]:
    user = current_user()
    return {"requests": list(reversed(db.rows("requests", user))), "complaints": list(reversed(db.rows("complaints", user))),
            "enrolments": db.rows("enrolments", user)}


def describe_bank_rules() -> dict[str, Any]:
    return {
        "bank": BANK,
        "transfers": {"modes": MODES, "daily_limit_to_beneficiaries": DAILY_THIRD_PARTY_LIMIT, "beneficiary_cooling_hours": COOLING_HOURS,
                      "max_limit_per_beneficiary": BENEFICIARY_MAX_LIMIT, "charges": "No charges for NEFT, RTGS or IMPS through net banking"},
        "deposits": get_deposit_rates(),
        "loans": {pid: {"name": p["name"], "rates_by_cibil": p.get("rates"), "processing": p["processing"], "max_tenure_months": p["max_tenure_months"]}
                  for pid, p in LOAN_PRODUCTS.items()},
        "charges": {"cheque_book": f"First {CHEQUE_FREE_LEAVES_PER_FY} leaves a financial year free, then ₹{CHEQUE_CHARGE_PER_LEAF} a leaf + GST",
                    "stop_cheque": f"₹{STOP_CHEQUE_FEE} + GST per instruction", "debit_card_annual": "₹200 + GST", "debit_card_reissue": f"₹{CARD_REISSUE_FEE} + GST (free if damaged)",
                    "sms_alerts": "₹15 a quarter incl. GST", "declined_at_other_bank_atm": "₹500 + GST (insufficient balance)",
                    "free_atm_withdrawals": "5 a month at VNB ATMs, 3 at other banks' ATMs in metros (5 elsewhere); then ₹21 + GST"},
        "kyc": "Re-KYC every 10 years (low risk), 8 (medium), 2 (high). No change: self-declaration online. Changed address: declare online, show proof at a branch.",
        "complaints": {k: {"label": v[0], "resolve_within_days": v[1]} for k, v in COMPLAINT_CATEGORIES.items()},
        "categories": CATEGORIES,
        "channels": CHANNELS,
    }
