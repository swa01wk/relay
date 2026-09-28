"""Smoke import of all §5.2 ports."""

import importlib


def test_all_ports_exported():
    ports = importlib.import_module("relay_runtime.ports")
    expected = [
        "RealtimeTransport",
        "SpeechToTextProvider",
        "TextToSpeechProvider",
        "TurnDetector",
        "ModelProvider",
        "AgentAdapter",
        "ToolExecutor",
        "StateStore",
        "EventStore",
        "EventPublisher",
    ]
    for name in expected:
        assert hasattr(ports, name)
