"""Products the customer can take up online: new savings / current accounts (and closing them),
VNB Mutual Fund (lumpsum, SIP, redemption), NPS and safe deposit lockers. Same conventions as
``logic.py``: whole rupees, IST, everything for ``current_user()``."""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from vnb_api import db
from vnb_api.logic import (
    _age,
    _amount,
    _bool,
    _customer,
    _debit_or_error,
    _error,
    _family_with_ages,
    _int,
    _next_id,
    _post,
    _ref,
    _request,
    _today,
    _with_gst,
    current_user,
    rupees,
    transactional_account,
)
from vnb_api.seeds import ACCOUNT_PRODUCTS, DEBIT_CARD, LOCKER_RULE, LOCKERS, MF_DISCLAIMER, MF_SCHEMES, NPS

RELATIONS = ("wife", "husband", "son", "daughter", "mother", "father", "brother", "sister")

# ---------------------------------------------------------------- savings / current accounts


def _daughter(user: str) -> dict[str, Any] | None:
    return next((m for m in _family_with_ages(_customer(user)) if m["relation"] == "daughter"), None)


def _eligibility(user: str, key: str) -> tuple[bool, str | None]:
    product = ACCOUNT_PRODUCTS[key]
    cust = _customer(user)
    age = _age(cust["dob"])
    accounts = [a for a in db.rows("accounts", user) if a["kind"] in ("savings", "current") and a["status"] == "active"]
    if key == "bsbd" and any(a["kind"] == "savings" for a in accounts):
        return False, "You already have a savings account here; a basic (BSBD) account can't be held with another savings account"
    if key == "salary":
        if any(a.get("product") == "salary" for a in accounts):
            return False, "Your account is already a salary package"
        if cust.get("employer_type") not in ("government", "private"):
            return False, "Only for salaried customers"
    if "min_age" in product and "daughter" not in product["holder"] and age < product["min_age"]:
        return False, f"Only for {product['min_age']}+ (you are {age})"
    if "daughter" in product["holder"]:
        child = _daughter(user)
        if child is None:
            return False, "Only for your minor child"
        if not product.get("min_age", 0) <= child["age"] < product["max_age"]:
            return False, f"For children aged {product.get('min_age', 0)}–{product['max_age'] - 1} ({child['name']} is {child['age']})"
        if any(a.get("holder") == child["name"] for a in accounts):
            return False, f"{child['name']} already has an account"
    return True, None


def list_account_products() -> dict[str, Any]:
    user = current_user()
    rows = []
    for key, p in ACCOUNT_PRODUCTS.items():
        ok, why = _eligibility(user, key)
        rows.append({"product": key, "name": p["name"], "kind": p["kind"], "for": p["for"], "interest_rate": p["rate"], "minimum_balance": p["minimum_balance"],
                     "features": p["features"], "charges": p["charges"], "rule": p.get("rule"), "eligible": ok, "why_not": why,
                     "holder": "your daughter" if "daughter" in p["holder"] else "you"})
    held = [{"id": a["id"], "product": a.get("product_name"), "holder": a.get("holder") or _customer(user)["name"]}
            for a in db.rows("accounts", user) if a["kind"] in ("savings", "current") and a["status"] == "active"]
    return {"products": rows, "you_hold": held,
            "documents": "Existing customers: no new KYC (your CIF is reused). A minor's account needs the child's birth certificate and Aadhaar at the branch within 30 days."}


