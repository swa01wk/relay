"""Payments beyond beneficiary transfers: between own accounts, bills (BBPS) with autopay, standing
instructions, income-tax challans and the customer's own daily transfer limit. Same conventions as
``logic.py``: whole rupees, IST, everything for ``current_user()``."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from vnb_api import db
from vnb_api.logic import (
    BENEFICIARY_MAX_LIMIT,
    DAILY_THIRD_PARTY_LIMIT,
    _amount,
    _bool,
    _customer,
    _debit_or_error,
    _error,
    _find_beneficiary,
    _ben_status,
    _int,
    _next_id,
    _parse_date,
    _post,
    _ref,
    _today,
    current_user,
    daily_limit,
    get_interest_certificate,
    rupees,
    transactional_account,
)
from vnb_api.seeds import ADVANCE_TAX_DUE, BILLER_CATEGORIES, BILLER_PROVIDERS, MOBILE_PLANS, PREPAID_CATEGORIES, add_months

MIN_DAILY_LIMIT = 10000

# ---------------------------------------------------------------- own accounts


def transfer_between_own_accounts(from_account: str, to_account: str, amount: int, remarks: str = "") -> dict[str, Any]:
    user = current_user()
    src = transactional_account(user, from_account)
    dst = transactional_account(user, to_account)
    if src is None or dst is None:
        return _error("Both must be your open savings or current accounts (like SB-01, SB-02)", to_account="not your account")
    if src["id"] == dst["id"]:
        return _error("Choose two different accounts", to_account="same as from")
    value = _amount(amount)
    if isinstance(value, dict):
        return value
    with db.transaction():
        problem = _debit_or_error(user, value, src["id"])
        if problem:
            return problem
        note = "".join(c for c in remarks if c.isalnum() or c == " ")[:20]
        out = _post(user, amount=value, direction="debit", narration=f"TO TRANSFER-INB OWN A/C {dst['number']} {note}--".replace("  ", " "),
                    category="transfer", counterparty=f"Own account {dst['id']}", channel="intra_bank", account_id=src["id"])
        _post(user, amount=value, direction="credit", narration=f"BY TRANSFER-INB OWN A/C {src['number']} {note}--".replace("  ", " "),
              category="transfer", counterparty=f"Own account {src['id']}", channel="intra_bank", account_id=dst["id"])
    return {"transfer": {"reference": out["ref"], "amount": value, "from": src["id"], "to": dst["id"]},
            "message": f"{rupees(value)} moved from {src['id']} to {dst['id']} (ref {out['ref']})."}


# ---------------------------------------------------------------- bills


def _biller(user: str, text: str) -> dict[str, Any] | None:
    t = str(text).strip().lower()
    for b in db.rows("billers", user):
        if t in (b["id"].lower(), b["consumer_number"].lower(), (b.get("nickname") or "").lower(), b["category"]) or (len(t) >= 3 and t in b["provider"].lower()):
            return b
    return None


def _biller_view(b: dict[str, Any]) -> dict[str, Any]:
    view = {k: b.get(k) for k in ("id", "category", "provider", "consumer_number", "nickname", "bill", "plan", "validity_till", "balance", "autopay", "last_paid")}
    view["category_label"] = BILLER_CATEGORIES[b["category"]]
    view["prepaid"] = b["category"] in PREPAID_CATEGORIES
    if b.get("bill"):
        view["days_to_due"] = (date.fromisoformat(b["bill"]["due"]) - _today()).days
    return view


def list_billers() -> dict[str, Any]:
    user = current_user()
    billers = [_biller_view(b) for b in db.rows("billers", user)]
    due = [b for b in billers if b.get("bill")]
    return {"billers": billers, "total_due": sum(b["bill"]["amount"] for b in due), "categories": BILLER_CATEGORIES,
            "providers": BILLER_PROVIDERS, "mobile_plans": MOBILE_PLANS}


def add_biller(category: str, provider: str, consumer_number: str, nickname: str = "") -> dict[str, Any]:
    user = current_user()
    if category not in BILLER_CATEGORIES:
        return _error(f"category must be one of: {', '.join(BILLER_CATEGORIES)}", category="unknown")
    if provider not in BILLER_PROVIDERS[category]:
        return _error(f"For {BILLER_CATEGORIES[category]} choose: {', '.join(BILLER_PROVIDERS[category])}", provider="not a registered biller")
    number = str(consumer_number).strip()
    if len(number) < 4:
        return _error("Give the consumer / account number printed on the bill", consumer_number="too short")
    if any(b["provider"] == provider and b["consumer_number"] == number for b in db.rows("billers", user)):
        return _error("This biller is already registered", consumer_number="already registered")
    biller = {"user_id": user, "id": _next_id("billers", user, "BLR-"), "category": category, "provider": provider, "consumer_number": number,
              "nickname": nickname.strip(), "autopay": None}
    if category not in PREPAID_CATEGORIES:
        # BBPS fetches the latest bill on registration (made up for the demo).
        biller["bill"] = {"amount": 450 + (sum(map(ord, number)) % 23) * 85, "due": (_today() + timedelta(days=9)).isoformat(),
                          "period": _today().strftime("%b %Y")}
    db.put("billers", biller)
    return {"biller": _biller_view(biller), "message": f"{provider} ({number}) registered." + (" Latest bill fetched." if biller.get("bill") else "")}


def pay_bill(biller_id: str, amount: int | None = None, from_account: str = "SB-01") -> dict[str, Any]:
    user = current_user()
    biller = _biller(user, biller_id)
    if biller is None:
        return _error(f"not_found: no registered biller {biller_id} — register it first", biller_id="not registered")
    account = transactional_account(user, from_account)
    if account is None:
        return _error("Pay from an open savings or current account", from_account="not your account")
    prepaid = biller["category"] in PREPAID_CATEGORIES
    if amount in (None, ""):
        if prepaid:
            return _error("Choose the recharge amount" + (f" (plans: {', '.join(rupees(p) for p in MOBILE_PLANS)})" if biller["category"] == "mobile_prepaid" else ""),
                          amount="required")
        if not biller.get("bill"):
            return _error("No bill is due for this biller", amount="nothing due")
        value: int | dict[str, Any] = biller["bill"]["amount"]
    else:
        value = _amount(amount)
    if isinstance(value, dict):
        return value
    if biller["category"] == "mobile_prepaid" and value not in MOBILE_PLANS:
        return _error(f"Telco prepaid plans: {', '.join(rupees(p) for p in MOBILE_PLANS)}", amount="not a plan")
    with db.transaction():
        problem = _debit_or_error(user, value, account["id"])
        if problem:
            return problem
        ref = "BBPS" + _ref()[:10]
        txn = _post(user, amount=value, direction="debit", narration=f"TO TRANSFER-BBPS/{biller['provider'].upper()[:22]}/{biller['consumer_number']}/{ref}--",
                    category="utilities" if biller["category"] not in ("insurance", "education_fee", "municipal_tax") else
                    {"insurance": "insurance", "education_fee": "education", "municipal_tax": "utilities"}[biller["category"]],
                    counterparty=f"{biller['provider']} ({BILLER_CATEGORIES[biller['category']]})", channel="bill_pay", account_id=account["id"])
        note = ""
        if prepaid:
            if biller["category"] == "fastag":
                biller["balance"] = biller.get("balance", 0) + value
                note = f" FASTag balance now {rupees(biller['balance'])}."
            else:
                biller["validity_till"] = (max(_today(), date.fromisoformat(biller.get("validity_till") or _today().isoformat())) + timedelta(days=28)).isoformat()
                biller["plan"] = value
                note = f" Valid till {biller['validity_till']}."
        elif biller.get("bill"):
            left = biller["bill"]["amount"] - value
            biller["bill"] = {**biller["bill"], "amount": left} if left > 0 else None
            note = f" {rupees(left)} still due." if left > 0 else ""
        biller["last_paid"] = {"amount": value, "date": _today().isoformat(), "ref": ref}
        db.put("billers", biller)
    return {"payment": {"reference": ref, "amount": value, "biller": biller["provider"], "transaction_id": txn["id"]},
            "message": f"Paid {rupees(value)} to {biller['provider']} ({biller['consumer_number']}), BBPS ref {ref}.{note}"}


def set_bill_autopay(biller_id: str, enabled: bool, max_amount: int | None = None, from_account: str = "SB-01") -> dict[str, Any]:
    user = current_user()
    biller = _biller(user, biller_id)
    if biller is None:
        return _error(f"not_found: no registered biller {biller_id}")
    if biller["category"] in PREPAID_CATEGORIES:
        return _error("Autopay is for postpaid bills; for a recharge set a standing instruction instead", biller_id="prepaid")
    on = _bool(enabled)
    if on:
        cap = _amount(max_amount or 0, "max_amount") if max_amount else (biller.get("bill") or {}).get("amount", 0) * 2 or 5000
        if isinstance(cap, dict):
            return cap
        if transactional_account(user, from_account) is None:
            return _error("Autopay must debit an open savings or current account", from_account="not your account")
        biller["autopay"] = {"max_amount": cap, "from_account": from_account.upper(), "since": _today().isoformat()}
        message = f"Autopay on for {biller['provider']}: bills up to {rupees(cap)} are paid on the due date from {from_account.upper()}; above that you get an SMS to pay yourself."
    else:
        biller["autopay"] = None
        message = f"Autopay off for {biller['provider']}."
    db.put("billers", biller)
    return {"biller": _biller_view(biller), "message": message}


# ---------------------------------------------------------------- standing instructions


def _si_view(si: dict[str, Any]) -> dict[str, Any]:
    today = _today()
    nxt = today.replace(day=min(si["day"], 28))
    if nxt <= today:
        nxt = add_months(nxt, 1)
    return {**{k: si.get(k) for k in ("id", "to_kind", "to", "to_label", "amount", "day", "from_account", "start", "end", "remarks", "status", "system")},
            "next_on": nxt.isoformat() if si["status"] == "active" else None}


def list_standing_instructions() -> dict[str, Any]:
    user = current_user()
    rows = [_si_view(s) for s in db.rows("standing", user)]
    return {"standing_instructions": rows, "monthly_total": sum(s["amount"] for s in rows if s["status"] == "active")}


def create_standing_instruction(to: str, amount: int, day_of_month: int, from_account: str = "SB-01", start_date: str | None = None,
                                installments: int | None = None, remarks: str = "") -> dict[str, Any]:
    user = current_user()
    value = _amount(amount)
    if isinstance(value, dict):
        return value
    day = _int(day_of_month, "day_of_month")
    if isinstance(day, dict):
        return day
    if not 1 <= day <= 28:
        return _error("Day of month must be 1–28", day_of_month="1–28")
    src = transactional_account(user, from_account)
    if src is None:
        return _error("Debit an open savings or current account", from_account="not your account")
    target = str(to).strip()
    own = transactional_account(user, target)
    if own is not None:
        if own["id"] == src["id"]:
            return _error("Choose a different account to credit", to="same account")
        kind, to_id, label = "own_account", own["id"], f"Own account {own['id']}"
    else:
        ben = _find_beneficiary(user, target)
        if ben is None:
            return _error(f"No beneficiary or own account {to} — add the beneficiary first", to="not found")
        if value > ben["limit"]:
            return _error(f"More than {ben['name']}'s limit of {rupees(ben['limit'])}", amount="over the beneficiary limit")
        kind, to_id, label = "beneficiary", ben["id"], f"{ben['name']} ({ben.get('nickname') or ben['bank']})"
        if _ben_status(ben)["status"] == "cooling":
            label += " — first payment after the cooling period"
    start = _today() + timedelta(days=1)
    if start_date:
        parsed = _parse_date(start_date, "start_date")
        if isinstance(parsed, dict):
            return parsed
        if parsed <= _today():
            return _error("Start date must be in the future", start_date="must be after today")
        start = parsed
    end = None
    if installments not in (None, ""):
        n = _int(installments, "installments")
        if isinstance(n, dict):
            return n
        if not 1 <= n <= 120:
            return _error("Instalments must be 1–120", installments="1–120")
        end = add_months(start.replace(day=day) if start.day <= day else add_months(start.replace(day=day), 1), n - 1).isoformat()
    si = {"user_id": user, "id": _next_id("standing", user, "SI-"), "to_kind": kind, "to": to_id, "to_label": label, "amount": value, "day": day,
          "from_account": src["id"], "start": start.isoformat(), "end": end, "remarks": remarks.strip()[:30], "status": "active"}
    db.put("standing", si)
    return {"standing_instruction": _si_view(si),
            "message": f"Standing instruction {si['id']}: {rupees(value)} to {label} on the {day} of every month from {start.isoformat()}"
                       + (f" until {end}" if end else " until you cancel") + "."}


def cancel_standing_instruction(standing_instruction_id: str) -> dict[str, Any]:
    user = current_user()
    si = db.get("standing", user, standing_instruction_id.strip().upper())
    if si is None or si["status"] != "active":
        return _error(f"not_found: no active standing instruction {standing_instruction_id}")
    if si.get("system"):
        return _error("RD instalments stop only when the RD is closed", standing_instruction_id="linked to a deposit")
    si["status"] = "cancelled"
    si["cancelled"] = _today().isoformat()
    db.put("standing", si)
    return {"standing_instruction": _si_view(si), "message": f"{si['id']} to {si['to_label']} cancelled; no more debits."}


# ---------------------------------------------------------------- transfer limit


def set_transfer_limit(daily_limit_amount: int) -> dict[str, Any]:
    user = current_user()
    value = _amount(daily_limit_amount, "daily_limit_amount")
    if isinstance(value, dict):
        return value
    if not MIN_DAILY_LIMIT <= value <= DAILY_THIRD_PARTY_LIMIT:
        return _error(f"The daily limit can be {rupees(MIN_DAILY_LIMIT)}–{rupees(DAILY_THIRD_PARTY_LIMIT)}", daily_limit_amount="out of range")
    cust = _customer(user)
    old = daily_limit(user)
    cust["daily_transfer_limit"] = value
    db.put("customers", cust)
    lowered = value < old
    return {"daily_limit": value, "previous": old,
            "message": f"Daily transfer limit {'lowered' if lowered else 'raised'} to {rupees(value)}" + ("." if lowered else
                       " (a higher limit applies after 4 hours, like a new beneficiary).") + f" Per-beneficiary limits (up to {rupees(BENEFICIARY_MAX_LIMIT)}) still apply."}


# ---------------------------------------------------------------- income tax (challan ITNS 280)

TAX_TYPES = {"advance_tax": ("100", "Advance tax"), "self_assessment": ("300", "Self-assessment tax")}


def _assessment_year() -> str:
    t = _today()
    start = t.year if t.month >= 4 else t.year - 1  # the financial year now running
    return f"{start + 1}-{str(start + 2)[2:]}"


def get_tax_payment_guide() -> dict[str, Any]:
    """Whether the customer needs to pay advance tax, and the due dates."""
    user = current_user()
    cust = _customer(user)
    cert = get_interest_certificate()
    other_income = cert["projected_deposit_interest_full_year"] + cert["savings_interest"] - cert["deduction_80tta"]
    tax_on_it = int(other_income * cust["income_tax_slab_percent"] / 100 * 1.04)
    tds = cert["tds_deducted_or_due"]
    needed = tax_on_it - tds > 10000
    t = _today()
    fy_start = t.year if t.month >= 4 else t.year - 1
    dues = []
    for md, pct in ADVANCE_TAX_DUE:
        year = fy_start if int(md[:2]) >= 4 else fy_start + 1
        dues.append({"due": f"{year}-{md}", "cumulative_percent": pct})
    return {"assessment_year": _assessment_year(), "salary_tds": "Your employer deducts tax on your salary (TDS).",
            "other_income_estimate": other_income, "tax_on_other_income": tax_on_it, "tds_on_deposits": tds,
            "advance_tax_needed": needed,
            "advice": ("Advance tax is needed only if tax not covered by TDS is above ₹10,000 for the year. "
                       + ("Yours is above that — pay by the due dates below to avoid interest (234B/234C)." if needed else
                          f"Yours is about {rupees(max(0, tax_on_it - tds))}, so no advance tax is needed; pay it as self-assessment tax before filing your return.")),
            "due_dates": dues, "how": "Pay through Tax Payments: challan ITNS 280, code 100 (advance) or 300 (self-assessment)."}


def pay_tax(tax_type: str, amount: int, assessment_year: str | None = None, from_account: str = "SB-01") -> dict[str, Any]:
    user = current_user()
    if tax_type not in TAX_TYPES:
        return _error("tax_type must be advance_tax or self_assessment", tax_type="unknown")
    value = _amount(amount)
    if isinstance(value, dict):
        return value
    ay = (assessment_year or _assessment_year()).strip()
    if len(ay) != 7 or ay[4] != "-":
        return _error("Assessment year looks like 2027-28", assessment_year="like 2027-28")
    account = transactional_account(user, from_account)
    if account is None:
        return _error("Pay from an open savings or current account", from_account="not your account")
    code, label = TAX_TYPES[tax_type]
    cust = _customer(user)
    with db.transaction():
        problem = _debit_or_error(user, value, account["id"])
        if problem:
            return problem
        bsr = "0451209"
        serial = str(len(db.rows("tax_payments", user)) + 10231)
        cin = f"{bsr}{_today().strftime('%d%m%y')}{serial}"
        _post(user, amount=value, direction="debit", narration=f"TO TRANSFER-OLTAS ITNS280/{code}/AY{ay}/CIN{cin}--", category="other",
              counterparty=f"Income tax — {label} (AY {ay})", channel="bill_pay", account_id=account["id"])
        payment = {"user_id": user, "id": _next_id("tax_payments", user, "TAX-"), "tax_type": tax_type, "label": label, "challan": "ITNS 280",
                   "minor_head": code, "assessment_year": ay, "pan": cust["pan"], "amount": value, "paid_on": _today().isoformat(), "cin": cin, "bsr_code": bsr}
        db.put("tax_payments", payment)
    return {"payment": payment, "message": f"{label} of {rupees(value)} paid for AY {ay}. CIN {cin} (BSR {bsr}) — quote it in your income-tax return."}


def list_tax_payments() -> dict[str, Any]:
    user = current_user()
    return {"tax_payments": list(reversed(db.rows("tax_payments", user)))}
