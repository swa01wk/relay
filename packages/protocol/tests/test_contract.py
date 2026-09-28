"""P00-TC-001, P00-TC-002 — RP schema and catalog contract tests."""

import json

import pytest
from pydantic import ValidationError

from relay_protocol import EventType, RelayEvent, RelayEventMetadata, minimal_payload_for
from relay_protocol.events import ALL_EVENT_TYPES, PROTOCOL_VERSION
from relay_protocol.schema import validate_relay_event


def _sample_metadata(session_id: str = "sess-1", **kwargs) -> RelayEventMetadata:
    return RelayEventMetadata(
        session_id=session_id,
        sequence=0,
        source="test",
        **kwargs,
    )


def test_p00_tc_001_missing_session_id_rejected():
    """Invalid RP payload missing session_id → validation error."""
    with pytest.raises(ValidationError) as exc:
        RelayEventMetadata(sequence=0, source="test")  # type: ignore[call-arg]
    assert "session_id" in str(exc.value)


@pytest.mark.parametrize("event_type", ALL_EVENT_TYPES)
def test_p00_tc_002_round_trip_all_event_types(event_type: EventType):
    """Every §8.1 event type serializes and validates with required metadata."""
    event = RelayEvent(
        type=event_type,
        metadata=_sample_metadata(
            trace_id="trace-abc",
            project_id="proj-1",
        ),
        payload=minimal_payload_for(event_type),
    )
    validate_relay_event(event)
    raw = event.model_dump(mode="json")
    restored = RelayEvent.model_validate(raw)
    assert restored.type == event_type
    assert restored.metadata.protocol_version == PROTOCOL_VERSION
    assert restored.metadata.session_id == "sess-1"
    json.dumps(raw)


def test_json_schema_rejects_missing_required_metadata_field():
    event = RelayEvent(
        type=EventType.SESSION_READY,
        metadata=_sample_metadata(),
        payload=minimal_payload_for(EventType.SESSION_READY),
    )
    data = event.model_dump(mode="json")
    del data["metadata"]["session_id"]
    with pytest.raises(Exception):
        from relay_protocol.schema import validate_relay_event_dict

        validate_relay_event_dict(data)


def test_event_enum_matches_schema_catalog():
    from importlib import resources

    raw = resources.files("relay_protocol.schemas").joinpath("relay_event.envelope.json").read_text()
    schema_path_events = set(json.loads(raw)["properties"]["type"]["enum"])
    enum_events = {e.value for e in EventType}
    assert schema_path_events == enum_events
