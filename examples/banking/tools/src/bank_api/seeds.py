"""Kestrel Bank's demo data: the bank's catalogues (categories, billers, FD rates, IFSC prefixes)
and the starting point for every new customer — accounts, cards, payees, billers, deposits and six
months of transactions generated around today's date.

Every customer starts as Arjun Mehta (Pune): a savings account (salary comes in on the 1st), a joint
account with Meera, a debit card and a credit card, five payees, two standing instructions, five
billers and two fixed deposits — one maturing soon.
"""

from __future__ import annotations

import calendar
import random
from datetime import date, datetime, time, timedelta
from typing import Any

DEFAULT_CUSTOMER = {
    "name": "Arjun Mehta",
    "email": "arjun.mehta@example.com",
    "phone": "+91 98220 41873",
    "city": "Pune",
    "customer_number": "KST-88142035",
    "branch": "Baner, Pune",
    "customer_since": "2016-08-11",
    "relationship_manager": "Nisha Rao",
}

CATEGORIES = {
    "income": "Income",
    "rent": "Rent",
    "groceries": "Groceries",
    "dining": "Food & dining",
    "shopping": "Shopping",
    "transport": "Transport",
    "fuel": "Fuel",
    "utilities": "Bills & utilities",
    "subscriptions": "Subscriptions",
    "health": "Health",
    "entertainment": "Entertainment",
    "travel": "Travel",
    "education": "Education",
    "family": "Family",
    "investments": "Investments",
    "cash": "Cash",
    "transfers": "Transfers",
    "card_payment": "Card payment",
    "interest": "Interest",
    "fees": "Fees & charges",
    "refunds": "Refunds",
}

# Bank name from the first four letters of an IFSC.
BANKS = {
    "KSTL": "Kestrel Bank",
    "HDFC": "HDFC Bank",
    "ICIC": "ICICI Bank",
    "SBIN": "State Bank of India",
    "UTIB": "Axis Bank",
    "KKBK": "Kotak Mahindra Bank",
    "PUNB": "Punjab National Bank",
    "BARB": "Bank of Baroda",
    "YESB": "Yes Bank",
    "IDIB": "Indian Bank",
    "CNRB": "Canara Bank",
    "IDFB": "IDFC FIRST Bank",
}

# (minimum days, maximum days, % a year) — general public.
FD_RATES = (
    (7, 45, 3.50),
    (46, 179, 4.75),
    (180, 364, 6.00),
    (365, 455, 6.80),
    (456, 729, 7.10),
    (730, 1094, 7.00),
    (1095, 1824, 6.75),
    (1825, 3650, 6.50),
)

ACCOUNTS = (
    {"id": "ACC-01", "type": "savings", "name": "Premier Savings", "number": "50100238414821", "ifsc": "KSTL0000412",
     "holders": ["Arjun Mehta"], "interest_rate": 3.0, "min_balance": 10000, "nominee": "Meera Mehta", "opened": "2016-08-11"},
    {"id": "ACC-02", "type": "savings", "name": "Joint Savings", "number": "50100519027730", "ifsc": "KSTL0000412",
     "holders": ["Arjun Mehta", "Meera Mehta"], "interest_rate": 3.0, "min_balance": 10000, "nominee": None, "opened": "2019-02-04"},
)

CARDS = (
    {"id": "CRD-01", "kind": "debit", "name": "Kestrel Platinum Debit", "network": "RuPay", "last4": "2207", "account_id": "ACC-01",
     "expires": "08/29", "status": "active",
     "controls": {"online": True, "international": False, "contactless": True, "atm": True},
     "limits": {"atm_daily": 40000, "pos_daily": 100000, "online_daily": 100000}},
    {"id": "CRD-02", "kind": "credit", "name": "Kestrel Horizon Credit", "network": "Visa", "last4": "9015", "account_id": None,
     "expires": "11/28", "status": "active", "credit_limit": 300000, "statement_day": 15, "due_after_days": 20,
     "reward_points": 18420,
     "controls": {"online": True, "international": True, "contactless": True},
     "limits": {"online_daily": 150000, "pos_daily": 200000}},
)

