"""Generative UI surfaces — ``present_ui`` model tool mapped to the ``PRESENT_UI`` action.

Domain-agnostic: agents let the model call ``present_ui`` and forward the surfaces to
the client, which renders them (Web SDK ``registerPlaygroundSurfaces``; app owns pixels).
"""

from __future__ import annotations

import json
import re
from typing import Any

from relay_runtime.tool_registry import ToolClassification, ToolRegistry

PRESENT_UI_ACTION = "PRESENT_UI"
PRESENT_UI_TOOL_NAME = "present_ui"
SURFACE_KINDS = ("table", "kv", "cards", "notice", "chart", "comparison", "markdown", "form")
CHART_TYPES = ("bar", "line", "area", "pie")
MAX_SURFACES = 4
MAX_TABLE_ROWS = 50
MAX_CHART_POINTS = 200
MAX_CHART_SERIES = 6
MAX_COMPARISON_ITEMS = 4
MAX_FORM_FIELDS = 20
FORM_FIELD_TYPES = ("text", "textarea", "number", "date", "email", "select", "checkbox")
MAX_MARKDOWN_CHARS = 8000

# Client → runtime: APP_EVENT advertising app UI actions the agent may call.
CLIENT_CAPABILITIES_EVENT = "ui.capabilities"
MAX_CLIENT_ACTIONS = 30
_CLIENT_ACTION_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,59}$")

# Client → runtime: APP_EVENT name carrying {form_id, title, values}; starts an agent turn.
FORM_SUBMIT_EVENT = "ui.form_submit"
FORM_SUBMISSION_PREFIX = "[Form submitted]"
_MAX_FORM_VALUE_CHARS = 500

_PRESENT_UI_DESCRIPTION = (
    "Show structured results on the user's screen: table, kv (key/value details), cards, "
    "chart, comparison (2-4 entities side by side), markdown (formatted explanation), notice, "
    "or form (collect structured input; the user's submission comes back as their next "
    "message). Use it whenever the user asks for a table, list, comparison, breakdown, chart, "
    "graph, trend, details, a write-up, or when you need several inputs from them. Charts: bar "
    "for comparing categories, line or area for values over time, pie for parts of a whole. "
    "Only use data you were given or fetched with other tools; never invent values."
)

_SURFACE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["kind", "title"],
    "properties": {
        "kind": {"type": "string", "enum": list(SURFACE_KINDS)},
        "title": {"type": "string"},
        "caption": {"type": "string"},
        "columns": {
            "type": "array",
            "description": "table: column keys in display order",
            "items": {"type": "string"},
        },
        "rows": {
            "type": "array",
            "description": "table: one object per row keyed by column",
            "items": {"type": "object"},
        },
        "items": {
            "type": "array",
            "description": "kv: label/value pairs",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
            },
        },
        "cards": {
            "type": "array",
            "description": "cards: title, optional body and fields",
            "items": {"type": "object"},
        },
        "body": {"type": "string", "description": "notice: text"},
        "chart_type": {"type": "string", "enum": list(CHART_TYPES), "description": "chart"},
        "x_key": {
            "type": "string",
            "description": "chart: field in each data point used for the x axis / pie labels",
        },
        "series": {
            "type": "array",
            "description": "chart: numeric fields to plot (pie uses the first)",
            "items": {
                "type": "object",
                "required": ["key"],
                "properties": {"key": {"type": "string"}, "label": {"type": "string"}},
            },
        },
        "data": {
            "type": "array",
            "description": "chart: one object per point, e.g. {month: '2025-09', amount: 2847.5}",
            "items": {"type": "object"},
        },
        "y_label": {"type": "string", "description": "chart: y axis label / unit"},
        "stacked": {"type": "boolean", "description": "chart: stack bar/area series"},
        "id": {"type": "string", "description": "stable id; required for form"},
        "compare": {
            "type": "array",
            "description": "comparison: 2-4 entities, each {name, fields: {label: value}}",
            "items": {
                "type": "object",
                "required": ["name", "fields"],
                "properties": {"name": {"type": "string"}, "fields": {"type": "object"}},
            },
        },
        "markdown": {"type": "string", "description": "markdown: GitHub-flavoured markdown body"},
        "description": {"type": "string", "description": "form: short instructions"},
        "fields": {
            "type": "array",
            "description": "form: input fields (with submit_tool: optional — the names to show, in order)",
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "label": {"type": "string"},
                    "type": {"type": "string", "enum": list(FORM_FIELD_TYPES)},
                    "required": {"type": "boolean"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "default": {"type": ["string", "number", "boolean"]},
                    "placeholder": {"type": "string"},
                },
            },
        },
        "submit_label": {"type": "string", "description": "form: submit button text"},
        "submit_tool": {
            "type": "string",
            "description": (
                "form: name of a write tool that saves the submission. Relay builds the fields "
                "from that tool's parameters; submitting saves directly (no separate approval)"
            ),
        },
        "values": {"type": "object", "description": "form: prefilled values by field name"},
    },
}


def present_ui_tool() -> dict[str, Any]:
    """OpenAI-style function tool the model calls to render surfaces."""
    return {
        "type": "function",
        "function": {
            "name": PRESENT_UI_TOOL_NAME,
            "description": _PRESENT_UI_DESCRIPTION,
            "parameters": {
                "type": "object",
                "required": ["surfaces"],
                "properties": {
                    "surfaces": {"type": "array", "items": _SURFACE_SCHEMA},
                    "replace": {
                        "type": "boolean",
                        "description": "true replaces the canvas; false appends",
                    },
                },
            },
        },
    }


