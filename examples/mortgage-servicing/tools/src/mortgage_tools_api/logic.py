"""Shared read-tool implementations for HTTP and in-process executors."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from mortgage_tools_api.seeds import (
    AUDIT_BY_MORTGAGE,
    CUSTOMERS,
    MORTGAGES,
    PAYMENTS_BY_MORTGAGE,
    RATE_HISTORY_BY_MORTGAGE,
)


def search_customer(query: str) -> dict[str, Any]:
    q = query.lower().strip()
    matches = [
        customer
        for customer in CUSTOMERS
        if q in customer["name"].lower() or q in customer["id"].lower()
    ]
    return {"customers": matches}


def get_mortgage(mortgage_id: str) -> dict[str, Any]:
    record = MORTGAGES.get(mortgage_id)
    if record is None:
        return {"error": "not_found", "mortgage": None}
    return {"mortgage": record}


def get_payments(mortgage_id: str, *, months: int = 3) -> dict[str, Any]:
    if mortgage_id not in MORTGAGES:
        return {"error": "not_found", "payments": []}
    rows = list(PAYMENTS_BY_MORTGAGE.get(mortgage_id, []))
    rows.sort(key=lambda row: row["month"], reverse=True)
    return {"mortgage_id": mortgage_id, "payments": rows[: max(1, months)]}


def get_rate_history(mortgage_id: str) -> dict[str, Any]:
    if mortgage_id not in MORTGAGES:
        return {"error": "not_found", "rates": []}
    return {"mortgage_id": mortgage_id, "rates": list(RATE_HISTORY_BY_MORTGAGE.get(mortgage_id, []))}


def get_audit_history(mortgage_id: str, *, limit: int = 10) -> dict[str, Any]:
    if mortgage_id not in MORTGAGES:
        return {"error": "not_found", "events": []}
    events = list(AUDIT_BY_MORTGAGE.get(mortgage_id, []))
    return {"mortgage_id": mortgage_id, "events": events[: max(1, limit)]}


def prepare_correction(
    mortgage_id: str,
    *,
    proposed_rate: float | None = None,
    effective_date: str | None = None,
    slow_ms: int = 0,
) -> dict[str, Any]:
    """Draft-only correction package (no ledger commit — Phase 9)."""
    if slow_ms > 0:
        time.sleep(slow_ms / 1000.0)
    mortgage = MORTGAGES.get(mortgage_id)
    if mortgage is None:
        return {"error": "not_found"}
    rate = float(proposed_rate if proposed_rate is not None else mortgage.get("current_rate") or 0.0)
    eff = effective_date or "2025-01-01"
    adjustment = calculate_adjustment(mortgage_id, new_rate=rate)
    if adjustment.get("error"):
        return adjustment
    return {
        "mortgage_id": mortgage_id,
        "draft": {
            **adjustment,
            "effective_date": eff,
            "proposed_rate": rate,
            "status": "draft",
        },
    }


def recalculate_correction_draft(
    mortgage_id: str,
    *,
    effective_date: str,
    proposed_rate: float | None = None,
) -> dict[str, Any]:
    """Recompute draft numbers after a human edit to effective date."""
    return prepare_correction(
        mortgage_id,
        proposed_rate=proposed_rate,
        effective_date=effective_date,
    )


_COMMIT_RECEIPTS: dict[str, dict[str, Any]] = {}


def expected_commit_token() -> str:
    return os.environ.get("MORTGAGE_COMMIT_TOKEN", "dev-mortgage-commit")


def commit_correction(
    mortgage_id: str,
    *,
    effective_date: str,
    proposed_rate: float,
    auth_token: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Apply a servicing correction — sole mutator of MORTGAGES / rate history (Phase 9)."""
    token = auth_token or ""
    if token != expected_commit_token():
        return {"error": "unauthorized"}
    if idempotency_key and idempotency_key in _COMMIT_RECEIPTS:
        return dict(_COMMIT_RECEIPTS[idempotency_key])

    mortgage = MORTGAGES.get(mortgage_id)
    if mortgage is None:
        return {"error": "not_found"}

    adjustment = calculate_adjustment(mortgage_id, new_rate=float(proposed_rate))
    if adjustment.get("error"):
        return adjustment

    projected_emi = float(adjustment.get("projected_emi") or mortgage.get("emi") or 0.0)
    mortgage["current_rate"] = float(proposed_rate)
    mortgage["emi"] = projected_emi
    history = list(RATE_HISTORY_BY_MORTGAGE.get(mortgage_id, []))
    history.append(
        {
            "effective_date": effective_date,
            "rate": float(proposed_rate),
            "reason": "servicing_correction",
        }
    )
    RATE_HISTORY_BY_MORTGAGE[mortgage_id] = history
    commit_id = str(uuid4())
    at = datetime.now(timezone.utc).isoformat()
    audit = list(AUDIT_BY_MORTGAGE.get(mortgage_id, []))
    audit.insert(
        0,
        {
            "at": at,
            "actor": "hitl_commit",
            "event": "correction_committed",
            "commit_id": commit_id,
            "effective_date": effective_date,
            "proposed_rate": proposed_rate,
        },
    )
    AUDIT_BY_MORTGAGE[mortgage_id] = audit

    body = {
        "commit_id": commit_id,
        "mortgage_id": mortgage_id,
        "committed": True,
        "effective_date": effective_date,
        "proposed_rate": float(proposed_rate),
        "projected_emi": projected_emi,
        "mortgage": dict(mortgage),
    }
    if idempotency_key:
        _COMMIT_RECEIPTS[idempotency_key] = dict(body)
    return body


def verify_correction(mortgage_id: str, *, commit_id: str | None = None) -> dict[str, Any]:
    """Read authoritative mortgage state after commit."""
    mortgage = MORTGAGES.get(mortgage_id)
    if mortgage is None:
        return {"error": "not_found", "verified": False}
    events = list(AUDIT_BY_MORTGAGE.get(mortgage_id, []))
    match = None
    if commit_id:
        match = next((e for e in events if e.get("commit_id") == commit_id), None)
    else:
        match = next((e for e in events if e.get("event") == "correction_committed"), None)
    if match is None:
        return {"error": "commit_not_found", "verified": False, "mortgage_id": mortgage_id}
    return {
        "verified": True,
        "commit_id": match.get("commit_id"),
        "mortgage_id": mortgage_id,
        "mortgage": dict(mortgage),
        "audit_event": match,
    }


def calculate_adjustment(mortgage_id: str, *, new_rate: float) -> dict[str, Any]:
    mortgage = MORTGAGES.get(mortgage_id)
    if mortgage is None:
        return {"error": "not_found"}
    current_rate = float(mortgage.get("current_rate") or 0.0)
    emi = float(mortgage.get("emi") or 0.0)
    delta_rate = round(new_rate - current_rate, 3)
    estimated_emi_delta = round((delta_rate / 0.125) * 12.0, 2)
    projected_emi = round(emi + estimated_emi_delta, 2)
    return {
        "mortgage_id": mortgage_id,
        "current_rate": current_rate,
        "new_rate": new_rate,
        "delta_rate": delta_rate,
        "current_emi": emi,
        "projected_emi": projected_emi,
        "estimated_emi_delta": estimated_emi_delta,
    }
