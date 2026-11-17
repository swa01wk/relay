"""Kestrel Bank's business logic — the one implementation behind both the net banking site's API and
the Relay tools. Every rule lives here once: balances, transfers (own accounts, UPI, IMPS, NEFT) and
their limits, new-payee cooling period, standing instructions, bill payments and autopay, card
controls, locks and replacements, credit card statements and payments, fixed deposits (rates,
maturity, premature closure) and transaction disputes.

Money is whole rupees; times are IST. Everything belongs to the signed-in customer, read from
``current_user()``; only the bank's catalogues (FD rates, billers' categories, rules) work without one.
Time-based events — standing instructions, bill autopay, FD payouts and maturity, card delivery —
are applied when the customer's data is next read (``_catch_up``), so no scheduler is needed.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from bank_api import db
from bank_api.seeds import (
    ACCOUNTS,
    BANKS,
    BILLERS,
    CARDS,
    CATEGORIES,
    DEFAULT_CUSTOMER,
    DEPOSITS,
    FD_RATES,
    HISTORY_DAYS,
    PAYEES,
    STANDING,
    add_months,
    build_history,
)

IST = timezone(timedelta(hours=5, minutes=30))
LIMITS = {
    "upi_per_transfer": 100000,
    "upi_daily": 100000,
    "imps_per_transfer": 500000,
    "daily_to_payees": 500000,  # all transfers to other people today (own-account transfers don't count)
    "new_payee_cap": 50000,  # in the first 24 hours after adding a payee
}
NEW_PAYEE_HOURS = 24
MODES = {"own": "Own account transfer", "upi": "UPI", "imps": "IMPS", "neft": "NEFT"}
ARRIVAL = {"own": "instantly", "upi": "instantly", "imps": "instantly", "neft": "within 30 minutes"}
REPEATS = ("once", "monthly")
CHANNEL_LABELS = {"upi": "UPI", "imps": "IMPS", "neft": "NEFT", "own": "Own account transfer", "card": "Card", "atm": "ATM",
                  "bill_pay": "Bill payment", "auto_debit": "Auto debit", "interest": "Interest", "fd": "Fixed deposit",
                  "card_payment": "Card bill payment", "fee": "Fee", "refund": "Refund"}
CHANNELS = tuple(CHANNEL_LABELS)
DISPUTE_REASONS = {
    "unauthorized": "I didn't make this transaction",
    "charged_twice": "Charged twice",
    "wrong_amount": "Charged the wrong amount",
    "not_received": "Paid but didn't get the goods or service",
    "refund_not_received": "Refund promised but not received",
    "other": "Something else",
}
DISPUTABLE_CHANNELS = ("card", "upi", "atm", "bill_pay", "auto_debit")
DISPUTE_WINDOW_DAYS = 120
DISPUTE_RESOLUTION_DAYS = 14
REPORT_REASONS = {"lost": "Lost", "stolen": "Stolen", "damaged": "Damaged"}
REPLACEMENT_FEE = 236  # ₹200 + 18% GST, debit cards reported lost or stolen
DELIVERY_DAYS = 5
CARD_LIMIT_MAX = {"atm_daily": 100000, "pos_daily": 500000, "online_daily": 500000}
FD_MIN, FD_MAX = 10000, 10000000
FD_PENALTY = 1.0  # percentage points off the rate for the time held, on premature closure
FD_PAYOUTS = {"cumulative": "Interest added at maturity (compounded quarterly)", "quarterly": "Interest paid to your account every quarter"}
SORTS = ("date", "amount")
DIRECTIONS = ("debit", "credit")
MAX_PAYEES = 50
INTERNAL_CATEGORIES = ("transfers", "card_payment")  # left out of income / spending analytics by default
_IFSC = re.compile(r"[A-Z]{4}0[A-Z0-9]{6}")
_UPI = re.compile(r"[A-Za-z0-9._-]{2,64}@[A-Za-z]{2,32}")
_ACCOUNT_NO = re.compile(r"\d{9,18}")

_user: ContextVar[str | None] = ContextVar("bank_user", default=None)


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
    _catch_up(user_id)
    return user_id


# ---------------------------------------------------------------- helpers


def _now() -> datetime:
    return datetime.now(IST)


def _today() -> date:
    return _now().date()


def _error(message: str, **fields: str) -> dict[str, Any]:
    return {"error": message, **({"fields": fields} if fields else {})}


def _amount(value: Any, field: str = "amount") -> int | dict[str, Any]:
    try:
        number = float(str(value).replace(",", "").replace("₹", "").strip())
    except (TypeError, ValueError):
        return _error(f"{field} must be a number of rupees", **{field: "not a number"})
    if not math.isfinite(number) or number <= 0:
        return _error(f"{field} must be more than ₹0", **{field: "must be positive"})
    return int(round(number))


def _parse_date(value: Any, field: str) -> date | dict[str, Any]:
    text = str(value or "").strip().lower()
    if text in ("today", "now"):
        return _today()
    if text == "tomorrow":
        return _today() + timedelta(days=1)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return _error(f"{field} must be a date like 2026-12-01", **{field: "not a date"})


def _bool(value: Any) -> bool:
    return value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes", "on")


def _mask(number: str) -> str:
    return f"••{number[-4:]}"


def _rupees(value: int) -> str:
    s = str(abs(int(value)))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"{'-' if value < 0 else ''}₹{s}"


def _day_of(iso: str) -> date:
    return datetime.fromisoformat(iso).astimezone(IST).date()


def _next_id(user_id: str, kind: str, prefix: str, width: int = 2, start: int = 1) -> str:
    numbers = [int(r["id"].split("-")[1]) for r in db.rows(kind, user_id) if r["id"].startswith(prefix + "-")]
    return f"{prefix}-{(max(numbers) + 1 if numbers else start):0{width}d}"


def _reference(prefix: str) -> str:
    return f"{prefix}{_now():%y%j%H%M%S%f}"[:16].upper()


# ---------------------------------------------------------------- seeding and catch-up


def _ensure_customer(user_id: str) -> None:
    """A new user starts as the demo customer with six months of history."""
    if db.get("customers", user_id, "me") is not None:
        return
    with db.transaction():
        if db.get("customers", user_id, "me") is not None:
            return
        today, now = _today(), _now()
        history = build_history(today)
        for d in DEPOSITS:
            opened = today - timedelta(days=d["opened_days_ago"])
            if opened > today - timedelta(days=HISTORY_DAYS):
                history.append({"account_id": "ACC-01", "posted_at": datetime.combine(opened, time(11, 5), IST).isoformat(), "direction": "debit",
                                "amount": d["principal"], "description": f"Fixed deposit {d['id']} opened", "category": "investments",
                                "channel": "fd", "deposit_id": d["id"]})
        history.sort(key=lambda t: t["posted_at"])
        _add_card_payments(history, today)
        txns = []
        for i, t in enumerate(history, start=1):
            txns.append({"id": f"TXN-{100000 + i}", "user_id": user_id, "reference": f"KST{(today.toordinal() * 7919 + i * 104729) % 10**10:010d}", **t})
        db.put_many("transactions", txns)

        net = {a["id"]: 0 for a in ACCOUNTS}
        for t in history:
            if t["account_id"] in net:
                net[t["account_id"]] += t["amount"] if t["direction"] == "credit" else -t["amount"]
        targets = {"ACC-01": 184260, "ACC-02": 61340}
        for a in ACCOUNTS:
            low = _lowest_running(history, a["id"])
            opening = max(targets[a["id"]] - net[a["id"]], 25000 - low)
            db.put("accounts", {**a, "user_id": user_id, "opening_balance": opening, "opening_date": (today - timedelta(days=HISTORY_DAYS)).isoformat()})
        for c in CARDS:
            db.put("cards", {**c, "user_id": user_id, "controls": dict(c["controls"]), "limits": dict(c["limits"])})
        for p in PAYEES:
            row = {k: v for k, v in p.items() if k != "added_days_ago"}
            db.put("payees", {**row, "user_id": user_id, "bank": BANKS.get(str(p.get("ifsc", ""))[:4]) if p["kind"] == "bank" else None,
                              "added_at": (now - timedelta(days=p["added_days_ago"])).isoformat()})
        for sid, payee, amount, day, note in STANDING:
            next_date = date(today.year, today.month, day)
            if next_date <= today:
                next_date = add_months(next_date, 1)
            db.put("scheduled", {"id": sid, "user_id": user_id, "from_account": "ACC-01", "to": payee, "amount": amount, "mode": "imps",
                                 "note": note, "repeat": "monthly", "next_date": next_date.isoformat(), "status": "active",
                                 "created_at": (now - timedelta(days=700)).isoformat(), "runs": []})
        for b in BILLERS:
            bill = None
            if b["due_in_days"] is not None:
                due = today + timedelta(days=b["due_in_days"])
                bill = {"amount": b["amount"], "due_date": due.isoformat(), "bill_date": (due - timedelta(days=15)).isoformat()}
            last = next((t for t in reversed(history) if t.get("biller_id") == b["id"]), None)
            db.put("billers", {"id": b["id"], "user_id": user_id, "name": b["name"], "category": b["category"], "nickname": b["nickname"],
                               "consumer_number": b["consumer_number"], "bill": bill, "autopay": {"enabled": b["autopay"], "from_account": "ACC-01", "max_amount": 5000},
                               "last_paid": {"amount": last["amount"], "date": last["posted_at"][:10]} if last else None})
        for d in DEPOSITS:
            opened = today - timedelta(days=d["opened_days_ago"])
            db.put("deposits", _new_deposit(user_id, d["id"], d["principal"], opened, d["tenure_months"], d["payout"], d["auto_renew"], "ACC-01"))
        db.put("customers", {"id": "me", "user_id": user_id, **DEFAULT_CUSTOMER})


def _lowest_running(history: list[dict[str, Any]], account_id: str) -> int:
    running, low = 0, 0
    for t in history:
        if t["account_id"] == account_id:
            running += t["amount"] if t["direction"] == "credit" else -t["amount"]
            low = min(low, running)
    return low


def _statement_closes(card: dict[str, Any], start: date, end: date) -> list[date]:
    """Statement dates (the card's statement day each month) after ``start`` and before ``end``."""
    day = card["statement_day"]
    d = date(start.year, start.month, day)
    out = []
    while d < end:
        if d > start:
            out.append(d)
        d = add_months(d, 1)
    return out


def _add_card_payments(history: list[dict[str, Any]], today: date) -> None:
    """The demo customer pays each credit card statement in full two days before it is due."""
    card = next(c for c in CARDS if c["kind"] == "credit")
    start = today - timedelta(days=HISTORY_DAYS)
    for close in _statement_closes(card, start, today):
        pay_day = close + timedelta(days=card["due_after_days"] - 2)
        if pay_day >= today:
            continue
        close_end = datetime.combine(close, time(23, 59, 59), IST).isoformat()
        pay_at = datetime.combine(pay_day, time(10, 15), IST).isoformat()
        owed = sum((t["amount"] if t["direction"] == "debit" else -t["amount"]) for t in history if t["account_id"] == card["id"] and t["posted_at"] <= close_end)
        credited = sum(t["amount"] for t in history if t["account_id"] == card["id"] and t["direction"] == "credit" and close_end < t["posted_at"] < pay_at)
        amount = owed - credited
        if amount <= 0:
            continue
        history.append({"account_id": "ACC-01", "posted_at": pay_at, "direction": "debit", "amount": amount,
                        "description": f"{card['name']} ••{card['last4']} payment", "category": "card_payment", "channel": "card_payment", "card_id": card["id"]})
        history.append({"account_id": card["id"], "posted_at": pay_at, "direction": "credit", "amount": amount,
                        "description": "Payment received — thank you", "category": "card_payment", "channel": "card_payment"})
        history.sort(key=lambda t: t["posted_at"])


def _catch_up(user_id: str) -> None:
    """Apply what happened since the data was last read: standing instructions and scheduled
    transfers, bill autopay, FD interest payouts and maturity, replacement cards arriving."""
    today = _today()
    with db.transaction():
        for s in db.rows("scheduled", user_id):
            changed = False
            while s["status"] == "active" and date.fromisoformat(s["next_date"]) <= today:
                when = date.fromisoformat(s["next_date"])
                result = _execute_transfer(user_id, s["from_account"], s["to"], s["amount"], s["mode"], s["note"],
                                           posted_at=datetime.combine(when, time(8, 0), IST), scheduled_id=s["id"])
                s["runs"] = [*s["runs"], {"date": when.isoformat(), "ok": "error" not in result, **({"error": result["error"]} if "error" in result else {})}][-12:]
                if s["repeat"] == "monthly":
                    s["next_date"] = add_months(when, 1).isoformat()
                else:
                    s["status"] = "completed" if "error" not in result else "failed"
                changed = True
            if changed:
                db.put("scheduled", s)
        for b in db.rows("billers", user_id):
            auto, bill = b["autopay"], b["bill"]
            if auto["enabled"] and bill and date.fromisoformat(bill["due_date"]) <= today and not bill.get("autopay_skipped"):
                if bill["amount"] <= auto["max_amount"] and _balance(user_id, auto["from_account"]) >= bill["amount"]:
                    _pay_biller(user_id, b, bill["amount"], auto["from_account"], autopay=True)
                else:
                    bill["autopay_skipped"] = "over your autopay limit" if bill["amount"] > auto["max_amount"] else "not enough balance"
                    db.put("billers", b)
        for d in db.rows("deposits", user_id):
            if d["status"] != "active":
                continue
            changed = False
            maturity = date.fromisoformat(d["maturity_date"])
            if d["payout"] == "quarterly":
                quarter = add_months(date.fromisoformat(d["opened"]), 3 * (d["payouts_made"] + 1))
                while quarter <= min(today, maturity):
                    interest = _quarter_interest(d)
                    _post(user_id, d["account_id"], "credit", interest, f"Interest — fixed deposit {d['id']}", "interest", "interest",
                          posted_at=datetime.combine(quarter, time(6, 0), IST), deposit_id=d["id"])
                    d["payouts_made"] += 1
                    d["interest_paid"] += interest
                    quarter = add_months(date.fromisoformat(d["opened"]), 3 * (d["payouts_made"] + 1))
                    changed = True
            if maturity <= today:
                value = _maturity_value(d)
                if d["auto_renew"]:
                    renewed = _new_deposit(user_id, _next_id(user_id, "deposits", "FD"), value, maturity, d["tenure_months"], d["payout"], True, d["account_id"])
                    db.put("deposits", renewed)
                    d["renewed_as"] = renewed["id"]
                else:
                    _post(user_id, d["account_id"], "credit", value, f"Fixed deposit {d['id']} matured", "investments", "fd",
                          posted_at=datetime.combine(maturity, time(6, 30), IST), deposit_id=d["id"])
                d.update(status="matured", closed_on=maturity.isoformat(), paid_out=value)
                changed = True
            if changed:
                db.put("deposits", d)
        for c in db.rows("cards", user_id):
            if c["status"] == "on_the_way" and date.fromisoformat(c["arrives_on"]) <= today:
                c["status"] = "active"
                db.put("cards", c)


# ---------------------------------------------------------------- accounts and transactions


def _accounts(user_id: str) -> list[dict[str, Any]]:
    return db.rows("accounts", user_id)


def _txns(user_id: str) -> list[dict[str, Any]]:
    return sorted(db.rows("transactions", user_id), key=lambda t: (t["posted_at"], t["id"]))


def _balance(user_id: str, account_id: str) -> int:
    account = db.get("accounts", user_id, account_id)
    if account is None:
        return 0
    return account["opening_balance"] + sum((t["amount"] if t["direction"] == "credit" else -t["amount"]) for t in db.rows("transactions", user_id) if t["account_id"] == account_id)


def _post(user_id: str, account_id: str, direction: str, amount: int, description: str, category: str, channel: str,
          posted_at: datetime | None = None, **extra: Any) -> dict[str, Any]:
    numbers = [int(t["id"].split("-")[1]) for t in db.rows("transactions", user_id)]
    row = {"id": f"TXN-{(max(numbers) + 1) if numbers else 100001}", "user_id": user_id, "account_id": account_id,
           "posted_at": (posted_at or _now()).isoformat(), "direction": direction, "amount": int(amount), "description": description,
           "category": category, "channel": channel, "reference": _reference("KST"), **extra}
    return db.put("transactions", row)


def _resolve_account(user_id: str, ref: Any) -> dict[str, Any] | None:
    q = str(ref or "").strip().lower()
    if not q:
        return None
    accounts = _accounts(user_id)
    for a in accounts:
        if q in (a["id"].lower(), a["number"], a["number"][-4:], a["name"].lower()):
            return a
    if q in ("main", "salary", "primary", "savings", "savings account", "premier", "my account"):
        return accounts[0]
    if q in ("joint", "joint account", "household"):
        return next((a for a in accounts if len(a["holders"]) > 1), None)
    hits = [a for a in accounts if q in a["name"].lower()]
    return hits[0] if len(hits) == 1 else None


def _account_label(user_id: str, account_id: str) -> str:
    a = db.get("accounts", user_id, account_id)
    if a:
        return f"{a['name']} {_mask(a['number'])}"
    c = db.get("cards", user_id, account_id)
    return f"{c['name']} ••{c['last4']}" if c else account_id


def _account_view(user_id: str, a: dict[str, Any]) -> dict[str, Any]:
    month = _today().isoformat()[:7]
    this_month = [t for t in db.rows("transactions", user_id) if t["account_id"] == a["id"] and t["posted_at"][:7] == month]
    return {
        "id": a["id"], "name": a["name"], "type": a["type"], "number_masked": _mask(a["number"]), "label": f"{a['name']} {_mask(a['number'])}",
        "balance": _balance(user_id, a["id"]), "holders": a["holders"], "min_balance": a["min_balance"],
        "money_in_this_month": sum(t["amount"] for t in this_month if t["direction"] == "credit"),
        "money_out_this_month": sum(t["amount"] for t in this_month if t["direction"] == "debit"),
    }


def list_accounts() -> dict[str, Any]:
    user_id = current_user()
    views = [_account_view(user_id, a) for a in _accounts(user_id)]
    return {"accounts": views, "total_balance": sum(v["balance"] for v in views), "currency": "INR"}


def get_account(*, account_id: str) -> dict[str, Any]:
    user_id = current_user()
    a = _resolve_account(user_id, account_id)
    if a is None:
        return _error(f"not_found: no account {account_id}", account_id="unknown account")
    view = _account_view(user_id, a)
    cards = [{"id": c["id"], "name": c["name"], "last4": c["last4"], "status": c["status"]} for c in db.rows("cards", user_id) if c.get("account_id") == a["id"]]
    scheduled = [_scheduled_view(user_id, s) for s in db.rows("scheduled", user_id) if s["from_account"] == a["id"] and s["status"] == "active"]
    recent = list_transactions(account_id=a["id"], limit=10)["transactions"]
    return {"account": {**view, "account_number": a["number"], "ifsc": a["ifsc"], "branch": DEFAULT_CUSTOMER["branch"],
                        "interest_rate": a["interest_rate"], "nominee": a["nominee"], "opened": a["opened"],
                        "below_min_balance": view["balance"] < a["min_balance"], "cards": cards, "scheduled_transfers": scheduled,
                        "recent_transactions": recent}}


def _txn_view(user_id: str, t: dict[str, Any], balance_after: int | None = None) -> dict[str, Any]:
    view = {k: t[k] for k in ("id", "account_id", "posted_at", "direction", "amount", "description", "category", "channel", "reference")}
    view["account"] = _account_label(user_id, t["account_id"])
    view["category_label"] = CATEGORIES.get(t["category"], t["category"])
    view["merchant"] = t.get("merchant")
    if balance_after is not None:
        view["balance_after"] = balance_after
    for k in ("payee_id", "biller_id", "deposit_id", "dispute_id", "note", "scheduled_id", "counterparty"):
        if t.get(k):
            view[k] = t[k]
    return view


def _running_balances(user_id: str, txns: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    running = {a["id"]: a["opening_balance"] for a in _accounts(user_id)}
    for t in txns:
        if t["account_id"] in running:
            running[t["account_id"]] += t["amount"] if t["direction"] == "credit" else -t["amount"]
            out[t["id"]] = running[t["account_id"]]
    return out


def _filter_txns(user_id: str, *, account_id: str | None = None, from_date: str | None = None, to_date: str | None = None,
                 category: str | None = None, direction: str | None = None, channel: str | None = None, min_amount: Any = None,
                 max_amount: Any = None, query: str | None = None, include_internal: bool = True) -> list[dict[str, Any]] | dict[str, Any]:
    txns = _txns(user_id)
    if account_id:
        account = _resolve_account(user_id, account_id)
        card = _resolve_card(user_id, account_id) if account is None else None
        if account is None and card is None:
            return _error(f"not_found: no account or card {account_id}", account_id="unknown account")
        if card and card["kind"] == "debit":
            # A debit card spends from its account; show that account's card payments.
            txns = [t for t in txns if t["account_id"] == card["account_id"] and t["channel"] in ("card", "atm")]
        else:
            target = account["id"] if account else _ledger_id(card)  # type: ignore[arg-type]
            txns = [t for t in txns if t["account_id"] == target]
    for value, field in ((from_date, "from_date"), (to_date, "to_date")):
        if value:
            parsed = _parse_date(value, field)
            if isinstance(parsed, dict):
                return parsed
            txns = [t for t in txns if (_day_of(t["posted_at"]) >= parsed if field == "from_date" else _day_of(t["posted_at"]) <= parsed)]
    if category:
        key = category.strip().lower()
        keys = [k for k, label in CATEGORIES.items() if key in (k, label.lower())] or [k for k, label in CATEGORIES.items() if key in label.lower()]
        if not keys:
            return _error(f"unknown category {category}; one of {', '.join(CATEGORIES)}", category="unknown category")
        txns = [t for t in txns if t["category"] in keys]
    if direction:
        if direction not in DIRECTIONS:
            return _error("direction is debit or credit", direction="debit or credit")
        txns = [t for t in txns if t["direction"] == direction]
    if channel:
        txns = [t for t in txns if t["channel"] == channel]
    if min_amount not in (None, ""):
        txns = [t for t in txns if t["amount"] >= float(min_amount)]
    if max_amount not in (None, ""):
        txns = [t for t in txns if t["amount"] <= float(max_amount)]
    if query:
        q = query.strip().lower()
        txns = [t for t in txns if q in t["description"].lower() or q in str(t.get("merchant") or "").lower() or q in t["reference"].lower() or q == t["id"].lower()]
    if not include_internal:
        txns = [t for t in txns if t["category"] not in INTERNAL_CATEGORIES]
    return txns


def list_transactions(
    *,
    account_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    category: str | None = None,
    direction: str | None = None,
    channel: str | None = None,
    min_amount: int | None = None,
    max_amount: int | None = None,
    query: str | None = None,
    sort_by: str = "date",
    sort_order: str = "desc",
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    user_id = current_user()
    txns = _filter_txns(user_id, account_id=account_id, from_date=from_date, to_date=to_date, category=category, direction=direction,
                        channel=channel, min_amount=min_amount, max_amount=max_amount, query=query)
    if isinstance(txns, dict):
        return txns
    all_txns = _txns(user_id)
    balances = _running_balances(user_id, all_txns)
    seen: dict[tuple[Any, ...], int] = {}
    for t in all_txns:
        if t["direction"] == "debit" and t.get("merchant"):
            k = (t["account_id"], t["merchant"], t["amount"], t["posted_at"][:10])
            seen[k] = seen.get(k, 0) + 1
    key = (lambda t: (t["amount"], t["posted_at"])) if sort_by == "amount" else (lambda t: (t["posted_at"], t["id"]))
    txns = sorted(txns, key=key, reverse=sort_order != "asc")
    page = txns[int(offset): int(offset) + max(1, min(int(limit), 200))]
    views = []
    for t in page:
        view = _txn_view(user_id, t, balances.get(t["id"]))
        if t["direction"] == "debit" and seen.get((t["account_id"], t.get("merchant"), t["amount"], t["posted_at"][:10]), 0) > 1:
            view["possible_duplicate"] = True  # same merchant, amount and day on the same account
        views.append(view)
    return {
        "transactions": views,
        "total": len(txns),
        "money_in": sum(t["amount"] for t in txns if t["direction"] == "credit"),
        "money_out": sum(t["amount"] for t in txns if t["direction"] == "debit"),
    }


def get_transaction(*, transaction_id: str) -> dict[str, Any]:
    user_id = current_user()
    t = _find_txn(user_id, transaction_id)
    if t is None:
        return _error(f"not_found: no transaction {transaction_id}", transaction_id="unknown transaction")
    view = _txn_view(user_id, t, _running_balances(user_id, _txns(user_id)).get(t["id"]))
    if t.get("payee_id"):
        payee = db.get("payees", user_id, t["payee_id"])
        view["payee"] = _payee_view(payee) if payee else None
    dispute = next((d for d in db.rows("disputes", user_id) if d["transaction_id"] == t["id"]), None)
    view["dispute"] = dispute
    view["can_dispute"], view["dispute_note"] = _disputable(t, dispute)
    similar = [x for x in _txns(user_id) if x["id"] != t["id"] and x.get("merchant") and x.get("merchant") == t.get("merchant")
               and x["amount"] == t["amount"] and x["posted_at"][:10] == t["posted_at"][:10]]
    if similar:
        view["possible_duplicate_of"] = [x["id"] for x in similar]
    return {"transaction": view}


def _find_txn(user_id: str, ref: str) -> dict[str, Any] | None:
    key = str(ref or "").strip().upper()
    t = db.get("transactions", user_id, key)
    if t is None and key:
        t = next((x for x in db.rows("transactions", user_id) if x["reference"] == key), None)
    return t


def aggregate_transactions(
    *,
    metric: str = "sum",
    group_by: str = "category",
    direction: str = "debit",
    account_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    category: str | None = None,
    include_internal: bool = False,
) -> dict[str, Any]:
    user_id = current_user()
    if group_by not in ("category", "merchant", "month", "week", "channel", "account", "weekday"):
        return _error("group_by is category, merchant, month, week, channel, account or weekday", group_by="unknown")
    if metric not in ("sum", "count", "avg"):
        return _error("metric is sum, count or avg", metric="unknown")
    txns = _filter_txns(user_id, account_id=account_id, from_date=from_date, to_date=to_date, category=category, direction=direction,
                        include_internal=include_internal)
    if isinstance(txns, dict):
        return txns
    groups: dict[str, list[int]] = {}
    for t in txns:
        day = _day_of(t["posted_at"])
        key = {
            "category": CATEGORIES.get(t["category"], t["category"]),
            "merchant": t.get("merchant") or t["description"],
            "month": day.isoformat()[:7],
            "week": (day - timedelta(days=day.weekday())).isoformat(),
            "channel": CHANNEL_LABELS.get(t["channel"], t["channel"]),
            "account": _account_label(user_id, t["account_id"]),
            "weekday": day.strftime("%A"),
        }[group_by]
        groups.setdefault(key, []).append(t["amount"])
    value = {"sum": sum, "count": len, "avg": lambda xs: round(sum(xs) / len(xs))}[metric]
    rows = [{"group": k, "value": value(v), "count": len(v)} for k, v in groups.items()]
    rows.sort(key=lambda r: r["group"] if group_by in ("month", "week") else -r["value"])
    return {"metric": metric, "group_by": group_by, "direction": direction, "groups": rows, "total": sum(sum(v) for v in groups.values()), "currency": "INR"}


def _month_keys(months: int) -> list[str]:
    today = _today()
    return [add_months(date(today.year, today.month, 1), -i).isoformat()[:7] for i in range(months - 1, -1, -1)]


def get_cash_flow(*, months: int = 6, account_id: str | None = None) -> dict[str, Any]:
    user_id = current_user()
    months = max(1, min(int(months), 6))
    txns = _filter_txns(user_id, account_id=account_id, include_internal=False)
    if isinstance(txns, dict):
        return txns
    out = []
    for key in _month_keys(months):
        mine = [t for t in txns if t["posted_at"][:7] == key]
        money_in = sum(t["amount"] for t in mine if t["direction"] == "credit" and t["category"] != "refunds")
        refunds = sum(t["amount"] for t in mine if t["direction"] == "credit" and t["category"] == "refunds")
        spent = sum(t["amount"] for t in mine if t["direction"] == "debit" and t["category"] != "investments") - refunds
        invested = sum(t["amount"] for t in mine if t["direction"] == "debit" and t["category"] == "investments")
        out.append({"month": key, "income": money_in, "spending": spent, "invested": invested, "net": money_in - spent - invested})
    return {"months": out, "currency": "INR", "note": "Transfers between your own accounts and credit card bill payments are left out; card spending counts when you spend."}


def get_month_summary(*, month: str | None = None) -> dict[str, Any]:
    user_id = current_user()
    key = (month or _today().isoformat())[:7]
    if not re.fullmatch(r"\d{4}-\d{2}", key):
        return _error("month must look like 2026-10", month="YYYY-MM")
    txns = [t for t in _filter_txns(user_id, include_internal=False) if t["posted_at"][:7] == key]  # type: ignore[index]
    prev_key = add_months(date.fromisoformat(f"{key}-01"), -1).isoformat()[:7]
    prev = [t for t in _filter_txns(user_id, include_internal=False) if t["posted_at"][:7] == prev_key]  # type: ignore[index]

    def spend(rows: list[dict[str, Any]]) -> int:
        refunds = sum(t["amount"] for t in rows if t["direction"] == "credit" and t["category"] == "refunds")
        return sum(t["amount"] for t in rows if t["direction"] == "debit" and t["category"] != "investments") - refunds

    income = sum(t["amount"] for t in txns if t["direction"] == "credit" and t["category"] != "refunds")
    spent = spend(txns)
    by_cat: dict[str, int] = {}
    by_merchant: dict[str, int] = {}
    for t in txns:
        if t["direction"] == "debit" and t["category"] != "investments":
            by_cat[CATEGORIES[t["category"]]] = by_cat.get(CATEGORIES[t["category"]], 0) + t["amount"]
            if t.get("merchant"):
                by_merchant[t["merchant"]] = by_merchant.get(t["merchant"], 0) + t["amount"]
    # The biggest one-off: not rent, family support, investments or anything scheduled.
    one_off = [t for t in txns if t["direction"] == "debit" and t["category"] not in ("investments", "rent", "family") and not t.get("scheduled_id")]
    biggest = max(one_off, key=lambda t: t["amount"], default=None)
    invested = sum(t["amount"] for t in txns if t["direction"] == "debit" and t["category"] == "investments")
    return {
        "month": key,
        "income": income,
        "spending": spent,
        "invested": invested,
        "saved": income - spent,
        "savings_rate_pct": round(100 * (income - spent) / income) if income else None,
        "spending_last_month": spend(prev),
        "change_vs_last_month_pct": round(100 * (spent - spend(prev)) / spend(prev)) if spend(prev) else None,
        "top_categories": [{"category": k, "amount": v} for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1])[:6]],
        "top_merchants": [{"merchant": k, "amount": v} for k, v in sorted(by_merchant.items(), key=lambda kv: -kv[1])[:5]],
        "biggest_expense": _txn_view(user_id, biggest) if biggest else None,
        "partial_month": key == _today().isoformat()[:7],
    }


# ---------------------------------------------------------------- payees


def _payee_view(p: dict[str, Any]) -> dict[str, Any]:
    added = datetime.fromisoformat(p["added_at"])
    cooling_until = added + timedelta(hours=NEW_PAYEE_HOURS)
    view = {"id": p["id"], "name": p["name"], "nickname": p.get("nickname"), "kind": p["kind"], "added_at": p["added_at"]}
    if p["kind"] == "upi":
        view["upi_id"] = p["upi_id"]
        view["label"] = f"{p['name']} · {p['upi_id']}"
    else:
        view.update(account_masked=_mask(p["account_number"]), ifsc=p["ifsc"], bank=p.get("bank") or BANKS.get(p["ifsc"][:4], "Other bank"))
        view["label"] = f"{p['name']} · {view['bank']} {_mask(p['account_number'])}"
    if _now() < cooling_until:
        view["cooling_until"] = cooling_until.isoformat()
    return view


def _resolve_payee(user_id: str, ref: Any) -> dict[str, Any] | None:
    q = str(ref or "").strip().lower()
    if not q:
        return None
    payees = db.rows("payees", user_id)
    for p in payees:
        if q in (p["id"].lower(), p["name"].lower(), str(p.get("nickname") or "").lower(), str(p.get("upi_id") or "").lower(), str(p.get("account_number") or "")):
            return p
    hits = [p for p in payees if q in p["name"].lower() or q in str(p.get("nickname") or "").lower()]
    return hits[0] if len(hits) == 1 else None


def list_payees(*, query: str | None = None) -> dict[str, Any]:
    user_id = current_user()
    payees = db.rows("payees", user_id)
    if query:
        q = query.strip().lower()
        payees = [p for p in payees if q in p["name"].lower() or q in str(p.get("nickname") or "").lower()]
    txns = _txns(user_id)
    out = []
    for p in payees:
        last = next((t for t in reversed(txns) if t.get("payee_id") == p["id"] and t["direction"] == "debit"), None)
        out.append({**_payee_view(p), "last_paid": {"amount": last["amount"], "date": last["posted_at"][:10]} if last else None})
    return {"payees": out, "total": len(out)}


def get_payee(*, payee_id: str) -> dict[str, Any]:
    user_id = current_user()
    p = _resolve_payee(user_id, payee_id)
    if p is None:
        return _error(f"not_found: no payee {payee_id}", payee_id="unknown payee")
    paid = [t for t in _txns(user_id) if t.get("payee_id") == p["id"] and t["direction"] == "debit"]
    scheduled = [_scheduled_view(user_id, s) for s in db.rows("scheduled", user_id) if s["to"] == p["id"] and s["status"] == "active"]
    return {"payee": {**_payee_view(p), "recent_transfers": [_txn_view(user_id, t) for t in paid[-8:][::-1]],
                      "paid_last_6_months": sum(t["amount"] for t in paid), "scheduled_transfers": scheduled}}


def add_payee(*, name: str, account_number: str | None = None, ifsc: str | None = None, upi_id: str | None = None, nickname: str | None = None) -> dict[str, Any]:
    user_id = current_user()
    name = " ".join(str(name or "").split())
    if len(name) < 2:
        return _error("give the payee's name as on their account", name="required")
    if upi_id and (account_number or ifsc):
        return _error("give either a UPI ID or an account number with IFSC, not both", upi_id="either UPI or account")
    if upi_id:
        upi_id = upi_id.strip().lower()
        if not _UPI.fullmatch(upi_id):
            return _error("that UPI ID doesn't look right (like name@okhdfcbank)", upi_id="invalid UPI ID")
        row: dict[str, Any] = {"kind": "upi", "upi_id": upi_id}
        dup = next((p for p in db.rows("payees", user_id) if p.get("upi_id") == upi_id), None)
    else:
        number = re.sub(r"[\s-]", "", str(account_number or ""))
        code = str(ifsc or "").strip().upper()
        fields = {}
        if not _ACCOUNT_NO.fullmatch(number):
            fields["account_number"] = "9–18 digits"
        if not _IFSC.fullmatch(code):
            fields["ifsc"] = "11 characters like HDFC0001234"
        if fields:
            return _error("check the account number and IFSC", **fields)
        row = {"kind": "bank", "account_number": number, "ifsc": code, "bank": BANKS.get(code[:4], "Other bank")}
        dup = next((p for p in db.rows("payees", user_id) if p.get("account_number") == number), None)
    if dup:
        return _error(f"{dup['name']} is already a payee with these details", name="already added")
    if len(db.rows("payees", user_id)) >= MAX_PAYEES:
        return _error(f"you can have at most {MAX_PAYEES} payees; remove one first")
    with db.transaction():
        payee = db.put("payees", {"id": _next_id(user_id, "payees", "PAY"), "user_id": user_id, "name": name,
                                  "nickname": (nickname or "").strip()[:30] or None, "added_at": _now().isoformat(), **row})
    view = _payee_view(payee)
    return {"payee": view, "message": f"{name} added. For the first {NEW_PAYEE_HOURS} hours you can send them up to {_rupees(LIMITS['new_payee_cap'])} in total."}


def remove_payee(*, payee_id: str) -> dict[str, Any]:
    user_id = current_user()
    p = _resolve_payee(user_id, payee_id)
    if p is None:
        return _error(f"not_found: no payee {payee_id}", payee_id="unknown payee")
    cancelled = []
    with db.transaction():
        for s in db.rows("scheduled", user_id):
            if s["to"] == p["id"] and s["status"] == "active":
                s["status"] = "cancelled"
                db.put("scheduled", s)
                cancelled.append(s["id"])
        db.delete("payees", user_id, p["id"])
    return {"removed": p["name"], "cancelled_scheduled_transfers": cancelled,
            "message": f"{p['name']} removed" + (f"; {len(cancelled)} scheduled transfer(s) to them cancelled." if cancelled else ".")}


# ---------------------------------------------------------------- transfers


def _sent_today(user_id: str) -> tuple[int, int]:
    """(to other people today, by UPI today) from bank accounts."""
    today = _today().isoformat()
    to_people = upi = 0
    for t in db.rows("transactions", user_id):
        if t["direction"] == "debit" and t.get("payee_id") and t["channel"] in ("upi", "imps", "neft") and _day_of(t["posted_at"]).isoformat() == today:
            to_people += t["amount"]
            if t["channel"] == "upi":
                upi += t["amount"]
    return to_people, upi


def _sent_to_since(user_id: str, payee_id: str, since: datetime) -> int:
    return sum(t["amount"] for t in db.rows("transactions", user_id)
               if t.get("payee_id") == payee_id and t["direction"] == "debit" and datetime.fromisoformat(t["posted_at"]) >= since)


def _plan_transfer(user_id: str, from_account: Any, to: Any, amount: Any, mode: str | None, *, check_limits: bool = True) -> dict[str, Any]:
    """Validate a transfer and work out its mode, arrival and limits; ``{"error": …}`` when it can't go."""
    source = _resolve_account(user_id, from_account or "ACC-01")
    if source is None:
        return _error(f"no account {from_account}; transfers go from a savings account", from_account="unknown account")
    value = _amount(amount)
    if isinstance(value, dict):
        return value
    own = _resolve_account(user_id, to)
    payee = None if own else _resolve_payee(user_id, to)
    if own is None and payee is None:
        return _error(f"no payee or own account called {to} — add them as a payee first", to="unknown payee")
    if own and own["id"] == source["id"]:
        return _error("choose a different account to send to", to="same account")
    if own:
        chosen = "own"
    elif payee["kind"] == "upi":  # type: ignore[index]
        chosen = "upi"
    else:
        chosen = (mode or "").lower() or ("imps" if value <= LIMITS["imps_per_transfer"] else "neft")
    if mode and mode.lower() != chosen and not (payee and payee["kind"] == "bank" and mode.lower() in ("imps", "neft")):
        return _error(f"{MODES.get(mode.lower(), mode)} isn't available for this payee; use {MODES[chosen]}", mode="not available")
    if chosen not in MODES:
        return _error("mode is upi, imps or neft", mode="unknown")
    warnings = []
    plan = {"from_account": source["id"], "from_label": f"{source['name']} {_mask(source['number'])}", "amount": value, "mode": chosen,
            "mode_label": MODES[chosen], "arrives": ARRIVAL[chosen], "fee": 0}
    if own:
        plan.update(to_kind="own", to_id=own["id"], to_label=f"{own['name']} {_mask(own['number'])}")
    else:
        plan.update(to_kind="payee", to_id=payee["id"], to_label=_payee_view(payee)["label"], payee_name=payee["name"])  # type: ignore[index]
    if check_limits and not own:
        to_people, upi = _sent_today(user_id)
        if chosen == "upi" and value > LIMITS["upi_per_transfer"]:
            return _error(f"UPI transfers are up to {_rupees(LIMITS['upi_per_transfer'])} each", amount="over the UPI limit")
        if chosen == "upi" and upi + value > LIMITS["upi_daily"]:
            return _error(f"that would pass today's UPI limit — {_rupees(LIMITS['upi_daily'] - upi)} left today", amount="over today's UPI limit")
        if chosen == "imps" and value > LIMITS["imps_per_transfer"]:
            return _error(f"IMPS transfers are up to {_rupees(LIMITS['imps_per_transfer'])}; use NEFT", amount="over the IMPS limit")
        if to_people + value > LIMITS["daily_to_payees"]:
            return _error(f"that would pass your daily transfer limit — {_rupees(LIMITS['daily_to_payees'] - to_people)} left today",
                          amount="over the daily limit")
        added = datetime.fromisoformat(payee["added_at"])  # type: ignore[index]
        if _now() < added + timedelta(hours=NEW_PAYEE_HOURS):
            sent = _sent_to_since(user_id, payee["id"], added)  # type: ignore[index]
            if sent + value > LIMITS["new_payee_cap"]:
                until = added + timedelta(hours=NEW_PAYEE_HOURS)
                return _error(f"{payee['name']} was added less than {NEW_PAYEE_HOURS} hours ago: up to {_rupees(LIMITS['new_payee_cap'] - sent)} "  # type: ignore[index]
                              f"more until {until:%d %b, %H:%M}", amount="new payee limit")
        plan["daily_limit_left_after"] = LIMITS["daily_to_payees"] - to_people - value
    balance = _balance(user_id, source["id"])
    plan["balance_before"] = balance
    plan["balance_after"] = balance - value
    if balance < value:
        return {**_error(f"not enough money in {plan['from_label']} — balance {_rupees(balance)}", amount="more than the balance"), "balance": balance}
    if balance - value < source["min_balance"]:
        warnings.append(f"Your balance would drop below the {_rupees(source['min_balance'])} average balance this account needs.")
    plan["warnings"] = warnings
    return plan


def _execute_transfer(user_id: str, from_account: str, to: str, amount: int, mode: str | None, note: str | None,
                      posted_at: datetime | None = None, scheduled_id: str | None = None) -> dict[str, Any]:
    with db.transaction():
        plan = _plan_transfer(user_id, from_account, to, amount, mode)
        if "error" in plan:
            return plan
        extra: dict[str, Any] = {"note": note} if note else {}
        if scheduled_id:
            extra["scheduled_id"] = scheduled_id
        if plan["to_kind"] == "own":
            out = _post(user_id, plan["from_account"], "debit", plan["amount"], f"To {plan['to_label']}", "transfers", "own", posted_at,
                        counterparty=plan["to_id"], **extra)
            source = db.get("accounts", user_id, plan["from_account"])
            _post(user_id, plan["to_id"], "credit", plan["amount"], f"From {source['name']} {_mask(source['number'])}", "transfers", "own", posted_at,  # type: ignore[index]
                  counterparty=plan["from_account"], **extra)
        else:
            category = "rent" if (note or "").lower().startswith("rent") else "transfers"
            description = f"{note} — {plan['payee_name']}" if note else plan["payee_name"]
            out = _post(user_id, plan["from_account"], "debit", plan["amount"], description, category, plan["mode"], posted_at,
                        payee_id=plan["to_id"], merchant=plan["payee_name"], **extra)
    return {"transfer": {**plan, "transaction_id": out["id"], "reference": out["reference"], "note": note, "posted_at": out["posted_at"],
                         "balance_after": _balance(user_id, plan["from_account"])}}


def get_transfer_quote(*, to: str, amount: int, from_account: str = "ACC-01", mode: str | None = None) -> dict[str, Any]:
    user_id = current_user()
    plan = _plan_transfer(user_id, from_account, to, amount, mode)
    if "error" in plan:
        return {"can_send": False, **plan}
    return {"can_send": True, **plan}


def get_transfer_limits() -> dict[str, Any]:
    user_id = current_user()
    to_people, upi = _sent_today(user_id)
    cooling = []
    for p in db.rows("payees", user_id):
        view = _payee_view(p)
        if "cooling_until" in view:
            sent = _sent_to_since(user_id, p["id"], datetime.fromisoformat(p["added_at"]))
            cooling.append({"payee": p["name"], "until": view["cooling_until"], "left": LIMITS["new_payee_cap"] - sent})
    return {"limits": LIMITS, "sent_to_people_today": to_people, "left_today": LIMITS["daily_to_payees"] - to_people,
            "upi_left_today": LIMITS["upi_daily"] - upi, "new_payees": cooling,
            "notes": "Transfers between your own accounts have no limit. NEFT has no per-transfer cap within the daily limit."}


def transfer_money(
    *,
    to: str,
    amount: int,
    from_account: str = "ACC-01",
    mode: str | None = None,
    note: str | None = None,
    transfer_date: str | None = None,
    repeat: str = "once",
) -> dict[str, Any]:
    user_id = current_user()
    note = (note or "").strip()[:60] or None
    if repeat not in REPEATS:
        return _error("repeat is once or monthly", repeat="once or monthly")
    when = _today()
    if transfer_date:
        parsed = _parse_date(transfer_date, "transfer_date")
        if isinstance(parsed, dict):
            return parsed
        if parsed < _today():
            return _error("the transfer date can't be in the past", transfer_date="in the past")
        if parsed > _today() + timedelta(days=365):
            return _error("schedule at most a year ahead", transfer_date="too far ahead")
        when = parsed
    if when > _today() or repeat == "monthly":
        # Limits and balance are checked when it runs; the payee, account and amount must be right now.
        plan = _plan_transfer(user_id, from_account, to, amount, mode, check_limits=False)
        if "error" in plan and "balance" not in plan:
            return plan
        source = _resolve_account(user_id, from_account or "ACC-01")
        own = _resolve_account(user_id, to)
        target = own or _resolve_payee(user_id, to)
        with db.transaction():
            s = db.put("scheduled", {"id": _next_id(user_id, "scheduled", "SCH"), "user_id": user_id, "from_account": source["id"],  # type: ignore[index]
                                     "to": target["id"], "amount": _amount(amount), "mode": None if own else (mode or None),  # type: ignore[index]
                                     "note": note, "repeat": repeat, "next_date": when.isoformat(), "status": "active",
                                     "created_at": _now().isoformat(), "runs": []})
        _catch_up(user_id)  # a monthly transfer starting today runs now
        s = db.get("scheduled", user_id, s["id"])
        view = _scheduled_view(user_id, s)  # type: ignore[arg-type]
        return {"scheduled_transfer": view, "message": f"Scheduled {_rupees(view['amount'])} to {view['to_label']} — "
                                                         f"{'every month from ' if repeat == 'monthly' else 'on '}{when:%d %b %Y}."}
    return _execute_transfer(user_id, from_account, to, amount, mode, note)


def _scheduled_view(user_id: str, s: dict[str, Any]) -> dict[str, Any]:
    own = db.get("accounts", user_id, s["to"])
    payee = None if own else db.get("payees", user_id, s["to"])
    to_label = f"{own['name']} {_mask(own['number'])}" if own else (payee["name"] if payee else "removed payee")
    return {"id": s["id"], "from_account": s["from_account"], "from_label": _account_label(user_id, s["from_account"]), "to": s["to"], "to_label": to_label,
            "amount": s["amount"], "note": s["note"], "repeat": s["repeat"], "next_date": s["next_date"] if s["status"] == "active" else None,
            "status": s["status"], "last_runs": s["runs"][-3:]}


def list_scheduled_transfers(*, status: str | None = "active") -> dict[str, Any]:
    user_id = current_user()
    rows = [s for s in db.rows("scheduled", user_id) if not status or s["status"] == status]
    rows.sort(key=lambda s: s["next_date"])
    return {"scheduled_transfers": [_scheduled_view(user_id, s) for s in rows], "total": len(rows)}


def cancel_scheduled_transfer(*, scheduled_id: str) -> dict[str, Any]:
    user_id = current_user()
    s = db.get("scheduled", user_id, str(scheduled_id).strip().upper())
    if s is None:
        return _error(f"not_found: no scheduled transfer {scheduled_id}", scheduled_id="unknown")
    if s["status"] != "active":
        return _error(f"that transfer is already {s['status']}")
    s["status"] = "cancelled"
    db.put("scheduled", s)
    view = _scheduled_view(user_id, s)
    return {"scheduled_transfer": view, "message": f"Cancelled the {'monthly ' if s['repeat'] == 'monthly' else ''}transfer of {_rupees(s['amount'])} to {view['to_label']}."}


# ---------------------------------------------------------------- bills


def _resolve_biller(user_id: str, ref: Any) -> dict[str, Any] | None:
    q = str(ref or "").strip().lower()
    billers = db.rows("billers", user_id)
    for b in billers:
        if q in (b["id"].lower(), b["name"].lower(), b["nickname"].lower(), b["category"].lower(), b["consumer_number"].lower()):
            return b
    hits = [b for b in billers if q and (q in b["name"].lower() or q in b["nickname"].lower() or q in b["category"].lower())]
    return hits[0] if len(hits) == 1 else None


def _biller_view(b: dict[str, Any]) -> dict[str, Any]:
    bill = b["bill"]
    view = {k: b[k] for k in ("id", "name", "category", "nickname", "consumer_number", "autopay", "last_paid")}
    if bill:
        due = date.fromisoformat(bill["due_date"])
        days = (due - _today()).days
        view["bill"] = {**bill, "days_left": days, "status": "overdue" if days < 0 else "due"}
    else:
        view["bill"] = None
    return view


def list_bills(*, status: str | None = None) -> dict[str, Any]:
    user_id = current_user()
    views = [_biller_view(b) for b in db.rows("billers", user_id)]
    if status == "due":
        views = [v for v in views if v["bill"]]
    elif status == "paid":
        views = [v for v in views if not v["bill"]]
    views.sort(key=lambda v: v["bill"]["due_date"] if v["bill"] else "9999")
    return {"billers": views, "total_due": sum(v["bill"]["amount"] for v in views if v["bill"])}


def _pay_biller(user_id: str, b: dict[str, Any], amount: int, account_id: str, autopay: bool = False) -> dict[str, Any]:
    t = _post(user_id, account_id, "debit", amount, f"{b['name']} bill — {b['consumer_number']}" + (" (autopay)" if autopay else ""),
              "utilities", "bill_pay", biller_id=b["id"], merchant=b["name"])
    bill = b["bill"]
    remaining = bill["amount"] - amount if bill else 0
    b["bill"] = {**bill, "amount": remaining} if bill and remaining > 0 else None
    b["last_paid"] = {"amount": amount, "date": _today().isoformat()}
    db.put("billers", b)
    return t


def pay_bill(*, biller_id: str, amount: int | None = None, from_account: str = "ACC-01") -> dict[str, Any]:
    user_id = current_user()
    b = _resolve_biller(user_id, biller_id)
    if b is None:
        return _error(f"not_found: no biller {biller_id}", biller_id="unknown biller")
    source = _resolve_account(user_id, from_account or "ACC-01")
    if source is None:
        return _error(f"no account {from_account}", from_account="unknown account")
    if amount in (None, ""):
        if not b["bill"]:
            return _error(f"nothing is due for {b['nickname']} — give an amount to pay in advance", amount="nothing due")
        value: int | dict[str, Any] = b["bill"]["amount"]
    else:
        value = _amount(amount)
    if isinstance(value, dict):
        return value
    if b["category"] == "Insurance" and b["bill"] and value != b["bill"]["amount"]:
        return _error(f"insurance premiums are paid in full ({_rupees(b['bill']['amount'])})", amount="pay the full premium")
    with db.transaction():
        balance = _balance(user_id, source["id"])
        if balance < value:
            return _error(f"not enough money in {source['name']} — balance {_rupees(balance)}", amount="more than the balance")
        t = _pay_biller(user_id, b, value, source["id"])
    view = _biller_view(db.get("billers", user_id, b["id"]))  # type: ignore[arg-type]
    left = view["bill"]["amount"] if view["bill"] else 0
    return {"payment": _txn_view(user_id, t), "biller": view,
            "message": f"Paid {_rupees(value)} to {b['name']} ({b['nickname']})." + (f" {_rupees(left)} is still due." if left else "")}


def set_bill_autopay(*, biller_id: str, enabled: bool, max_amount: int | None = None, from_account: str | None = None) -> dict[str, Any]:
    user_id = current_user()
    b = _resolve_biller(user_id, biller_id)
    if b is None:
        return _error(f"not_found: no biller {biller_id}", biller_id="unknown biller")
    auto = dict(b["autopay"])
    auto["enabled"] = _bool(enabled)
    if max_amount not in (None, ""):
        cap = _amount(max_amount, "max_amount")
        if isinstance(cap, dict):
            return cap
        auto["max_amount"] = cap
    if from_account:
        source = _resolve_account(user_id, from_account)
        if source is None:
            return _error(f"no account {from_account}", from_account="unknown account")
        auto["from_account"] = source["id"]
    b["autopay"] = auto
    if b["bill"]:
        b["bill"].pop("autopay_skipped", None)
    db.put("billers", b)
    state = f"on — bills up to {_rupees(auto['max_amount'])} are paid on the due date from {_account_label(user_id, auto['from_account'])}" if auto["enabled"] else "off"
    return {"biller": _biller_view(b), "message": f"Autopay for {b['nickname']} is {state}."}


# ---------------------------------------------------------------- cards


def _resolve_card(user_id: str, ref: Any) -> dict[str, Any] | None:
    q = str(ref or "").strip().lower()
    cards = db.rows("cards", user_id)
    for c in cards:
        if q in (c["id"].lower(), c["last4"]):
            return c
    live = [c for c in cards if c["status"] not in ("blocked",)]
    hits = [c for c in live if q and (q == c["kind"] or q in c["name"].lower() or q == c["network"].lower())]
    return hits[0] if len(hits) == 1 else None


def _card_owed(user_id: str, card_id: str, until: str | None = None) -> int:
    return sum((t["amount"] if t["direction"] == "debit" else -t["amount"]) for t in db.rows("transactions", user_id)
               if t["account_id"] == card_id and (until is None or t["posted_at"] <= until))


def _ledger_id(card: dict[str, Any]) -> str:
    """Credit card spending is on one ledger (the first credit card's id), carried over to replacements."""
    return card.get("ledger_id") or card["id"]


def _statement(user_id: str, card: dict[str, Any], close: date) -> dict[str, Any]:
    ledger = _ledger_id(card)
    prev = add_months(close, -1)
    close_end = datetime.combine(close, time(23, 59, 59), IST).isoformat()
    prev_end = datetime.combine(prev, time(23, 59, 59), IST).isoformat()
    in_cycle = [t for t in _txns(user_id) if t["account_id"] == ledger and prev_end < t["posted_at"] <= close_end]
    closing = _card_owed(user_id, ledger, close_end)
    opening = _card_owed(user_id, ledger, prev_end)
    after = [t for t in db.rows("transactions", user_id) if t["account_id"] == ledger and t["direction"] == "credit" and t["posted_at"] > close_end]
    paid_since = sum(t["amount"] for t in after)
    total_due = max(0, closing - paid_since)
    minimum = min(max(0, closing), max(200, round(closing * 0.05))) if closing > 0 else 0
    min_due = max(0, minimum - paid_since)
    due_date = close + timedelta(days=card["due_after_days"])
    status = "paid" if total_due == 0 else ("overdue" if due_date < _today() else ("minimum_paid" if min_due == 0 else "due"))
    return {"statement_date": close.isoformat(), "period_from": (prev + timedelta(days=1)).isoformat(), "period_to": close.isoformat(),
            "opening_balance": opening, "purchases": sum(t["amount"] for t in in_cycle if t["direction"] == "debit"),
            "payments_and_refunds": sum(t["amount"] for t in in_cycle if t["direction"] == "credit"), "statement_balance": closing,
            "minimum_due": minimum, "due_date": due_date.isoformat(), "paid_since_statement": paid_since, "total_due_now": total_due,
            "minimum_due_now": min_due, "status": status, "transactions": [_txn_view(user_id, t) for t in in_cycle[::-1]]}


def _last_close(card: dict[str, Any], today: date | None = None) -> date:
    today = today or _today()
    close = date(today.year, today.month, card["statement_day"])
    return close if close < today else add_months(close, -1)


def _card_view(user_id: str, c: dict[str, Any], detail: bool = False) -> dict[str, Any]:
    view = {k: c[k] for k in ("id", "kind", "name", "network", "last4", "expires", "status", "controls", "limits")}
    view["label"] = f"{c['name']} ••{c['last4']}"
    for k in ("arrives_on", "replaced_by", "replaces", "blocked_reason", "blocked_at"):
        if c.get(k):
            view[k] = c[k]
    if c["kind"] == "debit":
        view["account_id"] = c["account_id"]
        view["account_label"] = _account_label(user_id, c["account_id"])
        view["account_balance"] = _balance(user_id, c["account_id"])
    else:
        owed = _card_owed(user_id, _ledger_id(c))
        last = _statement(user_id, c, _last_close(c))
        view.update(credit_limit=c["credit_limit"], outstanding=owed, available_credit=c["credit_limit"] - owed, reward_points=c["reward_points"],
                    statement={k: last[k] for k in ("statement_date", "statement_balance", "minimum_due", "due_date", "total_due_now", "minimum_due_now", "status")},
                    unbilled=owed - last["total_due_now"])
    if detail:
        if c["kind"] == "credit":
            unbilled = [t for t in _txns(user_id) if t["account_id"] == _ledger_id(c) and t["posted_at"] > datetime.combine(_last_close(c), time(23, 59, 59), IST).isoformat()]
            view["unbilled_transactions"] = [_txn_view(user_id, t) for t in unbilled[::-1][:20]]
        else:
            spends = [t for t in _txns(user_id) if t["account_id"] == c["account_id"] and t["channel"] in ("card", "atm")]
            view["recent_transactions"] = [_txn_view(user_id, t) for t in spends[::-1][:10]]
        view["limit_maximums"] = {k: (c["credit_limit"] if c["kind"] == "credit" else v) for k, v in CARD_LIMIT_MAX.items() if k in c["limits"]}
    return view


def list_cards() -> dict[str, Any]:
    user_id = current_user()
    return {"cards": [_card_view(user_id, c) for c in db.rows("cards", user_id)]}


def get_card(*, card_id: str) -> dict[str, Any]:
    user_id = current_user()
    c = _resolve_card(user_id, card_id)
    if c is None:
        return _error(f"not_found: no card {card_id}", card_id="unknown card")
    return {"card": _card_view(user_id, c, detail=True)}


def set_card_lock(*, card_id: str, locked: bool) -> dict[str, Any]:
    user_id = current_user()
    c = _resolve_card(user_id, card_id)
    if c is None:
        return _error(f"not_found: no card {card_id}", card_id="unknown card")
    if c["status"] in ("blocked", "on_the_way"):
        return _error(f"this card is {c['status'].replace('_', ' ')} and can't be {'locked' if _bool(locked) else 'unlocked'}")
    c["status"] = "locked" if _bool(locked) else "active"
    db.put("cards", c)
    msg = (f"{c['name']} ••{c['last4']} is locked: no new payments or withdrawals until you unlock it. Autopays and standing instructions still run."
           if c["status"] == "locked" else f"{c['name']} ••{c['last4']} is unlocked.")
    return {"card": _card_view(user_id, c), "message": msg}


def update_card_controls(
    *,
    card_id: str,
    online: bool | None = None,
    international: bool | None = None,
    contactless: bool | None = None,
    atm: bool | None = None,
    atm_daily_limit: int | None = None,
    pos_daily_limit: int | None = None,
    online_daily_limit: int | None = None,
) -> dict[str, Any]:
    user_id = current_user()
    c = _resolve_card(user_id, card_id)
    if c is None:
        return _error(f"not_found: no card {card_id}", card_id="unknown card")
    if c["status"] == "blocked":
        return _error("this card is blocked; change the controls on its replacement")
    changes = []
    for key, value in (("online", online), ("international", international), ("contactless", contactless), ("atm", atm)):
        if value is None or value == "":
            continue
        if key not in c["controls"]:
            return _error(f"{key} isn't a control on a {c['kind']} card", **{key: "not available"})
        c["controls"][key] = _bool(value)
        changes.append(f"{key} {'on' if c['controls'][key] else 'off'}")
    for key, value in (("atm_daily", atm_daily_limit), ("pos_daily", pos_daily_limit), ("online_daily", online_daily_limit)):
        if value in (None, ""):
            continue
        field = f"{key}_limit"
        if key not in c["limits"]:
            return _error(f"a {c['kind']} card has no {key.replace('_', ' ')} limit", **{field: "not available"})
        number = _int_or_error(value, field)
        if isinstance(number, dict):
            return number
        cap = c["credit_limit"] if c["kind"] == "credit" else CARD_LIMIT_MAX[key]
        if not 0 <= number <= cap:
            return _error(f"the {key.replace('_', ' ')} limit is between ₹0 and {_rupees(cap)}", **{field: f"0–{cap}"})
        c["limits"][key] = number
        changes.append(f"{key.replace('_', ' ')} limit {_rupees(number)}")
    if not changes:
        return _error("say what to change: online, international, contactless, atm, or a daily limit")
    db.put("cards", c)
    return {"card": _card_view(user_id, c), "message": f"Updated {c['name']} ••{c['last4']}: {', '.join(changes)}."}


def _int_or_error(value: Any, field: str) -> int | dict[str, Any]:
    try:
        return int(float(str(value).replace(",", "").replace("₹", "")))
    except (TypeError, ValueError):
        return _error(f"{field} must be a number", **{field: "not a number"})


def report_card_lost(*, card_id: str, reason: str = "lost") -> dict[str, Any]:
    user_id = current_user()
    c = _resolve_card(user_id, card_id)
    if c is None:
        return _error(f"not_found: no card {card_id}", card_id="unknown card")
    if reason not in REPORT_REASONS:
        return _error("reason is lost, stolen or damaged", reason="lost, stolen or damaged")
    if c["status"] == "blocked":
        return _error("this card is already blocked")
    with db.transaction():
        new_id = _next_id(user_id, "cards", "CRD")
        digits = f"{(int(c['last4']) * 37 + 1931) % 10000:04d}"
        today = _today()
        replacement = {**c, "id": new_id, "last4": digits, "status": "on_the_way", "arrives_on": (today + timedelta(days=DELIVERY_DAYS)).isoformat(),
                       "expires": f"{today.month:02d}/{(today.year + 5) % 100:02d}", "replaces": c["id"], "controls": dict(c["controls"]), "limits": dict(c["limits"])}
        replacement.pop("blocked_reason", None)
        if c["kind"] == "credit":
            replacement["ledger_id"] = _ledger_id(c)
        if reason == "stolen":
            replacement["controls"]["international"] = False
        c.update(status="blocked", blocked_reason=reason, blocked_at=_now().isoformat(), replaced_by=new_id)
        db.put("cards", c)
        db.put("cards", replacement)
        fee = REPLACEMENT_FEE if c["kind"] == "debit" and reason in ("lost", "stolen") else 0
        if fee:
            _post(user_id, c["account_id"], "debit", fee, f"Debit card replacement fee (incl. GST) — ••{c['last4']}", "fees", "fee")
    return {"blocked_card": _card_view(user_id, c), "replacement": _card_view(user_id, replacement), "fee": fee,
            "message": f"Blocked ••{c['last4']} for good. A new card ending {digits} arrives at your registered address by "
                       f"{date.fromisoformat(replacement['arrives_on']):%d %b}" + (f"; a {_rupees(fee)} replacement fee was charged." if fee else ".")
                       + (" Raise a dispute for any payment you didn't make." if reason == "stolen" else "")}


def get_credit_card_statement(*, card_id: str = "CRD-02", statement_month: str | None = None) -> dict[str, Any]:
    user_id = current_user()
    c = _resolve_card(user_id, card_id)
    if c is None or c["kind"] != "credit":
        return _error(f"not_found: no credit card {card_id}", card_id="unknown credit card")
    close = _last_close(c)
    if statement_month:
        if not re.fullmatch(r"\d{4}-\d{2}", statement_month[:7]):
            return _error("statement_month looks like 2026-10", statement_month="YYYY-MM")
        y, m = (int(x) for x in statement_month[:7].split("-"))
        close = date(y, m, c["statement_day"])
        if close >= _today():
            return _error("that statement isn't out yet; ask for unbilled spending with get_card", statement_month="not out yet")
    return {"card": f"{c['name']} ••{c['last4']}", "statement": _statement(user_id, c, close)}


def pay_credit_card(*, card_id: str = "CRD-02", amount: int | None = None, pay: str = "total_due", from_account: str = "ACC-01") -> dict[str, Any]:
    user_id = current_user()
    c = _resolve_card(user_id, card_id)
    if c is None or c["kind"] != "credit":
        return _error(f"not_found: no credit card {card_id}", card_id="unknown credit card")
    source = _resolve_account(user_id, from_account or "ACC-01")
    if source is None:
        return _error(f"no account {from_account}", from_account="unknown account")
    ledger = _ledger_id(c)
    owed = _card_owed(user_id, ledger)
    st = _statement(user_id, c, _last_close(c))
    if amount not in (None, ""):
        value = _amount(amount)
    elif pay == "minimum_due":
        value = st["minimum_due_now"]
    elif pay == "outstanding":
        value = owed
    elif pay == "total_due":
        value = st["total_due_now"]
    else:
        return _error("pay is total_due, minimum_due or outstanding", pay="unknown")
    if isinstance(value, dict):
        return value
    if value <= 0:
        return _error("nothing is due on this card right now", amount="nothing due")
    if value > max(owed, 0):
        return _error(f"that's more than the {_rupees(owed)} you owe", amount="more than you owe")
    with db.transaction():
        balance = _balance(user_id, source["id"])
        if balance < value:
            return _error(f"not enough money in {source['name']} — balance {_rupees(balance)}", amount="more than the balance")
        t = _post(user_id, source["id"], "debit", value, f"{c['name']} ••{c['last4']} payment", "card_payment", "card_payment", card_id=c["id"])
        _post(user_id, ledger, "credit", value, "Payment received — thank you", "card_payment", "card_payment")
    after = _statement(user_id, c, _last_close(c))
    return {"payment": _txn_view(user_id, t), "statement": {k: after[k] for k in ("total_due_now", "minimum_due_now", "due_date", "status")},
            "outstanding_after": owed - value, "message": f"Paid {_rupees(value)} towards ••{c['last4']}." + (" The statement is fully paid." if after["status"] == "paid" else "")}


# ---------------------------------------------------------------- fixed deposits


def _rate_for_days(days: int) -> float | None:
    for lo, hi, rate in FD_RATES:
        if lo <= days <= hi:
            return rate
    return None


def _new_deposit(user_id: str, deposit_id: str, principal: int, opened: date, months: int, payout: str, auto_renew: bool, account_id: str) -> dict[str, Any]:
    maturity = add_months(opened, months)
    rate = _rate_for_days((maturity - opened).days) or FD_RATES[-1][2]
    return {"id": deposit_id, "user_id": user_id, "principal": int(principal), "rate": rate, "opened": opened.isoformat(), "tenure_months": months,
            "maturity_date": maturity.isoformat(), "payout": payout, "auto_renew": auto_renew, "account_id": account_id, "status": "active",
            "payouts_made": 0, "interest_paid": 0}


def _compound(principal: int, rate: float, days: int) -> int:
    return round(principal * (1 + rate / 400) ** (4 * days / 365))


def _quarter_interest(d: dict[str, Any]) -> int:
    return round(d["principal"] * d["rate"] / 400)


def _maturity_value(d: dict[str, Any]) -> int:
    days = (date.fromisoformat(d["maturity_date"]) - date.fromisoformat(d["opened"])).days
    if d["payout"] == "quarterly":
        return d["principal"]
    return _compound(d["principal"], d["rate"], days)


def _deposit_view(d: dict[str, Any]) -> dict[str, Any]:
    view = {k: d[k] for k in ("id", "principal", "rate", "opened", "tenure_months", "maturity_date", "payout", "auto_renew", "account_id", "status", "interest_paid")}
    maturity_value = _maturity_value(d)
    view["maturity_amount"] = maturity_value
    view["total_interest"] = (maturity_value - d["principal"]) if d["payout"] == "cumulative" else _quarter_interest(d) * (d["tenure_months"] // 3)
    if d["payout"] == "quarterly":
        view["quarterly_interest"] = _quarter_interest(d)
    if d["status"] == "active":
        view["days_to_maturity"] = (date.fromisoformat(d["maturity_date"]) - _today()).days
    for k in ("closed_on", "paid_out", "renewed_as", "closed_early"):
        if d.get(k):
            view[k] = d[k]
    return view


def list_fixed_deposits(*, status: str | None = None) -> dict[str, Any]:
    user_id = current_user()
    rows = [d for d in db.rows("deposits", user_id) if not status or d["status"] == status]
    views = [_deposit_view(d) for d in rows]
    return {"deposits": views, "total_active": sum(v["principal"] for v in views if v["status"] == "active")}


def get_fd_rates() -> dict[str, Any]:
    return {"rates": [{"from_days": lo, "to_days": hi, "rate": rate} for lo, hi, rate in FD_RATES], "minimum": FD_MIN,
            "premature_penalty": f"{FD_PENALTY}% off the rate for the time held", "payouts": FD_PAYOUTS,
            "note": "Interest compounds quarterly for cumulative deposits. Rates for the general public, % a year."}


def get_fd_quote(*, amount: int, tenure_months: int, payout: str = "cumulative") -> dict[str, Any]:
    value = _amount(amount)
    if isinstance(value, dict):
        return value
    months = _int_or_error(tenure_months, "tenure_months")
    if isinstance(months, dict):
        return months
    if not 1 <= months <= 120:
        return _error("tenure is 1 to 120 months", tenure_months="1–120")
    if payout not in FD_PAYOUTS:
        return _error("payout is cumulative or quarterly", payout="cumulative or quarterly")
    if not FD_MIN <= value <= FD_MAX:
        return _error(f"a deposit is {_rupees(FD_MIN)} to {_rupees(FD_MAX)}", amount="out of range")
    d = _new_deposit("-", "FD-QUOTE", value, _today(), months, payout, False, "ACC-01")
    view = _deposit_view(d)
    return {"quote": {k: view[k] for k in ("principal", "rate", "tenure_months", "maturity_date", "payout", "maturity_amount", "total_interest")}
            | ({"quarterly_interest": view["quarterly_interest"]} if payout == "quarterly" else {})}


def open_fixed_deposit(*, amount: int, tenure_months: int, payout: str = "cumulative", auto_renew: bool = False, from_account: str = "ACC-01") -> dict[str, Any]:
    user_id = current_user()
    quote = get_fd_quote(amount=amount, tenure_months=tenure_months, payout=payout)
    if "error" in quote:
        return quote
    source = _resolve_account(user_id, from_account or "ACC-01")
    if source is None:
        return _error(f"no account {from_account}", from_account="unknown account")
    value = quote["quote"]["principal"]
    with db.transaction():
        balance = _balance(user_id, source["id"])
        if balance < value:
            return _error(f"not enough money in {source['name']} — balance {_rupees(balance)}", amount="more than the balance")
        d = _new_deposit(user_id, _next_id(user_id, "deposits", "FD"), value, _today(), int(tenure_months), payout, _bool(auto_renew), source["id"])
        db.put("deposits", d)
        _post(user_id, source["id"], "debit", value, f"Fixed deposit {d['id']} opened", "investments", "fd", deposit_id=d["id"])
    view = _deposit_view(d)
    return {"deposit": view, "message": f"Opened {d['id']}: {_rupees(value)} at {d['rate']}% for {d['tenure_months']} months, "
                                        f"maturing {date.fromisoformat(d['maturity_date']):%d %b %Y} at {_rupees(view['maturity_amount'])}."}


def _closure(d: dict[str, Any]) -> dict[str, Any]:
    held = (_today() - date.fromisoformat(d["opened"])).days
    base = _rate_for_days(held)
    rate = max(0.0, (base or 0) - FD_PENALTY) if held >= 7 else 0.0
    earned = (_compound(d["principal"], rate, held) - d["principal"]) if d["payout"] == "cumulative" else round(d["principal"] * rate / 100 * held / 365)
    payout = d["principal"] + earned - d["interest_paid"]
    return {"deposit_id": d["id"], "days_held": held, "rate_for_time_held": base or 0.0, "penalty": FD_PENALTY if held >= 7 else None,
            "effective_rate": rate, "interest_earned": earned, "interest_already_paid": d["interest_paid"], "payout": payout,
            "payout_at_maturity": _maturity_value(d), "maturity_date": d["maturity_date"],
            "credit_to": d["account_id"]}


def get_fd_closure_quote(*, deposit_id: str) -> dict[str, Any]:
    user_id = current_user()
    d = db.get("deposits", user_id, str(deposit_id).strip().upper())
    if d is None:
        return _error(f"not_found: no deposit {deposit_id}", deposit_id="unknown deposit")
    if d["status"] != "active":
        return _error(f"{d['id']} is already {d['status']}")
    return {"closure": _closure(d)}


def close_fixed_deposit(*, deposit_id: str) -> dict[str, Any]:
    user_id = current_user()
    d = db.get("deposits", user_id, str(deposit_id).strip().upper())
    if d is None:
        return _error(f"not_found: no deposit {deposit_id}", deposit_id="unknown deposit")
    if d["status"] != "active":
        return _error(f"{d['id']} is already {d['status']}")
    with db.transaction():
        q = _closure(d)
        _post(user_id, d["account_id"], "credit", q["payout"], f"Fixed deposit {d['id']} closed early", "investments", "fd", deposit_id=d["id"])
        d.update(status="closed", closed_on=_today().isoformat(), paid_out=q["payout"], closed_early=True)
        db.put("deposits", d)
    return {"closure": q, "deposit": _deposit_view(d),
            "message": f"Closed {d['id']} early: {_rupees(q['payout'])} credited to {_account_label(user_id, d['account_id'])} (interest at {q['effective_rate']}%)."}


# ---------------------------------------------------------------- disputes


def _disputable(t: dict[str, Any], dispute: dict[str, Any] | None) -> tuple[bool, str]:
    if dispute and dispute["status"] in ("under_review", "resolved"):
        return False, f"already disputed ({dispute['id']}, {dispute['status'].replace('_', ' ')})"
    if t["direction"] != "debit":
        return False, "only payments out can be disputed"
    if t["channel"] not in DISPUTABLE_CHANNELS:
        return False, "transfers you made to payees can't be disputed; contact the payee"
    if (_today() - _day_of(t["posted_at"])).days > DISPUTE_WINDOW_DAYS:
        return False, f"older than {DISPUTE_WINDOW_DAYS} days"
    return True, ""


def raise_dispute(*, transaction_id: str, reason: str, details: str | None = None) -> dict[str, Any]:
    user_id = current_user()
    t = _find_txn(user_id, transaction_id)
    if t is None:
        return _error(f"not_found: no transaction {transaction_id}", transaction_id="unknown transaction")
    if reason not in DISPUTE_REASONS:
        return _error(f"reason is one of {', '.join(DISPUTE_REASONS)}", reason="unknown reason")
    existing = next((d for d in db.rows("disputes", user_id) if d["transaction_id"] == t["id"]), None)
    ok, why = _disputable(t, existing)
    if not ok:
        return _error(f"this transaction can't be disputed: {why}", transaction_id=why)
    if reason in ("other", "not_received", "wrong_amount") and len((details or "").strip()) < 10:
        return _error("describe what happened in a sentence or two", details="required for this reason")
    with db.transaction():
        dispute = {"id": _next_id(user_id, "disputes", "DSP"), "user_id": user_id, "transaction_id": t["id"], "reason": reason,
                   "details": (details or "").strip()[:1000] or None, "amount": t["amount"], "merchant": t.get("merchant") or t["description"],
                   "status": "under_review", "raised_at": _now().isoformat(),
                   "expected_by": (_today() + timedelta(days=DISPUTE_RESOLUTION_DAYS)).isoformat(), "provisional_credit": 0}
        duplicate = reason == "charged_twice" and any(
            x["id"] != t["id"] and x.get("merchant") == t.get("merchant") and x["amount"] == t["amount"] and x["posted_at"][:10] == t["posted_at"][:10]
            for x in db.rows("transactions", user_id))
        if duplicate:
            _post(user_id, t["account_id"], "credit", t["amount"], f"Provisional credit — dispute {dispute['id']}", "refunds", "refund", dispute_id=dispute["id"])
            dispute["provisional_credit"] = t["amount"]
        db.put("disputes", dispute)
    next_steps = []
    if reason == "unauthorized" and t["channel"] == "card":
        next_steps.append("Lock or block the card so no more payments go through.")
    msg = f"Dispute {dispute['id']} raised for {_rupees(t['amount'])} at {dispute['merchant']}. We'll update you by {date.fromisoformat(dispute['expected_by']):%d %b}."
    if duplicate:
        msg += f" We found the duplicate charge and credited {_rupees(t['amount'])} back while we confirm with the merchant."
    return {"dispute": dispute, "next_steps": next_steps, "message": msg}


def list_disputes(*, status: str | None = None) -> dict[str, Any]:
    user_id = current_user()
    rows = [d for d in db.rows("disputes", user_id) if not status or d["status"] == status]
    return {"disputes": rows[::-1], "total": len(rows)}


# ---------------------------------------------------------------- the customer, overview, search


def get_my_context() -> dict[str, Any]:
    user_id = current_user()
    customer = db.get("customers", user_id, "me")
    accounts = list_accounts()
    cards = [_card_view(user_id, c) for c in db.rows("cards", user_id)]
    nxt = list_scheduled_transfers()["scheduled_transfers"][:1]
    return {
        "customer": {k: customer[k] for k in ("name", "email", "phone", "city", "customer_number", "branch", "customer_since", "relationship_manager")},  # type: ignore[index]
        "accounts": [{k: a[k] for k in ("id", "name", "label", "balance")} for a in accounts["accounts"]],
        "total_balance": accounts["total_balance"],
        "cards": [{k: c[k] for k in ("id", "kind", "label", "last4", "status")} for c in cards],
        "payees": len(db.rows("payees", user_id)),
        "next_scheduled_transfer": nxt[0] if nxt else None,
        "today": _today().isoformat(),
    }


def list_attention_items() -> dict[str, Any]:
    user_id = current_user()
    today = _today()
    items = []
    for b in db.rows("billers", user_id):
        view = _biller_view(b)
        bill = view["bill"]
        if not bill:
            continue
        if b["autopay"]["enabled"] and not bill.get("autopay_skipped"):
            if bill["days_left"] <= 3:
                items.append({"kind": "autopay_soon", "ref": b["id"], "href": "/bills", "text": f"{b['nickname']}: {_rupees(bill['amount'])} will be paid by autopay on {date.fromisoformat(bill['due_date']):%d %b}."})
        elif bill["days_left"] <= 7:
            when = "overdue" if bill["days_left"] < 0 else ("due today" if bill["days_left"] == 0 else f"due in {bill['days_left']} day(s)")
            extra = f" (autopay skipped: {bill['autopay_skipped']})" if bill.get("autopay_skipped") else ""
            items.append({"kind": "bill_due", "ref": b["id"], "href": "/bills", "text": f"{b['nickname']} ({b['name']}): {_rupees(bill['amount'])} {when}{extra}."})
    for c in db.rows("cards", user_id):
        if c["kind"] == "credit" and c["status"] != "blocked":
            st = _statement(user_id, c, _last_close(c))
            days = (date.fromisoformat(st["due_date"]) - today).days
            if st["total_due_now"] > 0 and days <= 10:
                items.append({"kind": "card_due", "ref": c["id"], "href": f"/cards/{c['id']}",
                              "text": f"Credit card ••{c['last4']}: {_rupees(st['total_due_now'])} {'overdue' if days < 0 else f'due {date.fromisoformat(st['due_date']):%d %b}'} (minimum {_rupees(st['minimum_due_now'])})."})
        if c["status"] == "locked":
            items.append({"kind": "card_locked", "ref": c["id"], "href": f"/cards/{c['id']}", "text": f"{c['name']} ••{c['last4']} is locked."})
        if c["status"] == "on_the_way":
            items.append({"kind": "card_on_the_way", "ref": c["id"], "href": f"/cards/{c['id']}", "text": f"Your new card ending {c['last4']} arrives by {date.fromisoformat(c['arrives_on']):%d %b}."})
    for d in db.rows("deposits", user_id):
        if d["status"] == "active":
            days = (date.fromisoformat(d["maturity_date"]) - today).days
            if days <= 45:
                items.append({"kind": "fd_maturing", "ref": d["id"], "href": "/deposits",
                              "text": f"Fixed deposit {d['id']} ({_rupees(d['principal'])}) matures on {date.fromisoformat(d['maturity_date']):%d %b}" + (" and renews automatically." if d["auto_renew"] else " — it will be paid to your savings account.")})
    for a in _accounts(user_id):
        bal = _balance(user_id, a["id"])
        if bal < a["min_balance"]:
            items.append({"kind": "low_balance", "ref": a["id"], "href": f"/accounts/{a['id']}", "text": f"{a['name']} is below the {_rupees(a['min_balance'])} average balance ({_rupees(bal)})."})
    for s in db.rows("scheduled", user_id):
        if s["status"] == "active" and (date.fromisoformat(s["next_date"]) - today).days <= 3:
            view = _scheduled_view(user_id, s)
            short = _balance(user_id, s["from_account"]) < s["amount"]
            items.append({"kind": "scheduled_soon", "ref": s["id"], "href": "/transfer", "text": f"{_rupees(s['amount'])} to {view['to_label']} goes on {date.fromisoformat(s['next_date']):%d %b}" + (" — not enough balance yet." if short else ".")})
    for d in db.rows("disputes", user_id):
        if d["status"] == "under_review":
            items.append({"kind": "dispute_open", "ref": d["id"], "href": f"/transactions/{d['transaction_id']}", "text": f"Dispute {d['id']} ({_rupees(d['amount'])}, {d['merchant']}) is under review."})
    return {"items": items, "total": len(items)}


def get_overview() -> dict[str, Any]:
    ctx = get_my_context()
    return {"customer": ctx["customer"]["name"], "accounts": ctx["accounts"], "total_balance": ctx["total_balance"], "cards": list_cards()["cards"],
            "this_month": {k: v for k, v in get_month_summary().items() if k in ("income", "spending", "saved", "top_categories")},
            "recent_transactions": list_transactions(limit=6)["transactions"], "attention": list_attention_items()["items"]}


def search_all(*, query: str) -> dict[str, Any]:
    user_id = current_user()
    q = query.strip().lower()
    hits: list[dict[str, Any]] = []
    for a in _accounts(user_id):
        if q in a["name"].lower() or q in a["number"]:
            hits.append({"type": "account", "id": a["id"], "title": f"{a['name']} {_mask(a['number'])}"})
    for c in db.rows("cards", user_id):
        if q in c["name"].lower() or q == c["last4"] or q == c["kind"]:
            hits.append({"type": "card", "id": c["id"], "title": f"{c['name']} ••{c['last4']} ({c['status']})"})
    for p in db.rows("payees", user_id):
        if q in p["name"].lower() or q in str(p.get("nickname") or "").lower():
            hits.append({"type": "payee", "id": p["id"], "title": p["name"]})
    for b in db.rows("billers", user_id):
        if q in b["name"].lower() or q in b["nickname"].lower() or q in b["category"].lower():
            hits.append({"type": "biller", "id": b["id"], "title": f"{b['nickname']} — {b['name']}"})
    for d in db.rows("deposits", user_id):
        if q in d["id"].lower() or q in ("fd", "fixed deposit", "deposit"):
            hits.append({"type": "deposit", "id": d["id"], "title": f"{d['id']} {_rupees(d['principal'])} ({d['status']})"})
    merchants: dict[str, int] = {}
    for t in _txns(user_id)[::-1]:
        if q in t["description"].lower() or q in str(t.get("merchant") or "").lower() or q == t["id"].lower() or q == t["reference"].lower():
            merchants[t.get("merchant") or t["description"]] = merchants.get(t.get("merchant") or t["description"], 0) + 1
            if len([h for h in hits if h["type"] == "transaction"]) < 8:
                hits.append({"type": "transaction", "id": t["id"], "title": f"{t['description']} · {_rupees(t['amount'])} · {t['posted_at'][:10]}"})
    return {"hits": hits[:30], "total": len(hits), "matching_transactions_by_merchant": merchants}


def describe_data() -> dict[str, Any]:
    return {
        "bank": "Kestrel Bank (demo). Currency INR, whole rupees; times IST.",
        "accounts": "Premier Savings (salary account, debit card) and Joint Savings with Meera. Each needs a ₹10,000 average balance (a warning, not a block).",
        "categories": CATEGORIES,
        "channels": list(CHANNELS),
        "transfers": {
            "modes": MODES,
            "arrival": ARRIVAL,
            "limits": LIMITS,
            "rules": f"UPI payees get UPI; bank payees get IMPS (up to {_rupees(LIMITS['imps_per_transfer'])}) or NEFT. Own-account transfers have no limit. "
                     f"A payee added less than {NEW_PAYEE_HOURS} hours ago can receive at most {_rupees(LIMITS['new_payee_cap'])} in total. No fees. "
                     "A future date or repeat=monthly creates a scheduled transfer (standing instruction) that runs on its date.",
        },
        "payees": "Bank account (account number 9–18 digits + IFSC) or UPI ID. Removing a payee cancels its scheduled transfers.",
        "bills": "Billers have an open bill with a due date; pay the full amount or part of it (insurance premiums in full). Autopay pays on the due date when the bill is within its limit.",
        "cards": {
            "controls": "online, international, contactless (both cards), atm (debit only)",
            "limits": {"debit maximums": CARD_LIMIT_MAX, "credit": "up to the credit limit"},
            "lock": "Locking stops new card payments until unlocked; autopays still run.",
            "lost_or_stolen": f"Blocks the card for good and sends a replacement in {DELIVERY_DAYS} days; debit card replacement costs {_rupees(REPLACEMENT_FEE)} (incl. GST) when lost or stolen.",
            "credit_card": "Statement on the 15th, due 20 days later. Minimum due is 5% of the statement (at least ₹200). Pay total due, minimum due, the full outstanding, or any amount.",
        },
        "fixed_deposits": {"rates": get_fd_rates()["rates"], "minimum": FD_MIN, "payouts": FD_PAYOUTS,
                           "premature_closure": f"Interest at the rate for the time held minus {FD_PENALTY}%; nothing before 7 days."},
        "disputes": {"reasons": DISPUTE_REASONS, "window_days": DISPUTE_WINDOW_DAYS, "resolution_days": DISPUTE_RESOLUTION_DAYS,
                     "rules": "Card, UPI, ATM, bill and auto-debit payments can be disputed; a duplicate charge gets a provisional credit at once."},
    }
