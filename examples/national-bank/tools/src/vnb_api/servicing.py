"""Account servicing: nominees, Positive Pay for high-value cheques, cheque status and Form 15G/15H.
Same conventions as ``logic.py``: whole rupees, IST, everything for ``current_user()``."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from vnb_api import db
from vnb_api.logic import (
    _age,
    _amount,
    _customer,
    _error,
    _fy,
    _int,
    _next_id,
    _parse_date,
    _request,
    _today,
    current_user,
    rupees,
    transactional_account,
)
from vnb_api.products import RELATIONS

POSITIVE_PAY_MIN = 50000  # optional from ₹50,000; banks may make it mandatory at ₹5 lakh
POSITIVE_PAY_MANDATORY = 500000
BASIC_EXEMPTION = {"general": 250000, "senior": 300000}


# ---------------------------------------------------------------- nominees


def _nominee_targets(user: str) -> list[tuple[str, str, dict[str, Any], str]]:
    """(id, label, row, kind) for everything that can carry a nominee."""
    out: list[tuple[str, str, dict[str, Any], str]] = []
    for a in db.rows("accounts", user):
        if a["status"] == "active" and a["kind"] in ("savings", "current", "ppf"):
            out.append((a["id"], a.get("product_name") or a.get("name", a["id"]), a, "accounts"))
    for d in db.rows("deposits", user):
        if d["status"] == "active":
            out.append((d["id"], d["scheme"], d, "deposits"))
    return out


def list_nominees() -> dict[str, Any]:
    user = current_user()
    rows = [{"account_id": i, "account": label, "nominee": row.get("nominee") or "Not registered"} for i, label, row, _ in _nominee_targets(user)]
    missing = [r["account_id"] for r in rows if r["nominee"] == "Not registered"]
    return {"nominees": rows, "without_nominee": missing,
            "note": "A nominee receives the money if the account holder dies, without a succession certificate. Each account and deposit has its own."}


def update_nominee(account_id: str, nominee_name: str, nominee_relation: str, nominee_dob: str, guardian_name: str = "") -> dict[str, Any]:
    user = current_user()
    key = account_id.strip().upper()
    target = next(((i, label, row, kind) for i, label, row, kind in _nominee_targets(user) if i == key), None)
    if target is None:
        return _error(f"not_found: no account or deposit {account_id}")
    if nominee_relation not in RELATIONS:
        return _error(f"Relation must be one of: {', '.join(RELATIONS)}", nominee_relation="unknown")
    if not nominee_name.strip():
        return _error("Give the nominee's name", nominee_name="required")
    born = _parse_date(nominee_dob, "nominee_dob")
    if isinstance(born, dict):
        return born
    minor = _age(born.isoformat()) < 18
    if minor and not guardian_name.strip():
        return _error("The nominee is a minor: give a guardian who will receive the money on their behalf", guardian_name="required for a minor")
    _, label, row, kind = target
    row["nominee"] = f"{nominee_name.strip()} ({nominee_relation})" + (f", minor — guardian {guardian_name.strip()}" if minor else "")
    db.put(kind, row)
    req = _request(user, "nominee", f"Nominee for {key} ({label}): {row['nominee']}")
    return {"account_id": key, "nominee": row["nominee"], "request": req, "message": f"Nominee for {label} ({key}) is now {row['nominee']}. Acknowledgement sent by SMS."}


# ---------------------------------------------------------------- cheques


def _issued_cheques(user: str) -> list[tuple[str, dict[str, Any]]]:
    return [(a["id"], a["cheque_series"]) for a in db.rows("accounts", user) if a.get("cheque_series") and a["status"] == "active"]


def get_cheque_status(cheque_number: int) -> dict[str, Any]:
    user = current_user()
    n = _int(cheque_number, "cheque_number")
    if isinstance(n, dict):
        return n
    for account_id, series in _issued_cheques(user):
        if series["from"] <= n <= series["to"]:
            stopped = any(r["kind"] == "stop_cheque" and r["cheque_from"] <= n <= r["cheque_to"] for r in db.rows("requests", user))
            pp = next((p for p in db.rows("positive_pay", user) if p["cheque_number"] == n), None)
            if stopped:
                status = "Stopped (stop payment instruction)"
            elif n <= series["used_to"]:
                status = "Paid (cleared before the current statement period)"
            elif pp:
                status = f"Not presented yet — Positive Pay registered for {rupees(pp['amount'])} to {pp['payee']}"
            else:
                status = "Not presented yet (unused leaf)"
            return {"cheque_number": n, "account_id": account_id, "status": status, "positive_pay": pp}
    return _error(f"Cheque {n} is not from your cheque books", cheque_number="not yours")


def register_positive_pay(cheque_number: int, cheque_date: str, amount: int, payee_name: str) -> dict[str, Any]:
    user = current_user()
    n = _int(cheque_number, "cheque_number")
    if isinstance(n, dict):
        return n
    status = get_cheque_status(n)
    if "error" in status:
        return status
    if not status["status"].startswith("Not presented"):
        return _error(f"Cheque {n} is {status['status'].split(' (')[0].lower()}", cheque_number="not usable")
    if status["positive_pay"]:
        return _error(f"Positive Pay is already registered for cheque {n}", cheque_number="already registered")
    value = _amount(amount)
    if isinstance(value, dict):
        return value
    if value < POSITIVE_PAY_MIN:
        return _error(f"Positive Pay is for cheques of {rupees(POSITIVE_PAY_MIN)} and above", amount="below ₹50,000")
    when = _parse_date(cheque_date, "cheque_date")
    if isinstance(when, dict):
        return when
    if when < _today() - timedelta(days=90) or when > _today() + timedelta(days=90):
        return _error("Cheque date must be within 3 months (a cheque is valid for 3 months)", cheque_date="out of range")
    if not payee_name.strip():
        return _error("Give the payee's name as written on the cheque", payee_name="required")
    row = {"user_id": user, "id": _next_id("positive_pay", user, "PP-"), "cheque_number": n, "account_id": status["account_id"], "date": when.isoformat(),
           "amount": value, "payee": payee_name.strip().upper(), "registered": _today().isoformat()}
    db.put("positive_pay", row)
    _request(user, "positive_pay", f"Positive Pay: cheque {n}, {rupees(value)} to {row['payee']}")
    return {"positive_pay": row, "message": f"Positive Pay registered: cheque {n} dated {when.isoformat()} for {rupees(value)} to {row['payee']}. "
                                            "If a cheque presented differs, it will be returned."
                                            + (" (Mandatory at this amount.)" if value >= POSITIVE_PAY_MANDATORY else "")}


# ---------------------------------------------------------------- Form 15G / 15H


def submit_form_15g_15h(financial_year: str | None = None, estimated_total_income: int | None = None) -> dict[str, Any]:
    user = current_user()
    cust = _customer(user)
    senior = _age(cust["dob"]) >= 60
    form = "15H" if senior else "15G"
    fy = financial_year or _fy()[2]
    income = int(estimated_total_income) if estimated_total_income not in (None, "") else cust["net_monthly_income"] * 12
    limit = BASIC_EXEMPTION["senior" if senior else "general"]
    if income > limit:
        return _error(f"Form {form} is only for people whose total income is below the taxable limit ({rupees(limit)}). Your income of about {rupees(income)} "
                      "is taxable, so a declaration would be false (an offence under section 277). TDS on deposits is adjusted against your tax when you file.",
                      estimated_total_income="above the taxable limit")
    req = _request(user, "form_15g_15h", f"Form {form} for FY {fy}")
    return {"request": req, "message": f"Form {form} for FY {fy} submitted; no TDS will be deducted on your deposits this year."}
