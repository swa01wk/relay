"""Mortgage POC tool registry entries (Relay ToolRegistry metadata)."""

from __future__ import annotations

from relay_runtime.tool_registry import ToolClassification, ToolDefinition, ToolRegistry

_MORTGAGE_ID = {"type": "string", "minLength": 1}


def register_mortgage_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="search_customer",
            classification=ToolClassification.READ_ONLY,
            description="Search customers by name or id",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {"query": {"type": "string", "minLength": 1}},
            },
            output_schema={
                "type": "object",
                "required": ["customers"],
                "properties": {"customers": {"type": "array"}},
            },
        )
    )
    registry.register(
        ToolDefinition(
            name="get_mortgage",
            classification=ToolClassification.READ_ONLY,
            input_schema={
                "type": "object",
                "required": ["mortgage_id"],
                "properties": {"mortgage_id": _MORTGAGE_ID},
            },
            output_schema={"type": "object"},
        )
    )
    registry.register(
        ToolDefinition(
            name="get_payments",
            classification=ToolClassification.READ_ONLY,
            input_schema={
                "type": "object",
                "required": ["mortgage_id"],
                "properties": {
                    "mortgage_id": _MORTGAGE_ID,
                    "months": {"type": "integer", "minimum": 1},
                },
            },
            output_schema={
                "type": "object",
                "required": ["payments"],
                "properties": {"payments": {"type": "array"}},
            },
        )
    )
    registry.register(
        ToolDefinition(
            name="get_rate_history",
            classification=ToolClassification.READ_ONLY,
            input_schema={
                "type": "object",
                "required": ["mortgage_id"],
                "properties": {"mortgage_id": _MORTGAGE_ID},
            },
            output_schema={
                "type": "object",
                "required": ["rates"],
                "properties": {"rates": {"type": "array"}},
            },
        )
    )
    registry.register(
        ToolDefinition(
            name="get_audit_history",
            classification=ToolClassification.READ_ONLY,
            input_schema={
                "type": "object",
                "required": ["mortgage_id"],
                "properties": {
                    "mortgage_id": _MORTGAGE_ID,
                    "limit": {"type": "integer", "minimum": 1},
                },
            },
            output_schema={
                "type": "object",
                "required": ["events"],
                "properties": {"events": {"type": "array"}},
            },
        )
    )
    registry.register(
        ToolDefinition(
            name="prepare_correction",
            classification=ToolClassification.DRAFT,
            description="Build a draft rate correction package (no commit)",
            input_schema={
                "type": "object",
                "required": ["mortgage_id"],
                "properties": {
                    "mortgage_id": _MORTGAGE_ID,
                    "proposed_rate": {"type": "number"},
                    "effective_date": {"type": "string"},
                    "_slow_ms": {"type": "integer", "minimum": 0},
                },
            },
            output_schema={"type": "object"},
        )
    )
    registry.register(
        ToolDefinition(
            name="recalculate_correction_draft",
            classification=ToolClassification.DRAFT,
            description="Recompute draft numbers after human edits",
            input_schema={
                "type": "object",
                "required": ["mortgage_id", "effective_date"],
                "properties": {
                    "mortgage_id": _MORTGAGE_ID,
                    "effective_date": {"type": "string", "minLength": 1},
                    "proposed_rate": {"type": "number"},
                },
            },
            output_schema={"type": "object"},
        )
    )
    registry.register(
        ToolDefinition(
            name="calculate_adjustment",
            classification=ToolClassification.DRAFT,
            description="Deterministic EMI projection for a hypothetical rate",
            input_schema={
                "type": "object",
                "required": ["mortgage_id", "new_rate"],
                "properties": {
                    "mortgage_id": _MORTGAGE_ID,
                    "new_rate": {"type": "number"},
                },
            },
            output_schema={"type": "object"},
        )
    )
    registry.register(
        ToolDefinition(
            name="commit_correction",
            classification=ToolClassification.SIDE_EFFECTING,
            description="Post a servicing correction (requires HITL approval)",
            input_schema={
                "type": "object",
                "required": ["mortgage_id", "effective_date", "proposed_rate"],
                "properties": {
                    "mortgage_id": _MORTGAGE_ID,
                    "effective_date": {"type": "string", "minLength": 1},
                    "proposed_rate": {"type": "number"},
                },
            },
            output_schema={"type": "object"},
        )
    )
    registry.register(
        ToolDefinition(
            name="verify_correction",
            classification=ToolClassification.READ_ONLY,
            description="Verify committed correction against authoritative mortgage store",
            input_schema={
                "type": "object",
                "required": ["mortgage_id"],
                "properties": {
                    "mortgage_id": _MORTGAGE_ID,
                    "commit_id": {"type": "string", "minLength": 1},
                },
            },
            output_schema={"type": "object"},
        )
    )
