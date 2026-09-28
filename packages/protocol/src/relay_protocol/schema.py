"""JSON Schema validation for RP events."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator

from relay_protocol.models import RelayEvent


@lru_cache(maxsize=1)
def _load_envelope_schema() -> dict[str, Any]:
    raw = resources.files("relay_protocol.schemas").joinpath("relay_event.envelope.json").read_text()
    return json.loads(raw)


def validate_relay_event_dict(data: dict[str, Any]) -> None:
    """Validate a serialized event dict against the envelope JSON Schema."""
    schema = _load_envelope_schema()
    Draft202012Validator(schema).validate(data)


def validate_relay_event(event: RelayEvent) -> None:
    """Validate a RelayEvent model instance."""
    payload = event.model_dump(mode="json")
    validate_relay_event_dict(payload)
