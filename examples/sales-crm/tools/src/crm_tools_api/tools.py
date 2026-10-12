"""Single source of truth for CRM tools: function, description and input schema.

The HTTP API, the in-process executor and the agent's ToolRegistry are all built from
``TOOL_SPECS``, so adding a tool is one entry here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from crm_tools_api import logic
from crm_tools_api.seeds import REPS, STAGES


@dataclass(frozen=True)
class ToolSpec:
    fn: Callable[..., dict[str, Any]]
    description: str
    properties: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    # read_only | draft | side_effecting — side-effecting tools need human approval in Relay.
    classification: str = "read_only"

    @property
    def input_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": "object", "properties": self.properties}
        if self.required:
            schema["required"] = list(self.required)
        return schema


_REP_NAMES = [rep["name"] for rep in REPS]
_LIMIT = {"type": "integer", "minimum": 1}
_ID = {"type": "string", "minLength": 1}

TOOL_SPECS: dict[str, ToolSpec] = {
    "list_accounts": ToolSpec(
        logic.list_accounts,
        "List customer accounts (companies), optionally filtered by industry",
        {"industry": {"type": "string"}, "limit": _LIMIT},
    ),
    "search_accounts": ToolSpec(
        logic.search_accounts,
        "Find accounts by (partial) company name or account id",
        {"query": {"type": "string", "minLength": 1}},
        ("query",),
    ),
    "get_account": ToolSpec(
        logic.get_account,
        "One account with its contacts and all its deals",
        {"account_id": _ID},
        ("account_id",),
    ),
    "list_contacts": ToolSpec(
        logic.list_contacts,
        "Contacts (people), optionally for one account",
        {"account_id": {"type": "string"}, "limit": _LIMIT},
    ),
    "list_deals": ToolSpec(
        logic.list_deals,
        "Deals/opportunities sorted by amount; filter by stage, owner (rep name or id), "
        "account, minimum amount, or open_only for deals not yet closed",
        {
            "stage": {"type": "string", "enum": STAGES},
            "owner": {"type": "string"},
            "account_id": {"type": "string"},
            "min_amount": {"type": "number"},
            "open_only": {"type": "boolean"},
            "limit": _LIMIT,
        },
    ),
    "get_deal": ToolSpec(
        logic.get_deal,
        "One deal with its activity history",
        {"deal_id": _ID},
        ("deal_id",),
    ),
    "list_activities": ToolSpec(
        logic.list_activities,
        "Recent calls, emails and meetings, newest first; filter by deal or account",
        {"deal_id": {"type": "string"}, "account_id": {"type": "string"}, "limit": _LIMIT},
    ),
    "get_pipeline_summary": ToolSpec(
        logic.get_pipeline_summary,
        "Deal count, total and probability-weighted amount per pipeline stage",
    ),
    "get_revenue_by_month": ToolSpec(
        logic.get_revenue_by_month,
        "Closed-won revenue and target per month (most recent last)",
        {"months": {"type": "integer", "minimum": 1}},
    ),
    "get_rep_performance": ToolSpec(
        logic.get_rep_performance,
        "Per sales rep: quota, closed-won last quarter, attainment, win rate, open pipeline",
    ),
    # --- Writes: side_effecting, so Relay saves them only on approval or form submit ---
    "create_account": ToolSpec(
        logic.create_account,
        "Create a customer account (company)",
        {
            "name": {"type": "string", "minLength": 1, "title": "Company name"},
            "industry": {"type": "string", "minLength": 1, "title": "Industry"},
            "city": {"type": "string", "title": "City"},
            "employees": {"type": "integer", "minimum": 1, "title": "Employees"},
            "owner": {"type": "string", "enum": _REP_NAMES, "title": "Owner"},
        },
        ("name", "industry"),
        classification="side_effecting",
    ),
    "create_contact": ToolSpec(
        logic.create_contact,
        "Add a contact person to an account",
        {
            "account_id": {"type": "string", "minLength": 1, "title": "Account ID"},
            "name": {"type": "string", "minLength": 1, "title": "Full name"},
            "title": {"type": "string", "title": "Job title"},
            "email": {"type": "string", "format": "email", "title": "Email"},
            "phone": {"type": "string", "title": "Phone"},
        },
        ("account_id", "name"),
        classification="side_effecting",
    ),
    "update_contact": ToolSpec(
        logic.update_contact,
        "Change a contact's name, job title, email or phone",
        {
            "contact_id": {"type": "string", "minLength": 1, "title": "Contact ID"},
            "name": {"type": "string", "title": "Full name"},
            "title": {"type": "string", "title": "Job title"},
            "email": {"type": "string", "format": "email", "title": "Email"},
            "phone": {"type": "string", "title": "Phone"},
        },
        ("contact_id",),
        classification="side_effecting",
    ),
    "create_deal": ToolSpec(
        logic.create_deal,
        "Create a deal (opportunity) for an account",
        {
            "account_id": {"type": "string", "minLength": 1, "title": "Account ID"},
            "product": {"type": "string", "minLength": 1, "title": "Product / deal name"},
            "amount_usd": {"type": "number", "minimum": 1, "title": "Amount (USD)"},
            "close_date": {"type": "string", "format": "date", "title": "Expected close date"},
            "stage": {"type": "string", "enum": STAGES, "title": "Stage"},
            "owner": {"type": "string", "enum": _REP_NAMES, "title": "Owner"},
        },
        ("account_id", "product", "amount_usd", "close_date"),
        classification="side_effecting",
    ),
    "update_deal": ToolSpec(
        logic.update_deal,
        "Change a deal's stage, amount, expected close date or owner",
        {
            "deal_id": {"type": "string", "minLength": 1, "title": "Deal ID"},
            "stage": {"type": "string", "enum": STAGES, "title": "Stage"},
            "amount_usd": {"type": "number", "minimum": 1, "title": "Amount (USD)"},
            "close_date": {"type": "string", "format": "date", "title": "Expected close date"},
            "owner": {"type": "string", "enum": _REP_NAMES, "title": "Owner"},
        },
        ("deal_id",),
        classification="side_effecting",
    ),
    "delete_deal": ToolSpec(
        logic.delete_deal,
        "Delete a deal and its activities",
        {"deal_id": {"type": "string", "minLength": 1, "title": "Deal ID"}},
        ("deal_id",),
        classification="side_effecting",
    ),
    "log_activity": ToolSpec(
        logic.log_activity,
        "Log a call, email, meeting or note against a deal",
        {
            "deal_id": {"type": "string", "minLength": 1, "title": "Deal ID"},
            "type": {"type": "string", "enum": list(logic.ACTIVITY_TYPES), "title": "Activity type"},
            "subject": {"type": "string", "minLength": 1, "title": "Subject"},
            "contact": {"type": "string", "title": "Contact"},
            "date_logged": {"type": "string", "format": "date", "title": "Date"},
            "notes": {"type": "string", "maxLength": 2000, "title": "Notes"},
        },
        ("deal_id", "type", "subject"),
        classification="side_effecting",
    ),
}


def tool_manifest() -> list[dict[str, Any]]:
    """``GET /tools`` body: what Relay's tool discovery reads."""
    return [
        {
            "name": name,
            "description": spec.description,
            "input_schema": spec.input_schema,
            "classification": spec.classification,
        }
        for name, spec in TOOL_SPECS.items()
    ]


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    spec = TOOL_SPECS.get(name)
    if spec is None:
        return {"error": f"unknown_tool:{name}"}
    kwargs = {key: value for key, value in arguments.items() if key in spec.properties}
    missing = [key for key in spec.required if key not in kwargs]
    if missing:
        return {"error": f"missing_arguments:{','.join(missing)}"}
    return spec.fn(**kwargs)