def open_account(product: str, nominee_name: str = "", nominee_relation: str = "", initial_deposit: int | None = None, debit_card: bool = True,
                 cheque_book: bool = False, business_name: str = "") -> dict[str, Any]:
    user = current_user()
    if product not in ACCOUNT_PRODUCTS:
        return _error(f"product must be one of: {', '.join(ACCOUNT_PRODUCTS)}", product="unknown")
    ok, why = _eligibility(user, product)
    if not ok:
        return _error(why or "Not eligible", product="not eligible")
    p = ACCOUNT_PRODUCTS[product]
    cust = _customer(user)
    if p.get("converts_existing"):
        main = transactional_account(user, "SB-01")
        assert main is not None
        main.update({"product": product, "product_name": p["name"], "features": p["features"], "minimum_balance": p["minimum_balance"]})
        db.put("accounts", main)
        req = _request(user, "account_conversion", f"SB-01 converted to {p['name']}")
        return {"account": {k: main[k] for k in ("id", "number", "product_name", "features")}, "request": req,
                "message": f"Your account XXXXXXX{main['number'][-4:]} is now a {p['name']} — same account number. "
                           f"Benefits: {'; '.join(p['features'][:3])}."}
    if product == "current" and not business_name.strip():
        return _error("Give the name of the business", business_name="required")
    if nominee_relation and nominee_relation not in RELATIONS:
        return _error(f"Relation must be one of: {', '.join(RELATIONS)}", nominee_relation="unknown")
    deposit = 0
    if initial_deposit not in (None, "", 0):
        d = _amount(initial_deposit, "initial_deposit")
        if isinstance(d, dict):
            return d
        deposit = d
    if product == "current" and deposit < 10000:
        return _error("A current account needs ₹10,000 to start (average-balance requirement)", initial_deposit="at least ₹10,000")
    child = _daughter(user) if "daughter" in p["holder"] else None
    with db.transaction():
        if deposit:
            problem = _debit_or_error(user, deposit)
            if problem:
                return problem
        prefix = "CA-" if p["kind"] == "current" else "SB-"
        acc_id = _next_id("accounts", user, prefix)
        number = ("305" if p["kind"] == "current" else "302") + str(random.randint(10**10, 10**11 - 1))
        acc = {"user_id": user, "id": acc_id, "kind": p["kind"], "product": product, "product_name": p["name"], "name": p["name"], "number": number,
               "balance": 0, "lien": 0, "rate": p["rate"], "opened": _today().isoformat(), "status": "active",
               "mode": "Operated by guardian" if product == "minor" else "Single", "minimum_balance": p["minimum_balance"], "features": p["features"],
               "nominee": f"{nominee_name.strip()} ({nominee_relation})" if nominee_name.strip() else "Not registered",
               "holder": child["name"] if child else None, "guardian": cust["name"] if child else None,
               "business_name": business_name.strip() or None, "micr": "226017004"}
        if _bool(cheque_book) and product not in ("bsbd",):
            start = random.randint(600, 899) * 1000 + 1
            acc["cheque_series"] = {"from": start, "to": start + 24, "used_to": start - 1, "issued": _today().isoformat()}
        db.put("accounts", acc)
        if deposit:
            src = transactional_account(user, "SB-01")
            assert src is not None
            _post(user, amount=deposit, direction="debit", narration=f"TO TRANSFER-INB OWN A/C {number} OPENING--", category="transfer",
                  counterparty=f"Own account {acc_id} (opening deposit)", channel="intra_bank")
            _post(user, amount=deposit, direction="credit", narration=f"BY TRANSFER-INB OWN A/C {src['number']} OPENING--", category="transfer",
                  counterparty="Opening deposit from SB-01", channel="intra_bank", account_id=acc_id)
        card_note = ""
        if _bool(debit_card):
            limit = 5000 if product == "minor" else 2000 if product == "minor_self" else DEBIT_CARD["atm_daily_limit"]
            card = {**DEBIT_CARD, "user_id": user, "id": _next_id("cards", user, "CARD-"), "number_masked": f"6078 XXXX XXXX {random.randint(1000, 9999)}",
                    "status": "dispatched", "linked_account": acc_id, "atm_daily_limit": limit, "pos_daily_limit": limit if child else DEBIT_CARD["pos_daily_limit"],
                    "network": "RuPay Photo Card" if product == "minor" else DEBIT_CARD["network"], "expected_by": (_today() + timedelta(days=7)).isoformat()}
            db.put("cards", card)
            card_note = f" Debit card arrives by {card['expected_by']}."
        req = _request(user, "account_opening", f"{p['name']} {acc_id}" + (f" for {child['name']}" if child else ""), eta_days=30 if (child or product == "current") else 0)
    follow_up = {"minor": f" Bring {child['name'] if child else 'the child'}'s birth certificate and Aadhaar to the branch within 30 days.",
                 "minor_self": " Bring the child's birth certificate and Aadhaar to the branch within 30 days.",
                 "current": " Show proof of the business (shop registration, GST or Udyam) at the branch within 30 days."}.get(product, "")
    return {"account": {k: acc.get(k) for k in ("id", "number", "product_name", "holder", "guardian", "balance", "nominee")}, "request": req,
            "message": f"{p['name']} opened: A/c {number} ({acc_id}), IFSC {cust['ifsc']}" + (f", with {rupees(deposit)}" if deposit else "") + "."
                       + card_note + follow_up}


