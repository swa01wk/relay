"""Runtime adapter ports (PRD §5.2).

Implementations live under ``adapters/`` (Pipecat, OpenAI, Deepgram, LangGraph, etc.).
These ABCs must not reference framework-specific types.
"""

from relay_runtime.ports.agent import AgentAdapter
from relay_runtime.ports.events import EventPublisher, EventStore
from relay_runtime.ports.model import ModelProvider
from relay_runtime.ports.realtime import RealtimeTransport
from relay_runtime.ports.speech import SpeechToTextProvider, TextToSpeechProvider, TurnDetector
from relay_runtime.ports.state import StateStore
from relay_runtime.ports.tools import ToolExecutor

__all__ = [
    "AgentAdapter",
    "EventPublisher",
    "EventStore",
    "ModelProvider",
    "RealtimeTransport",
    "SpeechToTextProvider",
    "StateStore",
    "TextToSpeechProvider",
    "ToolExecutor",
    "TurnDetector",
]
