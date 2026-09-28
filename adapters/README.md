# Adapters

Implementation details for **runtime ports** (PRD §5.2). Pipecat, OpenAI, Deepgram, and LangGraph types stay here — never in `packages/protocol` or public SDK exports.

| Path | Port |
|------|------|
| `realtime/pipecat/` | `RealtimeTransport` |
| `models/` | `ModelProvider` |
| `speech/` | `SpeechToTextProvider`, `TextToSpeechProvider`, `TurnDetector` |
| `agents/` | `AgentAdapter` |
| `persistence/` | `EventStore`, `StateStore` |

See [`plans/phase-00-foundation.md`](../plans/phase-00-foundation.md).
