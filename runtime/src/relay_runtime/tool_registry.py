"""Tool metadata registry — classification and I/O validation (PRD §11.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ToolClassification(StrEnum):
    READ_ONLY = "read_only"
    DRAFT = "draft"
    SIDE_EFFECTING = "side_effecting"


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    classification: ToolClassification
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    description: str = ""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def is_side_effecting(self, name: str) -> bool:
        definition = self.get(name)
        return definition is not None and definition.classification == ToolClassification.SIDE_EFFECTING

    def is_blocked(self, name: str) -> tuple[bool, str | None]:
        """Unknown tools are blocked; side-effecting tools gated via HITL in RegistryToolExecutor."""
        definition = self.get(name)
        if definition is None:
            return True, f"unknown_tool:{name}"
        return False, None

    def validate_input(self, name: str, arguments: dict[str, Any]) -> str | None:
        definition = self.get(name)
        if definition is None:
            return f"unknown_tool:{name}"
        return _validate_object(arguments, definition.input_schema, path="arguments")

    def validate_output(self, name: str, result: dict[str, Any]) -> str | None:
        definition = self.get(name)
        if definition is None:
            return f"unknown_tool:{name}"
        return _validate_object(result, definition.output_schema, path="result")


def _validate_object(value: Any, schema: dict[str, Any], *, path: str) -> str | None:
    if not schema:
        return None
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            return f"{path} must be an object"
        required = schema.get("required") or []
        props = schema.get("properties") or {}
        for key in required:
            if key not in value:
                return f"{path}.{key} is required"
        for key, subschema in props.items():
            if key not in value:
                continue
            err = _validate_object(value[key], subschema, path=f"{path}.{key}")
            if err:
                return err
        return None
    if expected == "string":
        if not isinstance(value, str):
            return f"{path} must be a string"
        min_len = schema.get("minLength")
        if min_len is not None and len(value) < int(min_len):
            return f"{path} too short"
        return None
    if expected == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return f"{path} must be an integer"
        minimum = schema.get("minimum")
        if minimum is not None and value < int(minimum):
            return f"{path} below minimum"
        return None
    if expected == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return f"{path} must be a number"
        return None
    if expected == "array":
        if not isinstance(value, list):
            return f"{path} must be an array"
        item_schema = schema.get("items")
        if item_schema:
            for idx, item in enumerate(value):
                err = _validate_object(item, item_schema, path=f"{path}[{idx}]")
                if err:
                    return err
        return None
    return None