def model_tools_from_registry(
    registry: ToolRegistry,
    *,
    classifications: tuple[ToolClassification, ...] = (ToolClassification.READ_ONLY,),
) -> list[dict[str, Any]]:
    """Expose registry tools of the given classes as OpenAI-style function tools."""
    tools: list[dict[str, Any]] = []
    for definition in registry.list_tools():
        if definition.classification not in classifications:
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description or definition.name.replace("_", " "),
                    "parameters": definition.input_schema or {"type": "object", "properties": {}},
                },
            }
        )
    return tools


def sanitize_present_ui_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Keep known surface kinds and cap sizes before the payload reaches the client."""
    raw = arguments.get("surfaces")
    surfaces: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or item.get("kind") not in SURFACE_KINDS:
            continue
        surface = dict(item)
        if isinstance(surface.get("rows"), list):
            surface["rows"] = surface["rows"][:MAX_TABLE_ROWS]
        if surface["kind"] == "chart":
            if surface.get("chart_type") not in CHART_TYPES:
                surface["chart_type"] = "bar"
            if isinstance(surface.get("data"), list):
                surface["data"] = surface["data"][:MAX_CHART_POINTS]
            if isinstance(surface.get("series"), list):
                surface["series"] = surface["series"][:MAX_CHART_SERIES]
        if surface["kind"] == "comparison" and isinstance(surface.get("compare"), list):
            surface["compare"] = surface["compare"][:MAX_COMPARISON_ITEMS]
        if surface["kind"] == "markdown":
            surface["markdown"] = str(surface.get("markdown") or surface.get("body") or "")[
                :MAX_MARKDOWN_CHARS
            ]
        if surface["kind"] == "form":
            fields = [
                f for f in surface.get("fields") or []
                if isinstance(f, dict) and f.get("name") and f.get("type") in FORM_FIELD_TYPES
            ][:MAX_FORM_FIELDS]
            if not fields:
                continue
            surface["fields"] = fields
            surface["id"] = str(surface.get("id") or "form")
        surfaces.append(surface)
        if len(surfaces) >= MAX_SURFACES:
            break
    return {"surfaces": surfaces, "replace": bool(arguments.get("replace", True))}


def format_form_submission(payload: dict[str, Any]) -> str | None:
    """Turn a ``ui.form_submit`` payload into the user message for the next agent turn."""
    values = payload.get("values")
    if not isinstance(values, dict) or not values:
        return None
    clean: dict[str, Any] = {}
    for key, value in list(values.items())[:MAX_FORM_FIELDS]:
        if isinstance(value, (bool, int, float)) or value is None:
            clean[str(key)] = value
        else:
            clean[str(key)] = str(value)[:_MAX_FORM_VALUE_CHARS]
    title = str(payload.get("title") or payload.get("form_id") or "form")[:120]
    return f"{FORM_SUBMISSION_PREFIX} {title}: {json.dumps(clean, ensure_ascii=False)}"


def sanitize_client_actions(raw: Any) -> list[dict[str, Any]]:
    """Keep well-formed advertised actions: {name, description, parameters (object schema)}."""
    actions: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not _CLIENT_ACTION_NAME.match(name) or name in (PRESENT_UI_ACTION, "SHOW_TABLE"):
            continue
        parameters = item.get("parameters")
        if not isinstance(parameters, dict) or parameters.get("type") != "object":
            parameters = {"type": "object", "properties": {}}
        actions.append(
            {
                "name": name,
                "description": str(item.get("description") or name.replace("_", " ").lower())[:500],
                "parameters": parameters,
            }
        )
        if len(actions) >= MAX_CLIENT_ACTIONS:
            break
    return actions


def _label(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


def form_fields_from_schema(
    schema: dict[str, Any],
    *,
    include: list[str] | None = None,
    values: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Form fields for a tool's JSON-schema parameters (required ones are always included)."""
    properties: dict[str, Any] = schema.get("properties") or {}
    required = [n for n in schema.get("required") or [] if n in properties]
    names = [n for n in (include or list(properties)) if n in properties]
    names += [n for n in required if n not in names]
    fields: list[dict[str, Any]] = []
    for name in names[:MAX_FORM_FIELDS]:
        prop = properties[name] if isinstance(properties[name], dict) else {}
        kind = prop.get("type")
        if isinstance(kind, list):
            kind = next((k for k in kind if k != "null"), "string")
        options = [str(o) for o in prop.get("enum") or [] if o is not None]
        if options:
            field_type = "select"
        elif kind == "boolean":
            field_type = "checkbox"
        elif kind in ("number", "integer"):
            field_type = "number"
        elif prop.get("format") == "date":
            field_type = "date"
        elif prop.get("format") == "email":
            field_type = "email"
        elif int(prop.get("maxLength") or 0) >= 300:
            field_type = "textarea"
        else:
            field_type = "text"
        field: dict[str, Any] = {
            "name": name,
            "label": str(prop.get("title") or _label(name)),
            "type": field_type,
            "required": name in required,
        }
        if options:
            field["options"] = options
        if values and values.get(name) is not None:
            field["default"] = values[name]
        if prop.get("description"):
            field["placeholder"] = str(prop["description"])[:80]
        fields.append(field)
    return fields
