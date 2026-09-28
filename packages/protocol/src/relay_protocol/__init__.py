"""Relay Protocol (RP) — canonical event contract."""

from relay_protocol.events import EventType, PROTOCOL_VERSION
from relay_protocol.models import RelayEvent, RelayEventMetadata, minimal_payload_for

__all__ = [
    "EventType",
    "PROTOCOL_VERSION",
    "RelayEvent",
    "RelayEventMetadata",
    "minimal_payload_for",
]
