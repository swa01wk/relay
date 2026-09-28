# Relay — Phase 4: LLM + streaming TTS

## Summary

Close the **voice output** loop: streaming model output drives streaming TTS and playout through Pipecat SmallWebRTC, with `PlaybackTracker` recording playout progress for later heard-truth (Phase 7).

**PRD:** §6.1 (cascaded STT→LLM→TTS), §7 (heard vs generated prep), §9 (PlaybackTracker, ModelRouter), §15.1 phase 4.

**Status:** Signed off 2026-09-24 · **Decisions:** [DECISIONS.md](./DECISIONS.md) D-004-001–003

## Depends on

- [Phase 3: VAD/STT + TurnManager](./phase-03-vad-stt-turn-manager.md)

## Relay deliverables

| Area | Target artifact |
|------|-----------------|
| ModelRouter | Streaming chat completions via `ModelProvider` |
| TTS adapter | `TextToSpeechProvider` — streaming audio frames to Pipecat |
| AgentRuntime | Stream tokens → TTS sentence/chunk strategy |
| PlaybackTracker | Track playout cursor; emit `SPEECH_STARTED`, `SPEECH_PROGRESS`, `SPEECH_STOPPED` |
| TurnManager | AGENT_SPEAKING state; TURN_COMPLETE after playout |
| Cancellation hooks | Token for cancel TTS/model (used heavily in Phase 7) |

## Mortgage deliverables

| Area | Target artifact |
|------|-----------------|
| UI | Agent speaking indicator; optional text mirror of response |
| Demo | Spoken answer to simple mortgage question (no tools yet) |

## Key RP events

`RESPONSE_STARTED`, `RESPONSE_DELTA`, `SPEECH_STARTED`, `SPEECH_PROGRESS`, `SPEECH_STOPPED`, `RESPONSE_COMPLETED`, `TURN_COMPLETED`.

## Tasks

- [x] Pipeline: STT final → ContextManager → AgentRuntime → TTS → WebRTC out (§6.1).
- [x] Measure first-audio latency user stop-speaking → agent audio (§14.1) — RP `METRIC` events (`voice.user_stop_to_first_audio_ms`, etc.); OTel spans in Phase 10.
- [x] Store `generated_text` on response completion; PlaybackTracker stores delivery progress.
- [x] Web SDK: `on("agent_activity")` or equivalent for speaking state.
- [x] Integration test with mocked TTS frames for latency unit tests (`runtime/tests/test_voice_tts_integration.py`).

## Test cases

| ID | Type | Description | Expected | Sign-off |
|----|------|-------------|----------|----------|
| P04-TC-001 | E2E | Voice question → hear spoken reply | Audio plays; response events emitted | Browser @ :3000 |
| P04-TC-002 | E2E | Text fallback still works | Regression on Phase 1 path | pytest + live Docker WS |
| P04-TC-003 | Integration | Cancel TTS mid-playback | Playout stops; events consistent | pytest |
| P04-TC-004 | Metric | Log TTFT + first TTS byte | Present in event log (`METRIC`); trace spans Phase 10 | pytest |

## Acceptance criteria

- [x] Low-latency spoken response in happy path (subjective + logged metrics).
- [x] Generated text persisted separately from playout progress fields.
- [x] TTS/model swappable via adapters (§14.3).
- [x] Turn FSM includes AGENT_SPEAKING (§6.2).

## Implementation notes (sign-off)

- **LLM:** `ReferenceTextAgent.stream_turn()` → `OpenAIProvider.stream_completion()`; `AgentRuntime.run_streaming_turn()` publishes `RESPONSE_*` and optional token feed to TTS.
- **TTS:** `DeepgramTextToSpeechProvider` (Flux `/v2/speak`, end turn on `SpeechMetadata`) + `MockTextToSpeechProvider` when no key; see [D-004-002](./DECISIONS.md#d-004-002-tts-adapter-and-webrtc-egress), [D-004-004](./DECISIONS.md#d-004-004-tts-cancel-vs-next-utterance) (cancel vs next utterance).
- **Playout:** Session actor → `TextToSpeechProvider` → `RealtimeTransport.push_output_pcm` → `AgentAudioOutputProcessor` → SmallWebRTC out; `PlaybackTracker` emits `SPEECH_*`.
- **Text + voice connected:** batch speak after text turns — [D-004-005](./DECISIONS.md#d-004-005-spoken-replies-when-webrtc-connected); lifecycle [VOICE_LIFECYCLE.md](./VOICE_LIFECYCLE.md).
- **Metrics:** `model.ttft_ms`, `voice.first_tts_byte_ms`, `voice.user_stop_to_first_audio_ms` on RP `METRIC`.

## Out of scope

UI actions, tools, barge-in (Phase 7), optimistic state conflicts.
