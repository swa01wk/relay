"""Shared Relay types for runtime and agents."""

from relay_protocol import (
    EventType,
    PROTOCOL_VERSION,
    RelayEvent,
    RelayEventMetadata,
    minimal_payload_for,
)

__all__ = [
    "EventType",
    "PROTOCOL_VERSION",
    "RelayEvent",
    "RelayEventMetadata",
    "minimal_payload_for",
]
