"""Read-only CRM queries shared by the HTTP API and the in-process executor."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from crm_tools_api import db
from crm_tools_api.seeds import OPEN_STAGES, REPS, STAGE_PROBABILITY, STAGES, TODAY


def _quarter_start(day: date) -> date:
    return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def list_accounts(*, industry: str | None = None, limit: int = 50) -> dict[str, Any]:
    rows = [a for a in db.rows("accounts") if not industry or a["industry"].lower() == industry.lower()]
    return {"accounts": rows[:limit], "total": len(rows)}


def search_accounts(query: str) -> dict[str, Any]:
    q = query.lower().strip()
    rows = [a for a in db.rows("accounts") if q in a["name"].lower() or q in a["id"].lower()]
    return {"accounts": rows}


def get_account(account_id: str) -> dict[str, Any]:
    account = next((a for a in db.rows("accounts") if a["id"] == account_id), None)
    if account is None:
        return {"error": "not_found"}
    return {
        "account": account,
        "contacts": [c for c in db.rows("contacts") if c["account_id"] == account_id],
        "deals": [d for d in db.rows("deals") if d["account_id"] == account_id],
    }


def list_contacts(*, account_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    rows = [c for c in db.rows("contacts") if not account_id or c["account_id"] == account_id]
    return {"contacts": rows[:limit], "total": len(rows)}


def list_deals(
    *,
    stage: str | None = None,
    owner: str | None = None,
    account_id: str | None = None,
    min_amount: float | None = None,
    open_only: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    rows = list(db.rows("deals"))
    if stage:
        rows = [d for d in rows if d["stage"].lower() == stage.lower()]
    if owner:
        needle = owner.lower()
        rows = [d for d in rows if needle in d["owner"].lower() or d["owner_id"].lower() == needle]
    if account_id:
        rows = [d for d in rows if d["account_id"] == account_id]
    if min_amount is not None:
        rows = [d for d in rows if d["amount_usd"] >= min_amount]
    if open_only:
        rows = [d for d in rows if d["stage"] in OPEN_STAGES]
    rows.sort(key=lambda d: d["amount_usd"], reverse=True)
    return {"deals": rows[:limit], "total": len(rows)}


def get_deal(deal_id: str) -> dict[str, Any]:
    deal = next((d for d in db.rows("deals") if d["id"] == deal_id), None)
    if deal is None:
        return {"error": "not_found"}
    activities = sorted(
        (a for a in db.rows("activities") if a["deal_id"] == deal_id),
        key=lambda a: (a["date"], a["id"]),
        reverse=True,
    )
    return {"deal": deal, "activities": activities}


def list_activities(
    *, deal_id: str | None = None, account_id: str | None = None, limit: int = 20
) -> dict[str, Any]:
    rows = [
        a
        for a in db.rows("activities")
        if (not deal_id or a["deal_id"] == deal_id) and (not account_id or a["account_id"] == account_id)
    ]
    rows.sort(key=lambda a: (a["date"], a["id"]), reverse=True)
    return {"activities": rows[:limit], "total": len(rows)}


def get_pipeline_summary() -> dict[str, Any]:
    stages = []
    for stage in STAGES:
        deals = [d for d in db.rows("deals") if d["stage"] == stage]
        amount = sum(d["amount_usd"] for d in deals)
        stages.append(
            {
                "stage": stage,
                "deals": len(deals),
                "amount_usd": amount,
                "weighted_usd": round(sum(d["amount_usd"] * d["probability"] / 100 for d in deals)),
            }
        )
    return {"stages": stages}


def get_revenue_by_month(*, months: int = 12) -> dict[str, Any]:
    won: dict[str, float] = defaultdict(float)
    for deal in db.rows("deals"):
        if deal["stage"] == "Closed Won":
            won[deal["close_date"][:7]] += deal["amount_usd"]
    series = []
    year, month = TODAY.year, TODAY.month
    for _ in range(max(1, min(months, 24))):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        key = f"{year}-{month:02d}"
        series.append({"month": key, "revenue_usd": round(won.get(key, 0.0)), "target_usd": 220_000})
    series.reverse()
    return {"months": series}


def get_rep_performance() -> dict[str, Any]:
    # Last completed quarter: the one containing the day before the current quarter starts.
    quarter_start = _quarter_start(_quarter_start(TODAY) - timedelta(days=1))
    quarter_end = _quarter_start(TODAY) - timedelta(days=1)
    rows = []
    for rep in REPS:
        mine = [d for d in db.rows("deals") if d["owner_id"] == rep["id"]]
        won = [d for d in mine if d["stage"] == "Closed Won"]
        lost = [d for d in mine if d["stage"] == "Closed Lost"]
        won_quarter = [
            d for d in won if quarter_start <= date.fromisoformat(d["close_date"]) <= quarter_end
        ]
        closed_quarter = sum(d["amount_usd"] for d in won_quarter)
        decided = len(won) + len(lost)
        rows.append(
            {
                "rep": rep["name"],
                "region": rep["region"],
                "quota_usd": rep["quarterly_quota"],
                "closed_won_quarter_usd": closed_quarter,
                "attainment_pct": round(100 * closed_quarter / rep["quarterly_quota"], 1),
                "win_rate_pct": round(100 * len(won) / decided, 1) if decided else 0.0,
                "open_pipeline_usd": sum(d["amount_usd"] for d in mine if d["stage"] in OPEN_STAGES),
            }
        )
    return {"quarter": f"{quarter_start.isoformat()} to {quarter_end.isoformat()}", "reps": rows}


def get_dashboard() -> dict[str, Any]:
    """KPIs + series for the frontend dashboard (not exposed to the model)."""
    open_deals = [d for d in db.rows("deals") if d["stage"] in OPEN_STAGES]
    won = [d for d in db.rows("deals") if d["stage"] == "Closed Won"]
    lost = [d for d in db.rows("deals") if d["stage"] == "Closed Lost"]
    revenue = get_revenue_by_month(months=12)["months"]
    last, previous = revenue[-1]["revenue_usd"], revenue[-2]["revenue_usd"]
    return {
        "as_of": TODAY.isoformat(),
        "kpis": {
            "open_pipeline_usd": sum(d["amount_usd"] for d in open_deals),
            "open_deals": len(open_deals),
            "weighted_pipeline_usd": round(sum(d["amount_usd"] * d["probability"] / 100 for d in open_deals)),
            "win_rate_pct": round(100 * len(won) / (len(won) + len(lost)), 1),
            "avg_won_deal_usd": round(sum(d["amount_usd"] for d in won) / len(won)) if won else 0,
            "last_month_revenue_usd": last,
            "last_month_change_pct": round(100 * (last - previous) / previous, 1) if previous else None,
        },
        "revenue": revenue,
        "pipeline": get_pipeline_summary()["stages"],
        "deals": sorted(db.rows("deals"), key=lambda d: d["close_date"], reverse=True),
    }


# --- Writes (classified side_effecting: Relay runs them only after the user approves/submits) ---

ACTIVITY_TYPES = ("call", "email", "meeting", "note")


def _rep(owner: str | None, *, fallback_id: str | None = None) -> dict[str, Any] | None:
    if owner:
        needle = owner.strip().lower()
        return next((r for r in REPS if needle in (r["name"].lower(), r["id"].lower()) or needle in r["name"].lower()), None)
    return next((r for r in REPS if r["id"] == fallback_id), None)


def _valid_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        return False
    return True


def create_account(
    *, name: str, industry: str, city: str = "", employees: int | None = None, owner: str | None = None
) -> dict[str, Any]:
    if any(a["name"].lower() == name.strip().lower() for a in db.rows("accounts")):
        return {"error": "account_exists"}
    rep = _rep(owner) if owner else REPS[0]
    if rep is None:
        return {"error": f"unknown_owner:{owner}"}
    account = {
        "id": db.next_id("accounts"),
        "name": name.strip(),
        "industry": industry.strip(),
        "city": city.strip(),
        "employees": employees,
        "owner_id": rep["id"],
        "owner": rep["name"],
        "annual_revenue_usd": None,
    }
    return {"account": db.put("accounts", account)}


def create_contact(
    *, account_id: str, name: str, title: str = "", email: str = "", phone: str = ""
) -> dict[str, Any]:
    if db.get("accounts", account_id) is None:
        return {"error": "account_not_found"}
    contact = {
        "id": db.next_id("contacts"),
        "account_id": account_id,
        "name": name.strip(),
        "title": title.strip(),
        "email": email.strip(),
        "phone": phone.strip(),
    }
    return {"contact": db.put("contacts", contact)}


def update_contact(
    *, contact_id: str, name: str | None = None, title: str | None = None, email: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    contact = db.get("contacts", contact_id)
    if contact is None:
        return {"error": "contact_not_found"}
    changes = {k: v.strip() for k, v in {"name": name, "title": title, "email": email, "phone": phone}.items() if v is not None}
    return {"contact": db.put("contacts", {**contact, **changes}), "changed": sorted(changes)}


def create_deal(
    *, account_id: str, product: str, amount_usd: float, close_date: str, stage: str = "Prospecting",
    owner: str | None = None,
) -> dict[str, Any]:
    account = db.get("accounts", account_id)
    if account is None:
        return {"error": "account_not_found"}
    if stage not in STAGES:
        return {"error": f"invalid_stage:{stage}"}
    if not _valid_date(close_date):
        return {"error": "invalid_close_date"}
    if amount_usd <= 0:
        return {"error": "amount_must_be_positive"}
    rep = _rep(owner, fallback_id=account["owner_id"])
    if rep is None:
        return {"error": f"unknown_owner:{owner}"}
    deal = {
        "id": db.next_id("deals"),
        "name": f"{account['name']} — {product.strip()}",
        "account_id": account_id,
        "account": account["name"],
        "owner_id": rep["id"],
        "owner": rep["name"],
        "stage": stage,
        "amount_usd": round(float(amount_usd), 2),
        "probability": STAGE_PROBABILITY[stage],
        "created_date": date.today().isoformat(),
        "close_date": close_date,
    }
    return {"deal": db.put("deals", deal)}


def update_deal(
    *, deal_id: str, stage: str | None = None, amount_usd: float | None = None, close_date: str | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    deal = db.get("deals", deal_id)
    if deal is None:
        return {"error": "deal_not_found"}
    before = dict(deal)
    if stage is not None:
        if stage not in STAGES:
            return {"error": f"invalid_stage:{stage}"}
        deal["stage"] = stage
        deal["probability"] = STAGE_PROBABILITY[stage]
        if stage in ("Closed Won", "Closed Lost") and before["stage"] != stage:
            deal["close_date"] = date.today().isoformat()
    if amount_usd is not None:
        if amount_usd <= 0:
            return {"error": "amount_must_be_positive"}
        deal["amount_usd"] = round(float(amount_usd), 2)
    if close_date is not None:
        if not _valid_date(close_date):
            return {"error": "invalid_close_date"}
        deal["close_date"] = close_date
    if owner is not None:
        rep = _rep(owner)
        if rep is None:
            return {"error": f"unknown_owner:{owner}"}
        deal["owner_id"], deal["owner"] = rep["id"], rep["name"]
    changed = sorted(k for k in deal if deal[k] != before.get(k))
    return {"deal": db.put("deals", deal), "changed": changed}


def delete_deal(*, deal_id: str) -> dict[str, Any]:
    deal = db.get("deals", deal_id)
    if deal is None:
        return {"error": "deal_not_found"}
    removed = [a["id"] for a in db.rows("activities") if a["deal_id"] == deal_id]
    for activity_id in removed:
        db.delete("activities", activity_id)
    db.delete("deals", deal_id)
    return {"deleted": deal_id, "deal": deal, "activities_deleted": len(removed)}


def log_activity(
    *, deal_id: str, type: str, subject: str, contact: str = "", date_logged: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    deal = db.get("deals", deal_id)
    if deal is None:
        return {"error": "deal_not_found"}
    if type not in ACTIVITY_TYPES:
        return {"error": f"invalid_type:{type}"}
    when = date_logged or date.today().isoformat()
    if not _valid_date(when):
        return {"error": "invalid_date"}
    activity = {
        "id": db.next_id("activities"),
        "deal_id": deal_id,
        "account_id": deal["account_id"],
        "type": type,
        "subject": subject.strip(),
        "contact": contact.strip(),
        "owner": deal["owner"],
        "date": when,
        "notes": notes.strip(),
    }
    return {"activity": db.put("activities", activity)}

