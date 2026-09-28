# Relay POC — decision log

Record **product and engineering choices** that phases depend on. Update when a decision is made or superseded—not on every implementation detail.

**Status:** `Accepted` (in force) · `Superseded` (replaced by a later ID) · `Proposed` (not yet agreed)

| ID | Phase | Topic | Status | Date |
|----|-------|--------|--------|------|
| [D-003-001](#d-003-001-voice-turn-detection-vad--muteui) | 3 | Voice turn detection (VAD + mute UI) | Accepted | 2026-09-24 |
| [D-003-002](#d-003-002-stt-adapter-shape-for-poc) | 3 | STT adapter shape for POC | Accepted | 2026-09-24 |
| [D-003-003](#d-003-003-deepgram-credentials-for-e2e) | 3 | Deepgram credentials for E2E | Accepted | 2026-09-24 |
| [D-003-004](#d-003-004-smallwebrtc-mic-track-binding-race) | 3 | SmallWebRTC mic track binding race | Accepted | 2026-09-24 |
| [D-003-006](#d-003-006-hybrid-vad--smart-turn-endpointing) | 3 | Hybrid VAD + Smart Turn endpointing | Accepted | 2026-09-25 |
| [D-003-005](#d-003-005-smallwebrtc-audio-receiver-idle) | 3 | SmallWebRTC audio receiver idle | Accepted | 2026-09-25 |
| [D-004-001](#d-004-001-mute-vs-voice_cancel) | 4 | Mute vs `VOICE_CANCEL` | Accepted | 2026-09-24 |
| [D-004-002](#d-004-002-tts-adapter-and-webrtc-egress) | 4 | TTS adapter and WebRTC egress | Accepted | 2026-09-24 |
| [D-004-003](#d-004-003-deepgram-flux-tts-turn-completion) | 4 | Deepgram Flux TTS turn completion | Accepted | 2026-09-24 |
| [D-004-004](#d-004-004-tts-cancel-vs-next-utterance) | 4 | TTS `cancel()` vs next utterance | Accepted | 2026-09-25 |
| [D-004-005](#d-004-005-spoken-replies-when-webrtc-connected) | 4 | Spoken replies when WebRTC connected | Accepted | 2026-09-25 |
| [D-005-001](#d-005-001-state-sync-snapshot-only-phase-5) | 5 | State sync snapshot-only (Phase 5) | Accepted | 2026-09-25 |
| [D-005-002](#d-005-002-mortgage-tools-and-agent-boundary) | 5 | Mortgage tools + agent boundary | Accepted | 2026-09-25 |
| [D-005-003](#d-005-003-typed-action-envelope-and-client-handlers) | 5 | Typed action envelope + client handlers | Accepted | 2026-09-25 |
| [D-005-004](#d-005-004-searchopen-workflow-for-poc) | 5 | Search/open workflow for POC | Accepted | 2026-09-25 |
| [D-006-001](#d-006-001-toolregistry-and-registrytoolexecutor) | 6 | ToolRegistry + RegistryToolExecutor | Accepted | 2026-09-25 |
| [D-006-002](#d-006-002-activity-events-for-parallel-bundles-only) | 6 | `ACTIVITY_*` for parallel bundles only | Accepted | 2026-09-25 |
| [D-006-003](#d-006-003-paymentrate-deterministic-routes) | 6 | Payment/rate deterministic routes | Accepted | 2026-09-25 |
| [D-006-004](#d-006-004-side-effecting-tools-blocked-until-hitl) | 6 | Side-effecting tools blocked until HITL | Accepted | 2026-09-25 |
| [D-011-001](#d-011-001-krisp-ai-frontend-noise-cancellation) | 11 | Krisp AI frontend noise cancellation (target) | Accepted | 2026-09-25 |
| [D-011-002](#d-011-002-no-webrtc-nsaecagc-toggles-poc) | 11 | No WebRTC NS/AEC/AGC toggles (POC) | Accepted | 2026-09-25 |

---

## D-003-001 — Voice turn detection (VAD + mute UI)

**Status:** Accepted · **Date:** 2026-09-24 · **Plan:** [phase-03](./phase-03-vad-stt-turn-manager.md)

**Context:** Phase 3 needs endpointing for voice turns. Options included hands-free VAD, push-to-talk only, or both.

**Decision**

- **Default:** VAD **auto-endpoint** (Flux / TurnDetector drives `USER_SPEECH_STARTED` / `USER_SPEECH_ENDED` and turn finalization).
- **UI:** Provide **Mute** and **Unmute** controls on the mortgage shell (and Web SDK hooks as needed). Muting stops sending mic audio to the runtime; it is **not** a substitute for endpointing logic.
- **Not default for POC:** Push-to-talk as the primary mode (may add later behind a flag if debugging requires it).

**Consequences**

- P03-TC-001 / E2E demos assume speak → pause → transcript final without a PTT button.
- **P03-TC-002** in the phase plan (“hold-to-talk release”) is interpreted as **VAD endpoint → `TURN_PROCESSING`**, not push-to-talk (PTT not default for POC).
- Mute: client disables mic tracks (`track.enabled`). **Amended Phase 4 ([D-004-001](#d-004-001-mute-vs-voice_cancel)):** muting does **not** send `VOICE_CANCEL`; use **`cancelVoiceUtterance()`** / server cancel to abort an open utterance or agent playout.
- **Open speakers:** Muting is the supported POC mitigation for echo and false barge-in until [D-011-001](#d-011-001-krisp-ai-frontend-noise-cancellation) lands; do **not** rely on shell toggles for noise suppression / echo cancellation / auto gain ([D-011-002](#d-011-002-no-webrtc-nsaecagc-toggles-poc)).
- Mortgage shell shows `SESSION_ERROR` if the user sends text while a voice utterance is still open.

---

## D-003-006 — Hybrid VAD + Smart Turn endpointing

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-03](./phase-03-vad-stt-turn-manager.md) · **Amends:** [D-003-001](#d-003-001-voice-turn-detection-vad--mute-ui)

**Context:** Silero-only endpointing split long utterances on short pauses and felt late on barge-in follow-ups. Pipecat 1.11 ships **Smart Turn v3** (local ONNX) for semantic end-of-turn while keeping VAD for speech start.

**Decision**

- **Default (`RELAY_TURN_DETECTOR=hybrid`):** Pipecat ingress = `VADProcessor(Silero)` → STT → `UserTurnProcessor` with `TurnAnalyzerUserTurnStopStrategy(LocalSmartTurnAnalyzerV3)`.
- **Turn start strategies:** `VADUserTurnStartStrategy` only — not Pipecat’s default `TranscriptionUserTurnStartStrategy` (STT-driven starts caused spurious `broadcast_interruption` / split turns on open speakers).
- **Speech start (incl. barge-in):** `VADUserStartedSpeakingFrame` → Relay `on_speech_started` (fast path unchanged in runtime).
- **Speech end / commit:** `UserTurnProcessor` stop strategy (Smart Turn + STT final gating) → Relay `on_speech_ended`.
- **Fallback:** `RELAY_TURN_DETECTOR=silero` restores legacy `RelayVadProcessor` (VAD start and end).

**Consequences**

- Gateway image needs ONNX runtime (via Pipecat smart-turn bundle); first session pays model load cost.
- Tune `RELAY_SMART_TURN_*` and `RELAY_ENDPOINTING_SILENCE_MS` separately — VAD `stop_secs` is an input to Smart Turn, not the sole end signal.
- See [VOICE_LIFECYCLE.md](./VOICE_LIFECYCLE.md) for pipeline diagram update.

---

## D-003-002 — STT adapter shape for POC

**Status:** Accepted · **Date:** 2026-09-24 · **Plan:** [phase-03](./phase-03-vad-stt-turn-manager.md)

**Context:** STT can be implemented as a native `SpeechToTextProvider` (e.g. Deepgram WebSocket) or by wrapping Pipecat’s Deepgram live service inside `adapters/speech/` or `adapters/realtime/pipecat/`, as long as Pipecat types do not leak into `packages/protocol` or `@relay/web-sdk`.

**Decision**

- For the POC, **either approach is acceptable**; pick the path of least friction during Phase 3 implementation.
- **Invariant:** STT remains **swappable via the port** (§14.3); prefer [MODELS_AND_KEYS.md](./MODELS_AND_KEYS.md) defaults (Deepgram Flux live WS).
- **Post-POC:** Revisit if latency, testing, or multi-provider needs favor a single pattern.

**Consequences**

- Contract tests target `SpeechToTextProvider`, not a specific vendor SDK in runtime core.
- No requirement to refactor STT wiring before Phase 4 unless a concrete problem appears.

**Implementation (Phase 3 sign-off)**

- Production path: Pipecat `DeepgramSTTService` in the SmallWebRTC voice pipeline (`build_pipecat_stt_service`), with Silero `TurnDetector` ahead of STT.
- `DEEPGRAM_STT_MODEL` values containing `flux` are mapped to **`nova-3-general`** at runtime because Pipecat’s adapter uses Deepgram listen v1 (see env warning in gateway logs).

---

## D-003-003 — Deepgram credentials for E2E

**Status:** Accepted · **Date:** 2026-09-24 · **Plan:** [phase-03](./phase-03-vad-stt-turn-manager.md)

**Context:** Real STT gate tests (P03-TC-001) need server-side Deepgram access per [MODELS_AND_KEYS.md](./MODELS_AND_KEYS.md).

**Decision**

- **`DEEPGRAM_API_KEY` (and related STT model env) are configured** in `infra/docker/.env` for local and Docker gateway runs.
- CI may continue to use mocks when keys are absent; **local sign-off** assumes Docker gateway with keys loaded.

**Consequences**

- Phase 3 exit validation includes a live spoken phrase against Docker `:8080` + UI at `:3000`.
- Do not commit `.env`; keep `.env.example` in sync with required variable names only.

---

## D-003-004 — SmallWebRTC mic track binding race

**Status:** Accepted · **Date:** 2026-09-24 · **Plan:** [phase-03](./phase-03-vad-stt-turn-manager.md) (builds on [phase-02](./phase-02-pipecat-small-webrtc.md))

**Context:** Pipecat’s `SmallWebRTCClient` can receive ICE **connected** before transport `setup()` sets `_params`. The stock `on_connected` handler then skips mic track binding; a later `connect()` no-ops when the peer is already up, so RTP never reaches VAD/STT despite a green “voice connected” UI and local mic level.

**Decision**

- Apply a **Relay-side monkey patch** in `adapters/realtime/pipecat/webrtc_fixup.py`: after `setup()` and after `connect()`, bind input tracks when `_audio_input_track` is still unset and `audio_input_track()` is available—**without** relying on `is_connected()` (false until `connect()` is invoked).
- Keep the fix inside the Pipecat adapter layer; do not change RP or Web SDK contracts.

**Consequences**

- Docker gateway must be rebuilt after adapter changes; browser E2E at `:3000` is the authoritative Phase 3 media gate (host→Docker `voice_smoke.py` RTP remains best-effort only).
- If Pipecat fixes upstream ordering, revisit whether the patch can be removed.

---

## D-003-005 — SmallWebRTC audio receiver idle

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-03](./phase-03-vad-stt-turn-manager.md) · **Amends:** [D-003-004](#d-003-004-smallwebrtc-mic-track-binding-race)

**Context:** Pipecat 1.11 `SmallWebRTCTrack._idle_watcher` disables the **audio receiver** after ~2s without RTP. Gateway logs showed `Timeout: No audio frame received` and `Disabling receiver for audio track`, with no `voice pipeline audio ingress` — mic uplink appeared dead while ICE stayed connected.

**Decision**

- Extend `webrtc_fixup.py` to patch `_idle_watcher`: for **audio** tracks, discard stale queued frames on idle but **keep the receiver enabled**; video/screen tracks unchanged.
- Add ingress logging in `RelayVadProcessor` (first frame + every 250 frames) for UAT.

**Consequences**

- Rebuild Docker gateway after adapter changes.
- See [VOICE_LIFECYCLE.md](./VOICE_LIFECYCLE.md) debugging section for log patterns.

---

## D-004-001 — Mute vs `VOICE_CANCEL`

**Status:** Accepted · **Date:** 2026-09-24 · **Plan:** [phase-04](./phase-04-llm-streaming-tts.md) · **Amends:** [D-003-001](#d-003-001-voice-turn-detection-vad--muteui) (mute consequences only)

**Context:** Phase 4 runs agent + TTS after `TRANSCRIPT_FINAL`. Sending `VOICE_CANCEL` on **Mute** set `voice_cancelled` on the server, so the user saw a final transcript but **no agent response** (turn never started).

**Decision**

- **Mute / Unmute:** Web SDK only toggles `MediaStreamTrack.enabled` — **no** RP message.
- **Cancel utterance:** Explicit `cancelVoiceUtterance()` → `VOICE_CANCEL` on the control WebSocket; server cancels open user utterance or in-flight agent playout (Phase 7 extends barge-in).
- Mortgage shell: separate **Cancel utterance** control; copy clarifies “unmute to speak.”

**Consequences**

- Muting during agent speech does not by itself stop TTS (true barge-in is Phase 7).
- P03 “cancel mid-utterance” tests still use server cancel APIs; UI must not conflate mute with cancel.

---

## D-004-002 — TTS adapter and WebRTC egress

**Status:** Accepted · **Date:** 2026-09-24 · **Plan:** [phase-04](./phase-04-llm-streaming-tts.md)

**Context:** Phase 4 needs streaming TTS on the hot path without leaking Pipecat types into `runtime/` or RP. Options: Pipecat `DeepgramFluxTTSService` inside the media pipeline vs `TextToSpeechProvider` feeding PCM from the session actor.

**Decision**

- Implement **`TextToSpeechProvider`** in `adapters/speech/deepgram/` (`DeepgramTextToSpeechProvider` + `MockTextToSpeechProvider` for tests/CI).
- **Session actor** streams LLM tokens into TTS concurrently with RP `RESPONSE_DELTA` publication.
- **Egress:** `PipecatSmallWebRtcTransport.push_output_pcm` → **`AgentAudioOutputProcessor`** (background pump, independent of mic ingress) → `SmallWebRTCTransport` output @ `DEEPGRAM_TTS_SAMPLE_RATE` (default 24000).
- **Invariant:** Same as STT — swappable port; no Pipecat imports in `packages/protocol` / public Web SDK.

**Consequences**

- TTS runs outside the mic→STT Pipecat chain but shares the same WebRTC peer via the output processor.
- Live Docker sign-off uses Deepgram Flux Speak v2 when `DEEPGRAM_API_KEY` is set.

---

## D-004-003 — Deepgram Flux TTS turn completion

**Status:** Accepted · **Date:** 2026-09-24 · **Plan:** [phase-04](./phase-04-llm-streaming-tts.md)

**Context:** Flux `/v2/speak` keeps the WebSocket open across turns. Reading until socket close hung the session actor and blocked voice turns.

**Decision**

- After sending `Flush`, read messages until JSON **`SpeechMetadata`** (end of turn for that utterance), with a recv **timeout** fallback.
- Do **not** treat **`Flushed`** alone as end-of-turn (audio may still follow).
- Log **`Error`** payloads and fail the TTS stream for that turn.

**Consequences**

- Port-level TTS matches Pipecat Flux semantics documented in upstream `DeepgramFluxTTSBase`.
- Container smoke test: non-zero PCM byte count before sign-off.

---

## D-004-004 — TTS `cancel()` vs next utterance

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-04](./phase-04-llm-streaming-tts.md), [phase-07](./phase-07-interruption-heard-truth.md)

**Context:** Barge-in calls `TextToSpeechProvider.cancel(session_id)`. `DeepgramTextToSpeechProvider.synthesize_stream` treated a pending cancel flag as “skip entire next stream,” so **the turn immediately after an interrupt often had text but no `SPEECH_STARTED`** (UAT session event audit).

**Decision**

- **`cancel()`** applies only to the **in-flight** synthesize stream (break recv/send loops).
- Each **new** `synthesize_stream` **clears** the session cancel flag and speaks normally.
- Regression: `adapters/speech/deepgram/tests/test_tts_provider.py::test_mock_tts_speaks_after_cancel`.
- Safety net: if a voice turn finishes with no playout, `SessionManager` batch-fallback via `_speak_assistant_if_voice_connected`.

**Consequences**

- Event timeline after interrupt should show `SPEECH_STARTED` on subsequent turns when WebRTC is connected.
- Documented in [VOICE_LIFECYCLE.md](./VOICE_LIFECYCLE.md) barge-in section.

---

## D-004-005 — Spoken replies when WebRTC connected

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-04](./phase-04-llm-streaming-tts.md)

**Context:** Users expect **Send (text)** to be spoken when **Voice: connected**; previously only STT-final **voice turns** drove TTS.

**Decision**

- **Voice turn:** streaming tokens → `SpeechTextStream` → `play_tts_stream` (unchanged).
- **Text turn:** after `run_text_turn`, if `RealtimeTransport.is_connected`, speak **`plain_text_for_speech(full reply)`** in one batch (`_speak_assistant_if_voice_connected`).
- **Browser:** `webrtc-media.ts` uses `addTransceiver(..., sendrecv)` and Web Audio + `<audio>` for agent downlink; mortgage UI shows mic level when voice is connected.

**Consequences**

- Without WebRTC connected, text and voice logic remain text-only on the speaker path (RP transcripts still flow).
- Requires gateway + frontend rebuild for UAT.

---

## D-005-001 — State sync snapshot-only (Phase 5)

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-05](./phase-05-typed-actions-shared-state.md)

**Context:** RP catalog includes `STATE_DELTA` and `STATE_CONFLICT`; Phase 8 owns optimistic versioning and human-edit wins.

**Decision**

- Phase 5 client → runtime sync uses **full `STATE_SNAPSHOT`** only (Web SDK `sendState`).
- Runtime bumps monotonic **`state_version`** and emits `STATE_VERSION_ADVANCED`; latest snapshot is stored in **ContextManager** for the agent.
- **`STATE_DELTA`** is not produced or merged in Phase 5 (schema remains for later phases).

**Consequences**

- P05-TC-003 is satisfied via snapshot + `screen` / `selected_entity` in semantic state.
- Shared-state UI may show nested `search_results` (tool payload) alongside case fields until Phase 8+ UX polish.

---

## D-005-002 — Mortgage tools + agent boundary

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-05](./phase-05-typed-actions-shared-state.md)

**Context:** PRD requires domain logic outside `runtime/` and `packages/protocol`; tools must be HTTP-callable per agent config.

**Decision**

- **Read tools** live in `examples/mortgage-servicing/tools/` (FastAPI `search_customer`, `get_mortgage`; in-memory seeds for POC).
- **`MortgageServicingAgent`** lives in `examples/mortgage-servicing/agent/`; gateway wires it via `relay-mortgage-agent`.
- **`HttpToolExecutor`** (`adapters/tools/http/`) calls `RELAY_MORTGAGE_TOOLS_URL` (Docker: `http://mortgage-tools:8090`). When unset, **`LocalMortgageToolExecutor`** uses the same seeds in-process for pytest/CI.

**Consequences**

- No EMI/rate/mortgage types in protocol; runtime only sees generic tool names and JSON results.
- Postgres-backed tool seeds are optional post-POC; compose adds a dedicated `mortgage-tools` service.

---

## D-005-003 — Typed action envelope + client handlers

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-05](./phase-05-typed-actions-shared-state.md)

**Context:** UI actions must flow over RP with the app owning rendering (§10.3).

**Decision**

- **`ACTION_REQUESTED`** payload: `action` (name), `action_id`, `params` (object).
- Web SDK **`registerAction(name, handler)`** runs on the client; success → `ACTION_APPLIED`, missing handler or throw → `ACTION_FAILED` with `reason`.
- Runtime **ActionRouter** publishes requests; correlates client replies; EventStore persists the action/state event family.

**Consequences**

- P05-TC-004: unknown action → `ACTION_FAILED` / `no_handler_registered` (integration + SDK default).
- Mortgage shell registers `SHOW_SEARCH_RESULTS` and `OPEN_ENTITY` only; other action names fail closed on the client.

---

## D-005-004 — Search/open workflow for POC

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-05](./phase-05-typed-actions-shared-state.md)

**Context:** Phase 5 must prove search → open case (Rajesh / MORT-2931) reliably in CI and manual UAT, without waiting on model tool-calling quality.

**Decision**

- **`MortgageServicingAgent`** uses a **deterministic workflow** for search/open intents (keyword routing → `ToolExecutor` → `request_action` for UI).
- General questions fall through to **`ModelProvider`** streaming; agent context includes **`state_summary_for_agent()`** so follow-ups can reference the current screen/case.
- OpenAI **function/tool API** is not required for Phase 5 exit; Phase 6 adds **ToolRegistry** governance and RP tool events while keeping keyword workflows ([D-006-003](#d-006-003-paymentrate-deterministic-routes)).

**Consequences**

- Demo phrases like “Find Rajesh Sharma” and “Open MORT-2931” are stable; paraphrases depend on LLM unless patterns are extended.
- Manual UAT (2026-09-25) confirmed search/open UI sync and state-aware follow-ups with live model.

---

## D-006-001 — ToolRegistry + RegistryToolExecutor

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-06](./phase-06-parallel-async-tools.md)

**Context:** Phase 6 requires tool governance (§11.1), parallel async execution, timeouts, and RP `TOOL_CALL_*` correlation without embedding mortgage types in `runtime/`.

**Decision**

- **`ToolRegistry`** in `runtime/` holds per-tool JSON schema metadata and **`read_only` / `draft` / `side_effecting`** classification; validates I/O at the executor boundary.
- **`RegistryToolExecutor`** wraps the port **`ToolExecutor`** delegate (`HttpToolExecutor` or `LocalMortgageToolExecutor`); gateway registers mortgage tools via `register_mortgage_tools()` in the example agent package.
- **`AgentRuntime`** injects `run_tool` / `run_tools_parallel` into agent context (publish + `ContextManager` merge); mortgage agent no longer calls the raw delegate directly.

**Consequences**

- P06-TC-003 / P06-TC-004 satisfied via executor timeout and `ContextManager.begin_turn()` / stale suppression.
- Tool names and HTTP URLs remain config-driven per [D-005-002](#d-005-002-mortgage-tools-and-agent-boundary).

---

## D-006-002 — `ACTIVITY_*` for parallel bundles only

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-06](./phase-06-parallel-async-tools.md)

**Context:** RP defines both `TOOL_CALL_*` and `ACTIVITY_*`; the mortgage UI activity panel must reflect user-visible multi-step work without noise on every single tool call.

**Decision**

- Emit **`ACTIVITY_STARTED` / `ACTIVITY_PROGRESS` / `ACTIVITY_COMPLETED`** only when **`execute_parallel`** runs with an **`activity_label`** (e.g. payment + rate investigation).
- Single-tool paths (`run_tool`, including `get_payments` and Phase 5 `search_customer`) emit **`TOOL_CALL_*`** only; the activity panel stays empty — **expected**, not a failure.

**Consequences**

- P06-TC-002 Playwright asserts activity UI on the parallel phrase; P06-TC-001 payment-only phrase asserts chat/`TOOL_CALL_*` without activity rows.
- Future UX may list completed activities or rename panel copy; out of scope for Phase 6 exit.

---

## D-006-003 — Payment/rate deterministic routes

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-06](./phase-06-parallel-async-tools.md)

**Context:** Demo steps 5–6 must be reliable in CI; model tool-calling quality is not a gate.

**Decision**

- Extend **`MortgageServicingAgent`** keyword routing ([D-005-004](#d-005-004-searchopen-workflow-for-poc)):
  - **Payment compare** → `get_payments` (single `run_tool`).
  - **Payment + rate / rate history / investigate** → parallel `get_payments` + `get_rate_history` with spoken progress + optional **`SHOW_RATE_HISTORY`** action.
- **`mortgage_id`** from shared state `selected_entity`, utterance, or default **MORT-2931**.
- **`get_audit_history`** and **`calculate_adjustment`** are registered and HTTP-exposed but **not** keyword-routed in the agent (available for later phases / LLM tool API).

**Consequences**

- Stable demo phrases documented in README / manual UAT; paraphrases may hit LLM-only answers without tool RP events.
- Voice and text share the same agent code paths once a turn is finalized.

---

## D-006-004 — Side-effecting tools blocked until HITL

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-06](./phase-06-parallel-async-tools.md)

**Context:** Phase 9 owns commit/verify with approval; Phase 6 must classify but not execute side-effecting work.

**Decision**

- Register **`commit_correction`** as **`side_effecting`** in the mortgage ToolRegistry.
- **`RegistryToolExecutor`** rejects execution with **`side_effecting_blocked_until_hitl`** (no delegate call); emits **`TOOL_CALL_FAILED`** when publish metadata is present.

**Consequences**

- Phase 6 exit: commit not callable without HITL policy (Phase 9 wires approval + execution).
- `calculate_adjustment` remains **`draft`** (read-only projection math), not a ledger commit.

---

## D-008-001 — Optimistic state versioning (Phase 8)

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-08](./phase-08-state-versioning-conflicts.md)

**Context:** PRD §10.1 / §3.3 require human UI edits to win over stale agent mutations; RP catalog includes `STATE_DELTA` and `STATE_CONFLICT`.

**Decision**

- **`StateVersionEngine`** in runtime: client **`STATE_SNAPSHOT`** always applies and bumps version; agent **`STATE_DELTA`** requires `based_on_version == context.state_version` or runtime emits **`STATE_CONFLICT`** (no merge).
- Web SDK tracks **`stateVersion`**, supports **`optimisticAdvance`** on human edits (§10.3), and surfaces **`onStateConflict` / `state_conflict`**.
- Agents mutate shared state via **`apply_state_delta(patch, based_on_version=…)`** (captures version at mutation start — e.g. before slow tools).
- **`AgentAdapter.handle_runtime_event`**: optional hook; mortgage agent recalculates draft on conflict via **`recalculate_correction_draft`** + fresh delta.

**Consequences**

- P08-TC-004: deterministic unit tests without LLM; E2E uses **`prepare_correction`** + **`_slow_ms`** race with editable effective date.
- Future domains reuse the same pattern: human snapshot authority, agent deltas with `based_on_version`, conflict → recompute path.

---

## D-008-002 — Draft date updates + post-conflict UI (Phase 8)

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-08](./phase-08-state-versioning-conflicts.md)

**Context:** Manual UAT showed `STATE_CONFLICT` working, but voice “update date to 2026” was answered by the LLM without updating `correction_draft` in shared state. Post-conflict recompute forced `screen: correction_draft` while the operator was on rate history.

**Decision**

- Mortgage agent **routes** draft effective-date changes (including affirmations like “Yeah, update” after a dated request) to **`recalculate_correction_draft`** + **`apply_state_delta`** + **`SHOW_CORRECTION_DRAFT`** — never LLM-only confirmation.
- **`handle_runtime_event`** after conflict applies a **draft-only** patch when the user is on another screen (e.g. rate history); full draft screen patch when preparing or explicitly updating the draft.
- Client merges **`STATE_SNAPSHOT`** so nested fields (`correction_draft`, `rate_history`, …) update without dropping local view data.
- Client **state** and **action results** are applied **inline** during in-flight turns (not queued behind the session actor).

**Consequences**

- Demo §12.1 step 11: voice or text “change date to …” keeps UI, shared state, and assistant copy aligned.
- Playwright slow-tool race (P08-TC-002/003) remains environment-sensitive; manual banner + pytest cover the engine.

---

## D-011-001 — Krisp AI frontend noise cancellation

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-11](./phase-11-hardening-uat.md) · **Related:** [UAT-002](./UAT_VOICE_SCRIPT.md#uat-002) · [D-011-002](#d-011-002-no-webrtc-nsaecagc-toggles-poc) · [VOICE_LIFECYCLE.md](./VOICE_LIFECYCLE.md)

**Context:** Open-speaker and room noise caused false barge-in, agent TTS cutoffs, and garbled STT in voice UAT ([UAT-002](./UAT_VOICE_SCRIPT.md#uat-002)). A short-lived POC experiment exposed explicit WebRTC **`noiseSuppression`**, **`echoCancellation`**, and **`autoGainControl`** toggles in the mortgage shell and `@relay/web-sdk`; UAT on laptop speakers was worse (cutoffs, loopback). That path is **reverted** — see [D-011-002](#d-011-002-no-webrtc-nsaecagc-toggles-poc).

**Decision**

- **Primary capture cleanup (target, not yet implemented):** Integrate **Krisp AI** on the **mic path** before audio is sent on SmallWebRTC (processed `MediaStream` or Krisp SDK hook).
- **Placement:** Client-only — `examples/mortgage-servicing/frontend/` and **`@relay/web-sdk`** (`webrtc-media.ts` or a thin Krisp wrapper). **No** Krisp in `runtime/`, gateway, or Pipecat adapters for the POC.
- **UI (when Krisp lands):** Single operator toggle (on by default for demo), e.g. “Noise cancellation (Krisp)”—**not** a revival of per-constraint NS/AEC/AGC checkboxes.
- **Until Krisp ships:** `getUserMedia({ audio: true })` only; operators use **Mute mic** while the agent speaks or headphones ([D-003-001](#d-003-001-voice-turn-detection-vad--muteui)).

**Consequences**

- Phase 11 hardening includes Krisp wiring + one manual voice pass with open speakers in [UAT_VOICE_SCRIPT.md](./UAT_VOICE_SCRIPT.md).
- Krisp credentials (if required) live in **frontend env** only (e.g. `NEXT_PUBLIC_*`)—not in `infra/docker/.env` server secrets unless a server-side path is explicitly decided later.
- STT/VAD tuning ([D-003-006](#d-003-006-hybrid-vad--smart-turn-endpointing)) and runtime barge-in policy (VAD start, not STT partials during agent playout) remain; Krisp is complementary.
- Relay core stays vendor-agnostic: Krisp is **example-app + web-sdk media**, same boundary as [D-005-002](#d-005-002-mortgage-tools-and-agent-boundary).

---

## D-011-002 — No WebRTC NS/AEC/AGC toggles (POC)

**Status:** Accepted · **Date:** 2026-09-25 · **Plan:** [phase-11](./phase-11-hardening-uat.md) · **Supersedes:** interim WebRTC constraint UI described under [D-011-001](#d-011-001-krisp-ai-frontend-noise-cancellation) (2026-09-25 experiment) · **Related:** [D-003-001](#d-003-001-voice-turn-detection-vad--muteui) · [D-004-001](#d-004-001-mute-vs-voice_cancel)

**Context:** The mortgage shell briefly offered checkboxes for **noise suppression**, **echo cancellation**, and **auto gain control**, wired through `RelaySession.setAudioProcessing()` to `getUserMedia` / `applyConstraints` in `packages/web-sdk/src/webrtc-media.ts`. On open-speaker UAT this correlated with **agent speech cutting off** and the **mic picking up TTS** (echo + false barge-in). Forcing constraints on/off did not give a stable §12.1 demo across Chrome/macOS.

**Decision**

- **Do not ship** explicit NS/AEC/AGC toggles or SDK APIs for the POC. Removed from mortgage `page.tsx` and `@relay/web-sdk`.
- **Mic capture:** `navigator.mediaDevices.getUserMedia({ audio: true, video: false })` — rely on **browser defaults** for whatever processing the OS applies; do not set `{ noiseSuppression, echoCancellation, autoGainControl }` in application code unless a future decision (e.g. Krisp or a vetted AEC strategy) requires it.
- **Agent playback:** Remote TTS via a single **`<audio>`** element only (no parallel route to `AudioContext.destination`), to avoid extra speaker bleed.
- **Barge-in during agent playout:** **VAD `speech_started` fast path only** — STT **partials must not** trigger barge-in (speaker bleed was cancelling TTS).
- **Operator mitigation:** **Mute mic** while the agent is speaking when testing on speakers; headphones for hands-free demos.

**Consequences**

- Future noise/echo work goes through [D-011-001](#d-011-001-krisp-ai-frontend-noise-cancellation) (Krisp on capture), not restored constraint checkboxes.
- [VOICE_LIFECYCLE.md](./VOICE_LIFECYCLE.md) documents echo/cutoff symptoms and mitigations.
- Re-introducing NS/AEC/AGC UI requires a new decision ID and UAT on target devices (open speaker + headset).

---

## Template (copy for new decisions)

```markdown
## D-NNN-XXX — Title

**Status:** Proposed · **Date:** YYYY-MM-DD · **Plan:** [phase-NN-…](./phase-NN-….md)

**Context:** …

**Decision:** …

**Consequences:** …
```
