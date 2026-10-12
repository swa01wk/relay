"""Deterministic demo CRM data (fixed RNG seed) — accounts, contacts, reps, deals, activities."""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

TODAY = date(2026, 10, 1)
STAGES = ["Prospecting", "Qualification", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]
OPEN_STAGES = STAGES[:4]
STAGE_PROBABILITY = {
    "Prospecting": 10,
    "Qualification": 25,
    "Proposal": 50,
    "Negotiation": 75,
    "Closed Won": 100,
    "Closed Lost": 0,
}

REPS: list[dict[str, Any]] = [
    {"id": "REP-1", "name": "Ava Thompson", "region": "West", "quarterly_quota": 300_000},
    {"id": "REP-2", "name": "Marcus Lee", "region": "East", "quarterly_quota": 280_000},
    {"id": "REP-3", "name": "Sofia Alvarez", "region": "Central", "quarterly_quota": 260_000},
    {"id": "REP-4", "name": "Daniel Okafor", "region": "East", "quarterly_quota": 250_000},
    {"id": "REP-5", "name": "Hannah Becker", "region": "West", "quarterly_quota": 240_000},
]

_ACCOUNTS = [
    ("Northwind Logistics", "Logistics", "Seattle, WA", 1200),
    ("Brightpath Health", "Healthcare", "Boston, MA", 3400),
    ("Summit Retail Group", "Retail", "Denver, CO", 5200),
    ("Cobalt Financial", "Financial Services", "New York, NY", 2100),
    ("Evergreen Energy", "Energy", "Houston, TX", 1800),
    ("Lumen Education", "Education", "Chicago, IL", 650),
    ("Atlas Manufacturing", "Manufacturing", "Detroit, MI", 4100),
    ("Pioneer Biotech", "Biotech", "San Diego, CA", 900),
    ("Harbor Media", "Media", "Los Angeles, CA", 750),
    ("Keystone Insurance", "Insurance", "Philadelphia, PA", 2600),
    ("Vertex Software", "Software", "Austin, TX", 480),
    ("Riverbend Foods", "Food & Beverage", "Minneapolis, MN", 1500),
]
_FIRST = ["Priya", "James", "Elena", "Omar", "Grace", "Liam", "Mei", "Carlos", "Nora", "Ethan",
          "Aisha", "Lucas", "Zara", "Noah", "Ines", "Ryan", "Chloe", "Victor", "Maya", "Felix",
          "Leah", "Arjun", "Tara", "Ben"]
_LAST = ["Patel", "Carter", "Rossi", "Haddad", "Kim", "Murphy", "Chen", "Ruiz", "Novak", "Brooks",
         "Rahman", "Silva", "Ahmed", "Fischer", "Moreau", "Walsh", "Dubois", "Petrov", "Singh",
         "Larsen", "Cohen", "Iyer", "Quinn", "Wright"]
_TITLES = ["VP Operations", "Head of IT", "CFO", "Procurement Manager", "Director of Sales Ops",
           "CTO", "COO", "IT Manager"]
_PRODUCTS = ["Platform license", "Analytics add-on", "Enterprise support", "Data migration",
             "Seat expansion", "Renewal", "Integration package"]
_ACTIVITY_NOTES = {
    "call": ["Discovery call", "Pricing discussion", "Follow-up on proposal", "Check-in with champion"],
    "email": ["Sent proposal", "Shared case study", "Sent pricing update", "Answered security questions"],
    "meeting": ["Product demo", "Stakeholder alignment", "Negotiation meeting", "Kickoff planning"],
}


def _build() -> dict[str, Any]:
    rng = random.Random(42)
    accounts: list[dict[str, Any]] = []
    contacts: list[dict[str, Any]] = []
    deals: list[dict[str, Any]] = []
    activities: list[dict[str, Any]] = []

    names = iter(zip(_FIRST, _LAST))
    for index, (name, industry, city, employees) in enumerate(_ACCOUNTS, start=1):
        account_id = f"ACC-{100 + index}"
        owner = REPS[index % len(REPS)]
        accounts.append(
            {
                "id": account_id,
                "name": name,
                "industry": industry,
                "city": city,
                "employees": employees,
                "owner_id": owner["id"],
                "owner": owner["name"],
                "annual_revenue_usd": employees * rng.randint(90, 160) * 1000,
            }
        )
        for _ in range(2):
            first, last = next(names)
            contacts.append(
                {
                    "id": f"CON-{len(contacts) + 1:03d}",
                    "account_id": account_id,
                    "name": f"{first} {last}",
                    "title": rng.choice(_TITLES),
                    "email": f"{first.lower()}.{last.lower()}@{name.split()[0].lower()}.example.com",
                    "phone": f"+1-555-{rng.randint(100, 999)}-{rng.randint(1000, 9999)}",
                }
            )

    deal_no = 2000
    closed_count = {"Closed Won": 0, "Closed Lost": 0}
    for account in accounts:
        for _ in range(rng.randint(4, 8)):
            deal_no += 1
            stage = rng.choices(STAGES, weights=[9, 9, 9, 9, 42, 22])[0]
            if stage in ("Closed Won", "Closed Lost"):
                # Rotate wins and losses separately through the last 12 months so every
                # month has closed-won revenue.
                month_back = closed_count[stage] % 12
                closed_count[stage] += 1
                close_date = TODAY - timedelta(days=month_back * 30 + rng.randint(1, 28))
                created = close_date - timedelta(days=rng.randint(20, 120))
            else:
                created = TODAY - timedelta(days=rng.randint(10, 150))
                close_date = TODAY + timedelta(days=rng.randint(7, 150))
            amount = rng.randrange(8_000, 180_000, 500)
            owner = next(r for r in REPS if r["id"] == account["owner_id"])
            deals.append(
                {
                    "id": f"DEAL-{deal_no}",
                    "name": f"{account['name']} — {rng.choice(_PRODUCTS)}",
                    "account_id": account["id"],
                    "account": account["name"],
                    "owner_id": owner["id"],
                    "owner": owner["name"],
                    "stage": stage,
                    "amount_usd": amount,
                    "probability": STAGE_PROBABILITY[stage],
                    "created_date": created.isoformat(),
                    "close_date": close_date.isoformat(),
                }
            )

    for deal in deals:
        account_contacts = [c for c in contacts if c["account_id"] == deal["account_id"]]
        created = date.fromisoformat(deal["created_date"])
        last = min(TODAY, date.fromisoformat(deal["close_date"]))
        for _ in range(rng.randint(1, 4)):
            kind = rng.choice(list(_ACTIVITY_NOTES))
            when = created + timedelta(days=rng.randint(0, max(1, (last - created).days)))
            activities.append(
                {
                    "id": f"ACT-{len(activities) + 1:04d}",
                    "deal_id": deal["id"],
                    "account_id": deal["account_id"],
                    "type": kind,
                    "subject": rng.choice(_ACTIVITY_NOTES[kind]),
                    "contact": rng.choice(account_contacts)["name"],
                    "owner": deal["owner"],
                    "date": when.isoformat(),
                }
            )
    activities.sort(key=lambda a: a["date"], reverse=True)
    return {"accounts": accounts, "contacts": contacts, "deals": deals, "activities": activities}


def build_seed_data() -> dict[str, list[dict[str, Any]]]:
    """Fresh deterministic demo data (used once to seed an empty database)."""
    return _build()
