"""Minimal seeds when mortgage-tools-api is not on PYTHONPATH."""

from __future__ import annotations

from typing import Any

CUSTOMERS: list[dict[str, Any]] = [
    {
        "id": "CUST-1001",
        "name": "Rajesh Sharma",
        "email": "rajesh.sharma@example.com",
        "mortgages": [{"id": "MORT-2931", "status": "active", "property": "14 Oak Lane, Austin, TX"}],
    }
]

MORTGAGES: dict[str, dict[str, Any]] = {
    "MORT-2931": {
        "id": "MORT-2931",
        "status": "active",
        "property": "14 Oak Lane, Austin, TX",
        "customer_id": "CUST-1001",
        "customer_name": "Rajesh Sharma",
    }
}
