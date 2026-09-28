# Relay POC — models, speech, and API keys

PRD §13.1: **OpenAI initially** for LLM; **replaceable** STT/TTS adapters. Pipecat may wrap provider clients internally, but credentials stay **server-side only** (PRD §11.3).

## Recommended POC defaults

| Role | Adapter port | Suggested provider | Default model / product |
|------|--------------|-------------------|-------------------------|
| Agent LLM | `ModelProvider` | OpenAI | `gpt-5.4-mini` (dev, CI, demo) |
| STT | `SpeechToTextProvider` | Deepgram Listen (live WebSocket) | `flux-general-en` on `/v2/listen` |
| TTS | `TextToSpeechProvider` | Deepgram Speak (live WebSocket) | `flux-haley-en` on `/v2/speak` |
| Turn detect | `TurnDetector` | Deepgram Flux EOT + Relay TurnManager | Flux turn signals; Relay owns barge-in policy |

Swap providers by changing adapter registration—not RP or SDK types.

### Stream / realtime requirements (POC voice path)

Adapters on the **hot path** must use **streaming WebSockets**, not batch REST, so audio and tokens flow with low latency and barge-in works.

| Role | Transport | Required behavior |
|------|-----------|-------------------|
| STT | `wss://api.deepgram.com/v2/listen?model=flux-general-en` | Send PCM (or negotiated encoding) in small chunks; enable interim/final transcripts and Flux end-of-turn signals for TurnManager. |
| TTS | `wss://api.deepgram.com/v2/speak?model=flux-haley-en` | Stream LLM tokens in; receive raw audio out (`encoding=linear16`, `sample_rate` matched to playback); support `Interrupt` on user barge-in; `Flush` at turn boundaries. |
| LLM | OpenAI **streaming** chat/completions | Same session as agent graph; token stream feeds TTS adapter (no wait-for-full-message on live calls). |

**Adapter contract:** `SpeechToTextProvider` and `TextToSpeechProvider` implementations must expose async stream in/out compatible with Pipecat (or equivalent) live services. Reject or gate non-streaming config in Phase 3+ integration tests.

**Fallback (if a dependency lacks Flux v2 yet):** STT `nova-3` on `/v1/listen` with `interim_results=true` and endpointing; TTS `aura-2-thalia-en` on `/v1/speak` with token queue + `Flush`. Still WebSocket-only on the hot path—do not use prerecord/batch TTS for live sessions.

## Environment variables (target: `infra/docker/.env`)

```bash
# Required for agent path (Phase 1+)
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4-mini

# Required for voice path (Phase 3+)
DEEPGRAM_API_KEY=
DEEPGRAM_STT_MODEL=flux-general-en
DEEPGRAM_TTS_MODEL=flux-haley-en
# Optional: linear16 | mulaw | alaw — must match browser/WebRTC decode path
DEEPGRAM_TTS_ENCODING=linear16
DEEPGRAM_TTS_SAMPLE_RATE=24000

# Runtime
RELAY_DATABASE_URL=postgresql://...
RELAY_REDIS_URL=redis://...

# Session auth (POC dev mint)
RELAY_DEV_TOKEN_SECRET=change-me
```

Never expose provider keys to the browser or Web SDK.

## Agent orchestration

- **LangGraph** (optional) implements mortgage reference workflow **behind** `AgentAdapter` (PRD §9.1).
- Mortgage prompts, tool wiring, and business rules live in `examples/mortgage-servicing/agent/`—not in `runtime/`.

## Post-POC provider expansion

Anthropic, Gemini, Bedrock, vLLM, native speech-to-speech models: add adapters under `adapters/models/` and `adapters/speech/` without changing Phase 0+ contract tests.