def close_account(account_id: str) -> dict[str, Any]:
    user = current_user()
    acc = transactional_account(user, account_id)
    if acc is None:
        return _error(f"not_found: no open savings or current account {account_id}")
    if acc["id"] == "SB-01":
        return _error("Your main account (salary, loan EMIs and deposits are linked to it) can be closed only at the branch", account_id="main account")
    if any(s["status"] == "active" and s["from_account"] == acc["id"] for s in db.rows("standing", user)):
        return _error("Cancel the standing instructions from this account first", account_id="has standing instructions")
    with db.transaction():
        balance = acc["balance"]
        if balance:
            main = transactional_account(user, "SB-01")
            assert main is not None
            _post(user, amount=balance, direction="debit", narration=f"TO TRANSFER-ACCOUNT CLOSURE TO {main['number']}--", category="transfer",
                  counterparty="Closure: balance moved to SB-01", channel="intra_bank", account_id=acc["id"])
            _post(user, amount=balance, direction="credit", narration=f"BY TRANSFER-ACCOUNT CLOSURE {acc['number']}--", category="transfer",
                  counterparty=f"Closure of {acc['id']}", channel="intra_bank")
        acc = db.get("accounts", user, acc["id"]) or acc
        acc["status"] = "closed"
        acc["closed"] = _today().isoformat()
        db.put("accounts", acc)
        for card in db.rows("cards", user):
            if card.get("linked_account") == acc["id"] and card["status"] != "blocked":
                card["status"] = "blocked"
                card["blocked_reason"] = "Account closed"
                db.put("cards", card)
        req = _request(user, "account_closure", f"{acc['product_name']} {acc['id']} closed")
    return {"request": req, "message": f"{acc['id']} closed. {rupees(balance)} moved to your main account; its debit card is blocked. Destroy unused cheque leaves."}


# ---------------------------------------------------------------- mutual funds


def list_mutual_funds() -> dict[str, Any]:
    return {"schemes": [{"scheme": k, **v} for k, v in MF_SCHEMES.items()], "disclaimer": MF_DISCLAIMER,
            "note": "Direct plans through VNB net banking; units are allotted at the day's NAV (illustrative NAVs here)."}


def _holding(user: str, scheme: str) -> dict[str, Any] | None:
    return next((h for h in db.rows("mf_holdings", user) if h["scheme"] == scheme), None)


def invest_in_mutual_fund(scheme: str, amount: int, mode: str = "lumpsum", sip_day: int | None = None, from_account: str = "SB-01") -> dict[str, Any]:
    user = current_user()
    if scheme not in MF_SCHEMES:
        return _error(f"scheme must be one of: {', '.join(MF_SCHEMES)}", scheme="unknown")
    s = MF_SCHEMES[scheme]
    value = _amount(amount)
    if isinstance(value, dict):
        return value
    if mode not in ("lumpsum", "sip"):
        return _error("mode must be lumpsum or sip", mode="unknown")
    minimum = s["min_sip"] if mode == "sip" else s["min_lumpsum"]
    if value < minimum:
        return _error(f"Minimum {'SIP instalment' if mode == 'sip' else 'investment'} is {rupees(minimum)}", amount=f"at least {rupees(minimum)}")
    day = None
    if mode == "sip":
        d = _int(sip_day or 5, "sip_day")
        if isinstance(d, dict):
            return d
        if not 1 <= d <= 28:
            return _error("SIP day must be 1–28", sip_day="1–28")
        day = d
    account = transactional_account(user, from_account)
    if account is None:
        return _error("Invest from an open savings or current account", from_account="not your account")
    with db.transaction():
        problem = _debit_or_error(user, value, account["id"])
        if problem:
            return problem
        units = round(value / s["nav"], 3)
        h = _holding(user, scheme) or {"user_id": user, "id": _next_id("mf_holdings", user, "MF-"), "scheme": scheme, "name": s["name"],
                                        "folio": "9" + _ref()[:9], "units": 0.0, "invested": 0, "lots": [], "sip": None}
        h["units"] = round(h["units"] + units, 3)
        h["invested"] += value
        h["lots"].append({"date": _today().isoformat(), "units": units, "amount": value})
        if mode == "sip":
            h["sip"] = {"amount": value, "day": day, "from_account": account["id"], "since": _today().isoformat()}
        db.put("mf_holdings", h)
        _post(user, amount=value, direction="debit", narration=f"TO TRANSFER-VNBMF/{h['folio']}/{scheme.upper()}/{'SIP' if mode == 'sip' else 'PUR'}--",
              category="savings_investment", counterparty=f"{s['name']} ({'SIP' if mode == 'sip' else 'purchase'})", channel="intra_bank", account_id=account["id"])
    lock = f" Each instalment is locked in for 3 years (ELSS)." if s["lock_in"] else ""
    return {"holding": _mf_view(h), "message": f"{rupees(value)} invested in {s['name']}: {units} units at NAV {s['nav']} (folio {h['folio']})."
            + (f" SIP of {rupees(value)} on the {day} of every month starts next month." if mode == "sip" else "") + lock + " " + MF_DISCLAIMER}