PAYEES = (
    {"id": "PAY-01", "name": "Rakesh Kulkarni", "nickname": "Landlord", "kind": "bank", "account_number": "50200017734412",
     "ifsc": "HDFC0001234", "added_days_ago": 900},
    {"id": "PAY-02", "name": "Rohan Desai", "nickname": "Rohan", "kind": "upi", "upi_id": "rohan.desai@okicici", "added_days_ago": 400},
    {"id": "PAY-03", "name": "Meera Mehta", "nickname": "Meera", "kind": "bank", "account_number": "30881276654",
     "ifsc": "SBIN0004567", "added_days_ago": 1500},
    {"id": "PAY-04", "name": "Sunita Mehta", "nickname": "Aai", "kind": "bank", "account_number": "912010045563210",
     "ifsc": "KKBK0000721", "added_days_ago": 1200},
    {"id": "PAY-05", "name": "Vidya Valley School", "nickname": "Kabir's school", "kind": "bank", "account_number": "0412050009876",
     "ifsc": "UTIB0000412", "added_days_ago": 600},
)

# Standing instructions: (id, payee, amount, day of month, note)
STANDING = (
    ("SCH-01", "PAY-01", 32000, 3, "Rent"),
    ("SCH-02", "PAY-04", 10000, 5, "For Aai"),
)

# Billers: consumer number, typical amount, due day offset from today for the open bill (None: nothing due).
BILLERS = (
    {"id": "BLR-01", "name": "MSEDCL", "category": "Electricity", "consumer_number": "170012345678", "nickname": "Home electricity",
     "amount": 2340, "due_in_days": 6, "autopay": False, "bill_day": 10},
    {"id": "BLR-02", "name": "Airtel Postpaid", "category": "Mobile", "consumer_number": "9822041873", "nickname": "Arjun's mobile",
     "amount": 799, "due_in_days": 12, "autopay": True, "bill_day": 20},
    {"id": "BLR-03", "name": "ACT Fibernet", "category": "Broadband", "consumer_number": "1189034417", "nickname": "Home Wi-Fi",
     "amount": 1179, "due_in_days": 3, "autopay": False, "bill_day": 14},
    {"id": "BLR-04", "name": "Maharashtra Natural Gas", "category": "Piped gas", "consumer_number": "PNG-5512093", "nickname": "Cooking gas",
     "amount": 640, "due_in_days": None, "autopay": False, "bill_day": 18},
    {"id": "BLR-05", "name": "LIC of India", "category": "Insurance", "consumer_number": "884123906", "nickname": "Term policy",
     "amount": 18650, "due_in_days": 24, "autopay": False, "bill_day": None},
)

DEPOSITS = (
    # opened N days ago, tenure in months, payout
    {"id": "FD-01", "principal": 200000, "opened_days_ago": 340, "tenure_months": 12, "payout": "cumulative", "auto_renew": False},
    {"id": "FD-02", "principal": 100000, "opened_days_ago": 150, "tenure_months": 24, "payout": "quarterly", "auto_renew": True},
)

HISTORY_DAYS = 185

MERCHANTS: dict[str, list[tuple[str, int, int]]] = {
    # category -> (merchant, min ₹, max ₹)
    "groceries": [("BigBasket", 900, 3200), ("Zepto", 250, 1100), ("D-Mart Baner", 1500, 4200), ("Nature's Basket", 600, 2100)],
    "dining": [("Swiggy", 280, 950), ("Zomato", 300, 1100), ("Third Wave Coffee", 220, 520), ("Vaishali Restaurant", 450, 1400),
               ("Malaka Spice", 1800, 3600)],
    "transport": [("Uber", 140, 520), ("Ola", 120, 460), ("Rapido", 60, 180)],
    "fuel": [("HP Petrol Pump Aundh", 1500, 3200), ("Indian Oil Baner", 1200, 2900)],
    "shopping": [("Amazon", 450, 6500), ("Myntra", 900, 4200), ("Decathlon", 1200, 5400), ("Croma", 1500, 9000), ("IKEA Pune", 1800, 7500)],
    "health": [("Apollo Pharmacy", 280, 1600), ("Practo", 500, 900), ("Cult.fit", 1499, 1499)],
    "entertainment": [("BookMyShow", 450, 1600), ("PVR INOX", 520, 1400)],
}


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _at(day: date, hour: int, minute: int = 0) -> str:
    from bank_api.logic import IST

    return datetime.combine(day, time(hour, minute), IST).isoformat()


