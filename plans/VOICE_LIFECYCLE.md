# Voice lifecycle — mic to speaker (Relay POC)

Reference for debugging latency, barge-in, and TTS. Session events are persisted in PostgreSQL (`relay_events`).

Implementation status: **Phase 7 signed off** — see [STATUS.md](./STATUS.md). UAT fixes (2026-09-25): [D-003-005](./DECISIONS.md#d-003-005-smallwebrtc-audio-receiver-idle), [D-004-004](./DECISIONS.md#d-004-004-tts-cancel-vs-next-utterance), [D-004-005](./DECISIONS.md#d-004-005-spoken-replies-when-webrtc-connected).

## Components

| Layer | Component | Role |
|-------|-----------|------|
| Browser | WebRTC (`packages/web-sdk/src/webrtc-media.ts`) | Mic `sendrecv` transceiver → SRTP uplink; agent PCM downlink (Web Audio + `<audio>`) |
| Browser | RP WebSocket (`@relay/web-sdk`) | Control + transcripts + `RESPONSE_*` / `SPEECH_*` (not audio) |
| Browser | Mortgage UI mic meter | Local analyser only — if flat, fix OS mic permission before debugging STT |
| Gateway | `PipecatSmallWebRtcTransport` | WebRTC + Pipecat **ingress** pipeline per `session_id`; `push_output_pcm` for agent audio |
| Gateway | `webrtc_fixup.py` | Deferred mic bind ([D-003-004](./DECISIONS.md#d-003-004-smallwebrtc-mic-track-binding-race)); keep audio receiver on when idle ([D-003-005](./DECISIONS.md#d-003-005-smallwebrtc-audio-receiver-idle)) |
| Gateway | `VoicePipelineHooks` → `SessionManager.notify_*` | VAD/STT callbacks into the session actor ([`deps.py`](../services/gateway/src/relay_gateway/deps.py)) |
| Media (ingress) | **Hybrid (default):** `VADProcessor` (Silero) → STT → `RelayUserTurnProcessor` (Smart Turn v3 stop) · **Legacy:** `RelayVadProcessor` when `RELAY_TURN_DETECTOR=silero` | VAD → fast `on_speech_started`; semantic stop → `on_speech_ended` |
| Media (ingress) | `DeepgramSTTService` + `RelayTranscriptProcessor` | RP `TRANSCRIPT_DELTA` / `TRANSCRIPT_FINAL` |
| Media (egress) | `AgentAudioOutputProcessor` | Queues agent PCM from runtime → SmallWebRTC out |
| Runtime | `SessionManager` (actor queue) | Voice commands serialized; **barge-in fast path** when `AGENT_SPEAKING` |
| Runtime | `TurnManager` | Voice turn FSM (§6.2) |
| Runtime | `InterruptionManager` | Playout / barge-in FSM (§7; orthogonal to `TurnManager`) |
| Runtime | `TurnCancellation` | Shared cancel token for LLM stream + TTS + tool policy |
| Runtime | `AgentRuntime` | LLM stream → RP `RESPONSE_*` |
| Runtime | `play_tts_stream` + Deepgram TTS | Sanitized tokens → PCM → `RealtimeTransport.push_output_pcm` |
| Runtime | `SpeechTextStream` | Markdown stripped **only** for TTS (UI keeps raw `RESPONSE_DELTA`) |
| Runtime | `PlaybackTracker` | `SPEECH_*` progress; heard prefix for interrupt (`HEARD_TEXT_COMMITTED`) |
| Runtime | `_speak_assistant_if_voice_connected` | Batch TTS for **text Send** when WebRTC connected; fallback if streaming playout never started |

**Pipecat ingress order:** `transport.input()` → `RelayVadProcessor` → `DeepgramSTTService` → `RelayTranscriptProcessor` → sink. **TTS is not in this pipeline** — it runs in the session actor after `TURN_PROCESSING`.

## Two ways the agent speaks ([D-004-005](./DECISIONS.md#d-004-005-spoken-replies-when-webrtc-connected))

| User input | When WebRTC **connected** | When WebRTC **not** connected |
|------------|---------------------------|-------------------------------|
| **Voice** (mic → STT final) | Streaming TTS during `_run_voice_response_turn` | Same turn logic but `use_tts` false — text reply only |
| **Text** (Send / `USER_TEXT`) | LLM → then **batch** `_speak_assistant_if_voice_connected` | Text reply only (no `SPEECH_*`) |

Precondition for any speaker output: `DEEPGRAM_API_KEY` set (or mock TTS in tests) **and** `RealtimeTransport.is_connected(session_id)` true (Pipecat `on_client_connected`).

## TurnManager (voice FSM)

| Phase | Typical trigger |
|-------|-------------------|
| `IDLE` | Session ready; turn complete |
| `USER_SPEAKING` | VAD `speech_started` (or barge-in from `AGENT_SPEAKING`) |
| `ENDPOINTING` | VAD `speech_ended` (or STT-final fallback — see below) |
| `PROCESSING` | `begin_turn(voice=True)` after utterance commit |
| `AGENT_SPEAKING` | First TTS PCM / `on_playout_started` |

Text sends while phase ∉ `{IDLE}` can yield `SESSION_ERROR turn_in_progress` (unless the utterance is cleared — see Phase 3 tests).

## InterruptionManager (§7, parallel FSM)

| Phase | Meaning |
|-------|---------|
| `IDLE` | No agent playout tracked |
| `AGENT_PLAYOUT` | TTS/WebRTC output in progress |
| `INTERRUPTING` | Barge-in detected; draining cancel |
| `USER_CAPTURE` | Heard text committed; capturing next utterance |

Barge-in is only armed when **`TurnManager.phase == AGENT_SPEAKING`**. Earlier user speech during `PROCESSING` is ignored by the voice FSM (`TurnTransitionError` on `on_user_speech_started`).

## Happy path (no interrupt)

```mermaid
sequenceDiagram
  participant Mic
  participant WebRTC
  participant VAD as RelayVad + Silero
  participant STT as Deepgram STT
  participant Actor as SessionManager actor
  participant LLM as AgentRuntime
  participant TTS as play_tts_stream
  participant Out as AgentAudioOutput
  participant Spk as Speaker

  Mic->>WebRTC: PCM uplink
  WebRTC->>VAD: InputAudioRawFrame
  VAD->>Actor: notify_voice_speech_started (queued)
  Actor->>Actor: USER_SPEAKING + RP USER_SPEECH_STARTED
  STT->>Actor: notify_voice_transcript_delta/final (queued)
  Actor->>Actor: RP TRANSCRIPT_*
  VAD->>Actor: notify_voice_speech_ended (queued)
  Actor->>Actor: ENDPOINTING + RP USER_SPEECH_ENDED
  Note over Actor: RELAY_UTTERANCE_COMMIT_DELAY_MS; buffer STT finals
  Actor->>Actor: TURN_STARTED, TURN_PROCESSING
  Actor->>LLM: run_streaming_turn (+ TurnCancellation)
  LLM->>Actor: RESPONSE_STARTED, RESPONSE_DELTA*
  Actor->>TTS: SpeechTextStream → token queue
  TTS->>Out: push_output_pcm
  Out->>WebRTC: agent PCM
  WebRTC->>Spk: playout
  Note over Actor: enter_agent_speaking, RP SPEECH_STARTED
  LLM->>Actor: RESPONSE_COMPLETED
  Actor->>Actor: context append full text, complete_turn → IDLE
  Actor->>Actor: RP TURN_COMPLETED
```

**STT-before-VAD-end:** If `TRANSCRIPT_FINAL` arrives while still `USER_SPEAKING`, the actor arms `RELAY_STT_FINAL_ENDPOINT_MS` debounce, then forces endpointing (`_ensure_voice_endpointing`) so the turn can commit without a late Silero `speech_ended`.

**Typical latency budget (POC):** tune in [`infra/docker/.env.example`](../infra/docker/.env.example) (Compose copies to `.env`):

1. Silero end-of-speech (`RELAY_ENDPOINTING_SILENCE_MS`; code default 400ms, example **650ms**)
2. STT final debounce (`RELAY_STT_FINAL_ENDPOINT_MS`, example **500ms**) if VAD end is late
3. Utterance commit (`RELAY_UTTERANCE_COMMIT_DELAY_MS`, example **350ms**)
4. LLM TTFT (~0.5–2s)
5. TTS first byte + WebRTC

Metrics: `turn.endpointing_delay_ms`, `model.ttft_ms`, `voice.first_tts_byte_ms`, `voice.user_stop_to_first_audio_ms`.

### RP events (uninterrupted, voice + TTS)

Rough order: `USER_SPEECH_STARTED` → `USER_SPEECH_ENDED` → `TRANSCRIPT_*` → `TURN_STARTED` → `TURN_PROCESSING` → `RESPONSE_STARTED` → `RESPONSE_DELTA*` → (`SPEECH_STARTED`, optional `SPEECH_PROGRESS`) → `RESPONSE_COMPLETED` → `TURN_COMPLETED`.

**Text Send with voice connected:** same RP text path (`TRANSCRIPT_FINAL` from client text) → `TURN_*` → `RESPONSE_*` → **`SPEECH_STARTED`** (batch TTS, often after `RESPONSE_COMPLETED`) → `TURN_COMPLETED`.

Without WebRTC connected, both paths are **text-only** on the speaker (no `SPEECH_*`).

## Barge-in (interrupt during agent playout)

Precondition: **`TurnManager` = `AGENT_SPEAKING`** and TTS/playout active (`InterruptionManager` ideally `AGENT_PLAYOUT`).

```mermaid
sequenceDiagram
  participant VAD as RelayVad + Silero
  participant SM as SessionManager
  participant Cancel as TurnCancellation
  participant TTS as TTS + transport
  participant LLM as AgentRuntime
  participant PT as PlaybackTracker

  VAD->>SM: notify_voice_speech_started (fast path, not actor queue)
  SM->>Cancel: cancel()
  SM->>TTS: cancel_output + tts.cancel
  SM->>SM: INTERRUPTION_DETECTED, USER_SPEECH_STARTED
  SM->>SM: TurnManager.on_barge_in → USER_SPEAKING
  Note over LLM: If still streaming: RESPONSE_CANCELLED
  Note over LLM: If already done: RESPONSE_COMPLETED may precede interrupt
  SM->>PT: finalize_heard(interrupted=true)
  SM->>SM: RESPONSE_INTERRUPTED, HEARD_TEXT_COMMITTED
  SM->>SM: context commit_assistant_heard; TURN_COMPLETED
  Note over TTS: Next synthesize_stream clears cancel ([D-004-004])
  Note over SM: New utterance uses normal queued VAD/STT path
```

Steps (maps to [`session_manager._handle_barge_in`](../runtime/src/relay_runtime/session_manager.py)):

1. VAD → `notify_voice_speech_started` **fast path** when phase is `AGENT_SPEAKING` (does not wait on session actor).
2. `TurnCancellation.cancel()`; `INTERRUPTION_DETECTED`; stop TTS/WebRTC out (`cancel_output` + `TextToSpeechProvider.cancel`).
3. `InterruptionManager.on_barge_in_detected()`; `TurnManager.on_barge_in()` → **`USER_SPEAKING`** (`active_turn_id` cleared).
4. RP `USER_SPEECH_STARTED`; reset transcript buffer; open voice capture.
5. Voice turn task finishes: **`RESPONSE_INTERRUPTED`**, **`HEARD_TEXT_COMMITTED`**, **`TURN_COMPLETED`** (no `complete_turn()` — already barged).
6. **Next turn:** TTS must run normally — cancel flag cleared at start of each `synthesize_stream` ([D-004-004](./DECISIONS.md#d-004-004-tts-cancel-vs-next-utterance)). If streaming playout never fires `SPEECH_STARTED`, batch fallback runs at end of voice turn.

**Heard vs generated:** `PlaybackTracker` + `InterruptionManager.heard_prefix` — context gets **`commit_assistant_heard`**, not the full `RESPONSE_COMPLETED` text when interrupt wins after partial playout.

**Also triggers interrupt:** client `cancelVoiceUtterance()` / `cancel_agent_playback` during `AGENT_SPEAKING` (same cancel + heard path; may not emit `INTERRUPTION_DETECTED` unless VAD barge-in handler runs).

## What breaks UX (seen in UAT)

| Symptom | Likely cause | Where to look |
|---------|----------------|---------------|
| Transcript but no reply | Stuck `USER_SPEAKING`, no endpoint commit | Events: missing `TURN_STARTED`; logs: `voice turn not started` |
| Text send blocked | `SESSION_ERROR turn_in_progress` while voice FSM not IDLE | `USER_SPEAKING` / `ENDPOINTING` / `AGENT_SPEAKING` |
| TTS reads "asterisk" | Raw markdown in token stream | Fixed: `SpeechTextStream` before TTS queue |
| **Text only after you interrupted agent** | Was: cancel flag skipped next TTS stream | Fixed [D-004-004]: audit `SPEECH_STARTED` per turn after `INTERRUPTION_DETECTED` |
| **Never speaks (voice connected)** | WebRTC up but no RTP / TTS | Logs: `No audio frame received`; events: no `SPEECH_STARTED` |
| Mic meter silent | Browser/OS mic permission | macOS → Privacy → Microphone → Chrome; not a gateway STT issue |
| Interrupt weak | Barge-in before `AGENT_SPEAKING` or speaker bleed into VAD | Events: no `INTERRUPTION_DETECTED` near prior `SPEECH_STARTED` |
| Slow to respond | Sum of endpointing + STT debounce + commit + LLM | Tune env vars in `infra/docker/.env` |
| **Full reply in chat while agent still talking** | UI rendered every `RESPONSE_DELTA`; TTS lags LLM | Fixed: mortgage UI follows `SPEECH_PROGRESS.heard_text` when voice connected |
| **Interrupt speech appears seconds late** | Session actor blocked in `_run_voice_response_turn`; STT queued | Fixed: voice turn runs in `voice_response_task`; actor keeps processing `TRANSCRIPT_*` |
| **No partial user text while speaking** | `TRANSCRIPT_DELTA` not shown in UI | Fixed: live transcript row in mortgage chat panel |
| Agent TTS cuts off on open speakers | STT partial triggered barge-in during `AGENT_SPEAKING` | Fixed: barge-in from **VAD start only**, not STT partials |
| Echo / double agent loudness | Remote audio routed to `AudioContext.destination` + `<audio>` | Fixed: play agent audio via `<audio>` only (browser default AEC on mic when available) |

## Debugging commands

```bash
# Gateway logs (ingress + Pipecat)
docker compose -f infra/docker/docker-compose.yml logs gateway --tail=200

# Mic reaching VAD?
docker compose -f infra/docker/docker-compose.yml logs gateway 2>&1 | grep -E "audio ingress|No audio frame|binding input"

# Event timeline — expect SPEECH_STARTED on each spoken turn
docker exec docker-postgres-1 psql -U relay -d relay -c \
  "SELECT sequence, type, metadata->>'turn_id' FROM relay_events WHERE session_id='<id>' AND type IN ('SPEECH_STARTED','SPEECH_STOPPED','INTERRUPTION_DETECTED','TURN_STARTED','RESPONSE_COMPLETED') ORDER BY sequence;"
```

**Rebuild after adapter / runtime voice changes:**

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```

**Operator UAT:** Scripted queries, run logs, and open issues (EMI/rate agent gaps, §12.1 7–9) — [UAT_VOICE_SCRIPT.md](./UAT_VOICE_SCRIPT.md).
