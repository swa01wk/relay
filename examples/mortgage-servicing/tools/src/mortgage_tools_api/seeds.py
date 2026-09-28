"""POC seed data — Rajesh Sharma / MORT-2931 demo scenario."""

from __future__ import annotations

from typing import Any

CUSTOMERS: list[dict[str, Any]] = [
    {
        "id": "CUST-1001",
        "name": "Rajesh Sharma",
        "email": "rajesh.sharma@example.com",
        "mortgages": [
            {
                "id": "MORT-2931",
                "status": "active",
                "property": "14 Oak Lane, Austin, TX",
                "current_rate": 6.125,
                "emi": 2847.50,
            },
            {
                "id": "MORT-1102",
                "status": "closed",
                "property": "2200 W 5th St, Austin, TX",
                "current_rate": 4.875,
                "emi": 0,
            },
        ],
    },
    {
        "id": "CUST-1002",
        "name": "Maria Lopez",
        "email": "maria.lopez@example.com",
        "mortgages": [
            {
                "id": "MORT-4410",
                "status": "active",
                "property": "88 Pine St, Denver, CO",
                "current_rate": 5.75,
                "emi": 1920.00,
            }
        ],
    },
]

MORTGAGES: dict[str, dict[str, Any]] = {}
for customer in CUSTOMERS:
    for mortgage in customer["mortgages"]:
        MORTGAGES[str(mortgage["id"])] = {
            **mortgage,
            "customer_id": customer["id"],
            "customer_name": customer["name"],
        }

PAYMENTS_BY_MORTGAGE: dict[str, list[dict[str, Any]]] = {
    "MORT-2931": [
        {"month": "2025-09", "amount": 2847.50, "status": "paid", "paid_on": "2025-09-01"},
        {"month": "2025-08", "amount": 2847.50, "status": "paid", "paid_on": "2025-08-01"},
        {"month": "2025-07", "amount": 2847.50, "status": "paid", "paid_on": "2025-07-01"},
        {"month": "2025-06", "amount": 2795.00, "status": "paid", "paid_on": "2025-06-01"},
    ],
    "MORT-4410": [
        {"month": "2025-09", "amount": 1920.00, "status": "paid", "paid_on": "2025-09-03"},
    ],
}

RATE_HISTORY_BY_MORTGAGE: dict[str, list[dict[str, Any]]] = {
    "MORT-2931": [
        {"effective_date": "2023-06-01", "rate": 5.500, "reason": "origination"},
        {"effective_date": "2024-01-01", "rate": 5.875, "reason": "arm_adjustment"},
        {"effective_date": "2025-01-01", "rate": 6.125, "reason": "arm_adjustment"},
    ],
}

AUDIT_BY_MORTGAGE: dict[str, list[dict[str, Any]]] = {
    "MORT-2931": [
        {"at": "2025-08-15T10:00:00Z", "actor": "system", "event": "rate_lookup"},
        {"at": "2025-09-01T09:00:00Z", "actor": "ops", "event": "payment_posted"},
    ],
}