def _mf_view(h: dict[str, Any]) -> dict[str, Any]:
    s = MF_SCHEMES[h["scheme"]]
    value = round(h["units"] * s["nav"])
    locked = 0.0
    if s["lock_in"]:
        cutoff = _today() - timedelta(days=3 * 365)
        locked = sum(l["units"] for l in h["lots"] if date.fromisoformat(l["date"]) > cutoff)
    return {"id": h["id"], "scheme": h["scheme"], "name": h["name"], "folio": h["folio"], "units": h["units"], "nav": s["nav"], "value": value,
            "invested": h["invested"], "gain": value - h["invested"], "sip": h["sip"], "locked_units": round(locked, 3),
            "redeemable_value": round((h["units"] - locked) * s["nav"])}


def list_mf_holdings() -> dict[str, Any]:
    user = current_user()
    rows = [_mf_view(h) for h in db.rows("mf_holdings", user) if h["units"] > 0 or h["sip"]]
    return {"holdings": rows, "total_value": sum(r["value"] for r in rows), "disclaimer": MF_DISCLAIMER}


def redeem_mutual_fund(scheme: str, amount: int | None = None, stop_sip: bool = False) -> dict[str, Any]:
    user = current_user()
    h = _holding(user, scheme)
    if h is None:
        return _error(f"not_found: you hold no units of {scheme}")
    view = _mf_view(h)
    if _bool(stop_sip) and amount in (None, "", 0):
        h["sip"] = None
        db.put("mf_holdings", h)
        return {"holding": _mf_view(h), "message": f"SIP in {h['name']} stopped. Your units stay invested."}
    value = view["redeemable_value"] if amount in (None, "", 0) else _amount(amount)
    if isinstance(value, dict):
        return value
    if value <= 0:
        return _error("All your units are still in the ELSS 3-year lock-in", amount="locked in")
    if value > view["redeemable_value"]:
        return _error(f"You can redeem up to {rupees(view['redeemable_value'])} now" + (" (the rest is in the 3-year lock-in)" if view["locked_units"] else ""),
                      amount="more than redeemable")
    s = MF_SCHEMES[scheme]
    units = round(value / s["nav"], 3)
    with db.transaction():
        h["units"] = round(h["units"] - units, 3)
        h["invested"] = max(0, round(h["invested"] * (h["units"] / (h["units"] + units)))) if h["units"] + units else 0
        if _bool(stop_sip):
            h["sip"] = None
        db.put("mf_holdings", h)
        _post(user, amount=value, direction="credit", narration=f"BY TRANSFER-VNBMF/{h['folio']}/{scheme.upper()}/RED--", category="savings_investment",
              counterparty=f"{s['name']} (redemption)", channel="intra_bank")
    return {"holding": _mf_view(h), "message": f"Redeemed {units} units of {s['name']} for {rupees(value)}, credited to SB-01."
            + (" Exit load may apply as per the scheme." if "within" in s["exit_load"] else "")}


# ---------------------------------------------------------------- NPS


def get_nps_details() -> dict[str, Any]:
    user = current_user()
    account = next(iter(db.rows("nps", user)), None)
    age = _age(_customer(user)["dob"])
    years_to_60 = max(0, NPS["exit_age"] - age)
    return {"account": account, "rules": NPS, "your_age": age, "years_to_60": years_to_60,
            "tax_saving_per_year": int(50000 * _customer(user)["income_tax_slab_percent"] / 100 * 1.04),
            "eligible": 18 <= age <= 70}


def open_nps_account(investment_choice: str, initial_contribution: int, nominee_name: str, nominee_relation: str) -> dict[str, Any]:
    user = current_user()
    if db.rows("nps", user):
        return _error("You already have an NPS account — contribute to it instead", investment_choice="already open")
    if investment_choice not in NPS["choices"]:
        return _error(f"investment_choice must be one of: {', '.join(NPS['choices'])}", investment_choice="unknown")
    value = _amount(initial_contribution, "initial_contribution")
    if isinstance(value, dict):
        return value
    if value < NPS["min_opening"]:
        return _error(f"The first contribution must be at least {rupees(NPS['min_opening'])}", initial_contribution="too low")
    if nominee_relation not in RELATIONS or not nominee_name.strip():
        return _error("Give a nominee and their relation", nominee_name="required")
    with db.transaction():
        problem = _debit_or_error(user, value)
        if problem:
            return problem
        pran = "1100" + _ref()[:8]
        acc = {"user_id": user, "id": "NPS-01", "pran": pran, "tier": "Tier I", "choice": NPS["choices"][investment_choice], "contributed": value,
               "this_fy": value, "opened": _today().isoformat(), "nominee": f"{nominee_name.strip()} ({nominee_relation})"}
        db.put("nps", acc)
        _post(user, amount=value, direction="debit", narration=f"TO TRANSFER-NPS TIER1 PRAN {pran}--", category="savings_investment",
              counterparty="NPS Tier I contribution", channel="intra_bank")
    return {"nps": acc, "message": f"NPS Tier I opened, PRAN {pran}, with {rupees(value)}. Up to ₹50,000 a year gets the extra 80CCD(1B) deduction. "
                                   "Your e-PRAN card comes by e-mail."}