def build_history(today: date) -> list[dict[str, Any]]:
    """Six months of transactions ending yesterday, oldest first (no ids, no balances yet).

    Bank-account money moves on ACC-01 / ACC-02; card spending is on the credit card (CRD-02).
    Credit card bills are paid in full two days before each due date (added by the caller, which
    knows the statement cycle).
    """
    rng = random.Random(4821)
    start = today - timedelta(days=HISTORY_DAYS)
    out: list[dict[str, Any]] = []

    def add(day: date, account: str, direction: str, amount: int, description: str, category: str, channel: str,
            hour: int = 12, **extra: Any) -> None:
        if start <= day < today:
            out.append({"account_id": account, "posted_at": _at(day, hour, rng.randrange(0, 60)), "direction": direction,
                        "amount": int(amount), "description": description, "category": category, "channel": channel, **extra})

    day = start
    while day < today:
        dom = day.day
        if dom == 1:
            add(day, "ACC-01", "credit", 172000, "Salary — Tessaract Labs Pvt Ltd", "income", "neft", 9, merchant="Tessaract Labs")
        if dom == 2:
            add(day, "ACC-01", "debit", 25000, "To Joint Savings ••7730", "transfers", "own", 10, counterparty="ACC-02")
            add(day, "ACC-02", "credit", 25000, "From Premier Savings ••4821", "transfers", "own", 10, counterparty="ACC-01")
            add(day, "ACC-02", "credit", 20000, "From Meera Mehta", "transfers", "imps", 11, merchant="Meera Mehta")
        if dom == 4:
            add(day, "ACC-02", "debit", 9000, "Sakharam Pawar — household help", "family", "upi", 10, merchant="Sakharam Pawar")
        if dom == 8:
            add(day, "ACC-02", "debit", 4500, "Baner Heights CHS — maintenance", "rent", "neft", 12, merchant="Baner Heights CHS")
        for sid, payee, amount, on_day, note in STANDING:
            if dom == on_day:
                name = next(p["name"] for p in PAYEES if p["id"] == payee)
                add(day, "ACC-01", "debit", amount, f"{note} — {name}", "rent" if payee == "PAY-01" else "family", "imps", 8,
                    payee_id=payee, merchant=name, scheduled_id=sid)
        if dom == 7:
            add(day, "ACC-01", "debit", 15000, "SIP — Parag Parikh Flexi Cap Fund", "investments", "auto_debit", 7, merchant="PPFAS Mutual Fund")
        if dom == 12:
            add(day, "CRD-02", "debit", 649, "Netflix", "subscriptions", "card", 6, merchant="Netflix")
        if dom == 22:
            add(day, "CRD-02", "debit", 119, "Spotify", "subscriptions", "card", 6, merchant="Spotify")
        if dom == 25:
            add(day, "CRD-02", "debit", 1499, "Cult.fit membership", "health", "card", 6, merchant="Cult.fit")
        for b in BILLERS:
            if b["bill_day"] and dom == b["bill_day"] and b["id"] != "BLR-05":
                amount = round(b["amount"] * rng.uniform(0.85, 1.12)) if b["category"] in ("Electricity", "Piped gas") else b["amount"]
                add(day, "ACC-01", "debit", amount, f"{b['name']} bill — {b['consumer_number']}", "utilities", "bill_pay", 19,
                    merchant=b["name"], biller_id=b["id"])
        if day.month in (3, 6, 9, 12) and dom == calendar.monthrange(day.year, day.month)[1]:
            add(day, "ACC-01", "credit", rng.randrange(1650, 2100), "Savings interest", "interest", "interest", 23)
            add(day, "ACC-02", "credit", rng.randrange(380, 520), "Savings interest", "interest", "interest", 23)
        if day.month in (1, 4, 7, 10) and dom == 10:
            add(day, "ACC-02", "debit", 18500, "Term fees — Vidya Valley School", "education", "neft", 11, payee_id="PAY-05",
                merchant="Vidya Valley School")
        # everyday spending
        weekday = day.weekday()
        if rng.random() < 0.38:
            m, lo, hi = rng.choice(MERCHANTS["groceries"])
            card = rng.random() < 0.5
            add(day, "CRD-02" if card else "ACC-02", "debit", rng.randrange(lo, hi), m, "groceries", "card" if card else "upi", 18, merchant=m)
        if rng.random() < (0.45 if weekday >= 4 else 0.2):
            m, lo, hi = rng.choice(MERCHANTS["dining"])
            card = rng.random() < 0.6
            add(day, "CRD-02" if card else "ACC-01", "debit", rng.randrange(lo, hi), m, "dining", "card" if card else "upi", 20, merchant=m)
        if weekday < 5 and rng.random() < 0.45:
            m, lo, hi = rng.choice(MERCHANTS["transport"])
            add(day, "ACC-01", "debit", rng.randrange(lo, hi), m, "transport", "upi", 9, merchant=m)
        if day.toordinal() % 9 == 0:
            m, lo, hi = rng.choice(MERCHANTS["fuel"])
            add(day, "CRD-02", "debit", rng.randrange(lo, hi), m, "fuel", "card", 8, merchant=m)
        if rng.random() < 0.08:
            m, lo, hi = rng.choice(MERCHANTS["shopping"])
            add(day, "CRD-02", "debit", rng.randrange(lo, hi), m, "shopping", "card", 15, merchant=m)
        if rng.random() < 0.04:
            m, lo, hi = rng.choice(MERCHANTS["health"][:2])
            add(day, "ACC-01", "debit", rng.randrange(lo, hi), m, "health", "upi", 17, merchant=m)
        if weekday == 5 and rng.random() < 0.3:
            m, lo, hi = rng.choice(MERCHANTS["entertainment"])
            add(day, "CRD-02", "debit", rng.randrange(lo, hi), m, "entertainment", "card", 13, merchant=m)
        if day.toordinal() % 23 == 0:
            add(day, "ACC-01", "debit", 5000, "ATM withdrawal — Kestrel ATM Baner", "cash", "atm", 11, merchant="Kestrel ATM")
        if day.toordinal() % 31 == 4:
            amount = rng.choice((850, 1200, 1460, 2100))
            add(day, "ACC-01", "debit", amount, "Rohan Desai", "transfers", "upi", 22, payee_id="PAY-02", merchant="Rohan Desai")
        if day.toordinal() % 37 == 9:
            add(day, "ACC-01", "credit", rng.choice((600, 950, 1300)), "From Rohan Desai", "transfers", "upi", 21, merchant="Rohan Desai")
        day += timedelta(days=1)

    # One-offs: a trip to Goa two months ago, a refund, and a duplicate food order last week.
    trip = today - timedelta(days=64)
    add(trip, "CRD-02", "debit", 11480, "IndiGo — PNQ to GOI, 2 passengers", "travel", "card", 21, merchant="IndiGo")
    add(trip + timedelta(days=1), "CRD-02", "debit", 18900, "MakeMyTrip — Taj Holiday Village, 3 nights", "travel", "card", 22, merchant="MakeMyTrip")
    shoes = today - timedelta(days=26)
    add(shoes, "CRD-02", "debit", 4299, "Myntra", "shopping", "card", 14, merchant="Myntra")
    add(shoes + timedelta(days=9), "CRD-02", "credit", 4299, "Refund — Myntra", "refunds", "card", 10, merchant="Myntra")
    dup = today - timedelta(days=4)
    add(dup, "CRD-02", "debit", 612, "Zomato", "dining", "card", 21, merchant="Zomato")
    add(dup, "CRD-02", "debit", 612, "Zomato", "dining", "card", 21, merchant="Zomato")
    out.sort(key=lambda t: t["posted_at"])
    return out