def contribute_to_nps(amount: int) -> dict[str, Any]:
    user = current_user()
    acc = next(iter(db.rows("nps", user)), None)
    if acc is None:
        return _error("not_found: no NPS account — open one first")
    value = _amount(amount)
    if isinstance(value, dict):
        return value
    if value < NPS["min_contribution"]:
        return _error(f"Minimum contribution is {rupees(NPS['min_contribution'])}", amount="too low")
    with db.transaction():
        problem = _debit_or_error(user, value)
        if problem:
            return problem
        acc["contributed"] += value
        acc["this_fy"] += value
        db.put("nps", acc)
        _post(user, amount=value, direction="debit", narration=f"TO TRANSFER-NPS TIER1 PRAN {acc['pran']}--", category="savings_investment",
              counterparty="NPS Tier I contribution", channel="intra_bank")
    left = max(0, 50000 - acc["this_fy"])
    return {"nps": acc, "message": f"{rupees(value)} contributed to NPS (PRAN {acc['pran']})."
            + (f" {rupees(left)} more this year still gets the extra 80CCD(1B) deduction." if left else " You've used the full ₹50,000 80CCD(1B) deduction this year.")}


# ---------------------------------------------------------------- lockers


def get_locker_availability() -> dict[str, Any]:
    user = current_user()
    cust = _customer(user)
    mine = db.rows("lockers", user)
    return {"branch": cust["branch"], "sizes": [{"size": k, "rent_per_year": v["rent"], "rent_with_gst": _with_gst(v["rent"]), "available": v["available"],
                                                  "waitlist": v["waitlist"]} for k, v in LOCKERS.items()],
            "rule": LOCKER_RULE, "yours": mine}


def apply_for_locker(size: str, nominee_name: str = "", nominee_relation: str = "") -> dict[str, Any]:
    user = current_user()
    if size not in LOCKERS:
        return _error(f"size must be one of: {', '.join(LOCKERS)}", size="unknown")
    if any(l["status"] in ("allotted", "waitlisted") for l in db.rows("lockers", user)):
        return _error("You already have a locker or a pending request", size="already applied")
    info = LOCKERS[size]
    cust = _customer(user)
    with db.transaction():
        if info["available"] > 0:
            rent = _with_gst(info["rent"])
            problem = _debit_or_error(user, rent)
            if problem:
                return problem
            number = f"{size[0].upper()}-{random.randint(100, 399)}"
            row = {"user_id": user, "id": _next_id("lockers", user, "LKR-"), "size": size, "status": "allotted", "locker_number": number, "rent_paid": rent,
                   "branch": cust["branch"], "since": _today().isoformat(), "renews": (_today() + timedelta(days=365)).isoformat(),
                   "nominee": f"{nominee_name.strip()} ({nominee_relation})" if nominee_name.strip() else None}
            _post(user, amount=rent, direction="debit", narration=f"LOCKER RENT {number} INCL GST--", category="charges",
                  counterparty=f"Locker {number} rent (incl. GST)", channel="charges")
            message = (f"Locker {number} ({size.replace('_', ' ')}) allotted at {cust['branch']}; {rupees(rent)} rent paid. Visit the branch to sign the "
                       "locker agreement and collect the key (bring ID).")
        else:
            row = {"user_id": user, "id": _next_id("lockers", user, "LKR-"), "size": size, "status": "waitlisted", "position": info["waitlist"] + 1,
                   "branch": cust["branch"], "since": _today().isoformat()}
            message = f"No {size.replace('_', ' ')} locker is free at {cust['branch']}; you are number {row['position']} on the waiting list (RBI requires the bank to keep it)."
        db.put("lockers", row)
        _request(user, "locker", message[:120])
    return {"locker": row, "message": message}
