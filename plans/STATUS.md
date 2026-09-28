# Relay POC — implementation status

**Overall status:** In progress — Phases 0–7 signed off; **Phases 8–11 implemented — sign-off pending** (see [ACCEPTANCE_TRACKER.md](./ACCEPTANCE_TRACKER.md))  
**Last updated:** 2026-09-28 — Phase 10 timeline API + Phase 11 failure injection; pending voice UAT + full-stack Playwright  
**Spec:** [Relay_Final_PRD_16_Pages.docx](../Relay_Final_PRD_16_Pages.docx)

Update this file when a phase is **signed off** (milestones + [TESTING.md](./TESTING.md) acceptance and gate tests)—not on implementation alone. Scope detail: linked `phase-NN-*.md` plans.

## Phase summary

| Phase | Plan | Relay capability | Mortgage validation | PRD §12.1 demo | Status | Owner | Notes |
|-------|------|------------------|---------------------|----------------|--------|-------|-------|
| 0 | [phase-00](./phase-00-foundation.md) | Repo, RP schemas, adapter ports | Health/session connection | — (enables 1–3) | Signed off | | P00-TC-001–004 pass (local pytest, Docker Compose, frontend build) |
| 1 | [phase-01](./phase-01-text-session-loop.md) | SessionManager + text loop | Text-only mortgage turn | — (enables 1–3) | Signed off | | P01-TC-001–004; UI + live `gpt-5.4-mini` via `infra/docker/.env` |
| 2 | [phase-02](./phase-02-pipecat-small-webrtc.md) | Pipecat SmallWebRTC | Realtime audio connection | — (enables 1–3) | Signed off | | P02-TC-001–003; browser voice connected @ :3000 |
| 3 | [phase-03](./phase-03-vad-stt-turn-manager.md) | VAD/STT + TurnManager | Stable voice turns | — (enables 1–3) | Signed off | | P03-TC-001–004; live STT + text agent reply @ :3000 (TTS Phase 4) |
| 4 | [phase-04](./phase-04-llm-streaming-tts.md) | LLM + streaming TTS | Spoken agent response | Steps 1–3 (voice loop) | Signed off | | P04-TC-001–004; voice + transcript @ :3000 |
| 5 | [phase-05](./phase-05-typed-actions-shared-state.md) | Typed actions + shared state | Open case; UI sync | Step 4 (search + open) | Signed off | | P05 gates + Playwright; manual: Find Rajesh → case + state-aware follow-ups ([DECISIONS](./DECISIONS.md) D-005-*) |
| 6 | [phase-06](./phase-06-parallel-async-tools.md) | Parallel/async tools | Payment/rate progress | Steps 5–6 | Signed off | | P06 gates + Playwright; parallel `ACTIVITY_*` + tools ([DECISIONS](./DECISIONS.md) D-006-*) |
| 7 | [phase-07](./phase-07-interruption-heard-truth.md) | Interruption + heard-truth | Barge-in; memory | Steps 7–9 | Signed off | | P07-TC-001–004 pytest; Playwright P07-TC-003; voice §12.1 7–9 manual @ :3000 → Phase 11 |
| 8 | [phase-08](./phase-08-state-versioning-conflicts.md) | State versioning + conflicts | Human edit wins | Steps 10–12 | Implemented — exit tests pending | | Manual: conflict banner @ :3000; Playwright P08-TC-002/003 flaky in CI stack |
| 9 | [phase-09](./phase-09-hitl-commit-verify.md) | HITL commit + verify | Approve → commit → verify | Steps 13–15 | Implemented — exit tests pending | | P09 pytest + `test_p09_hitl_ws.py`; Playwright P09-TC-001–004; voice step 13–15 → Phase 11 |
| 10 | [phase-10](./phase-10-observability-evals.md) | Observability + evals | Latency + trace timeline | Full §12.1 traced | Implemented — exit tests pending | | P10 pytest green; `/dev/sessions/{id}/timeline` |
| 11 | [phase-11](./phase-11-hardening-uat.md) | Hardening | Deterministic UAT demo | Full §12.1 voice-first UAT | Implemented — exit tests pending | | Injection env + `phase-11-uat-demo.spec.ts`; voice UAT manual |

---

## Phase milestones

Check milestones as work completes. **Exit** = that phase’s acceptance criteria and gate tests in [TESTING.md](./TESTING.md) (source test IDs in linked `phase-NN-*.md`).

### Phase 0 — Foundation

**Plan:** [phase-00-foundation.md](./phase-00-foundation.md) · **Depends on:** none · **Demo:** infrastructure for §12.1 steps 1–3

**Relay**

- [x] Monorepo layout per PRD §13.2 (workspaces, `packages/`, `runtime/`, `adapters/`, `services/gateway/`, `infra/docker/`)
- [x] `packages/protocol/` — RP event enums, JSON schemas, `protocol_version`, canonical metadata (§8.2)
- [x] `packages/python-sdk/` — shared event models for runtime/agents
- [x] Port interfaces defined: `RealtimeTransport`, `SpeechToTextProvider`, `TextToSpeechProvider`, `TurnDetector`, `ModelProvider`, `AgentAdapter`, `ToolExecutor`, `StateStore`, `EventStore`, `EventPublisher` (§5.2)
- [x] SessionManager / EventGateway / TraceManager skeletons (correlation IDs, publish stub)
- [x] Gateway: FastAPI `/health`, `/ready`; dev session token mint (POC-only)
- [x] Docker Compose: Redis + PostgreSQL + gateway healthcheck
- [x] CI: lint, protocol contract tests, import rules blocking adapter types in `packages/protocol`
- [x] Contract tests: all §8.1 event names round-trip; required metadata on every event

**Mortgage**

- [x] `examples/mortgage-servicing/frontend/` — Next.js + shadcn shell; `projectId` / `agentId` env only
- [x] Frontend demonstrates health + session connection (no business UI)

**Validation (tests → exit)**

- [x] P00-TC-001–004 pass (schema validation, contract catalog, `/health`, dev token + `SESSION_READY`)
- [x] **Exit:** repo matches §13.2; RP versioned; ports documented; no mortgage logic under `runtime/` or `packages/protocol`; CI green on protocol tests

---

### Phase 1 — SessionManager + text loop

**Plan:** [phase-01-text-session-loop.md](./phase-01-text-session-loop.md) · **Depends on:** Phase 0 · **Demo:** text path toward §12.1

**Relay**

- [x] SessionManager: create/end session, agent + auth context (§9)
- [x] Per-session asyncio queue (single writer / actor ownership §3.3)
- [x] TurnManager text FSM: IDLE → PROCESSING → TURN_COMPLETE (§6.2)
- [x] EventGateway: WebSocket or SSE, RP JSON, sequence numbers
- [x] ContextManager: minimal transcript + state slot
- [x] AgentRuntime + ModelRouter; `OpenAIProvider` behind `ModelProvider`
- [x] AgentAdapter (LangGraph or thin async handler) in `adapters/agents/`
- [x] Web SDK: `createRelaySession`, send user text, `on("transcript")`, connection state (§10.2 subset)
- [x] EventStore: append-only PostgreSQL log; Redis session routing / lock
- [x] RP events wired: `TURN_*`, `TRANSCRIPT_FINAL`, `RESPONSE_*`; persist `turn_id`, `trace_id`

**Mortgage**

- [x] Connect UI, text input, message list via Web SDK only
- [x] Reference agent prompt in `examples/mortgage-servicing/agent/` (no tools)
- [x] Smoke: one text round-trip (“hello” / “who are you?”) — pytest/Docker WebSocket + **browser UI** (`http://localhost:3000`, Connect → Send)
- [x] Live provider: OpenAI via `infra/docker/.env` on Docker gateway (`gpt-5.4-mini`); mock when key absent (CI/local pytest)

**Validation (tests → exit)**

- [x] P01-TC-001–004 pass (E2E text turn, ordered rapid messages, FSM guards, event replay)
- [x] **Exit:** text-only mortgage turn via public Web SDK; no Pipecat/LangGraph in RP or web-sdk API; keys server-side only (§11.3)

---

### Phase 2 — Pipecat SmallWebRTC transport

**Plan:** [phase-02-pipecat-small-webrtc.md](./phase-02-pipecat-small-webrtc.md) · **Depends on:** Phase 1 ✓ · **Demo:** realtime media for §12.1 steps 1–3

**Relay**

- [x] `adapters/realtime/pipecat/small_webrtc.py` implements `RealtimeTransport`
- [x] Pipecat pipeline shell: frame ingress/egress bound to RP `session_id`
- [x] Web SDK: `transport: "small-webrtc"` on existing session (§10.2)
- [x] Two-plane documented: WebRTC media vs RP control (WebSocket/data channel)
- [x] `livekit.py` stub + migration notes (§5.4)
- [x] Reconnect / basic transport errors surfaced in Web SDK
- [x] Contract test: `packages/protocol` imports without Pipecat

**Mortgage**

- [x] Mic permission, voice connect, audio level or “connected” indicator
- [x] Optional loopback/silence check (STT not required yet)

**Validation (tests → exit)**

- [x] P02-TC-001–003 pass (ICE connected, transport mock swap, clean teardown)
- [x] **Exit:** bidirectional SmallWebRTC audio; LiveKit stub present; no mortgage code in Pipecat adapter; connection setup latency logged

---

### Phase 3 — VAD/STT + TurnManager (voice turns)

**Plan:** [phase-03-vad-stt-turn-manager.md](./phase-03-vad-stt-turn-manager.md) · **Depends on:** Phase 2 ✓ · **Demo:** voice input for §12.1 · **Decisions:** [DECISIONS.md](./DECISIONS.md) D-003-001–004

**Relay**

- [x] `SpeechToTextProvider` + Deepgram (or Pipecat STT) behind port
- [x] TurnDetector: VAD/endpointing → `USER_SPEECH_STARTED` / `USER_SPEECH_ENDED`
- [x] TurnManager voice FSM: USER_SPEAKING → ENDPOINTING → PROCESSING (§6.2)
- [x] Pipecat: mic → VAD → STT → Relay turn events
- [x] Streaming STT partials on EventGateway with sequence ordering
- [x] Turn finalizes on endpointing; AgentRuntime invoked with transcript (text UI response OK until Phase 4)
- [x] Endpointing delay metrics (§14.1 turn detection); replaceable TurnDetector config
- [x] PlaybackTracker stub for Phase 4
- [x] SmallWebRTC deferred mic track binding ([D-003-004](./DECISIONS.md#d-003-004-smallwebrtc-mic-track-binding-race))
- [x] Text during active voice utterance → `SESSION_ERROR` (session actor stays alive)

**Mortgage**

- [x] Live transcript panel (`TRANSCRIPT_DELTA` / `TRANSCRIPT_FINAL`)
- [x] VAD auto-endpoint + Mute/Unmute UI (D-003-001); `SESSION_ERROR` surfaced in shell

**Validation (tests → exit)**

- [x] P03-TC-001–004 pass (spoken phrase @ :3000; VAD endpoint → `TURN_PROCESSING` per [D-003-001](./DECISIONS.md#d-003-001-voice-turn-detection-vad--muteui); FSM unit; cancel mid-utterance)
- [x] **Exit:** stable voice turns (§6.3); STT swappable via adapter ports; one active turn owner; mortgage UI shows streaming + final transcript

---

### Phase 4 — LLM + streaming TTS

**Plan:** [phase-04-llm-streaming-tts.md](./phase-04-llm-streaming-tts.md) · **Depends on:** Phase 3 ✓ · **Demo:** **§12.1 steps 1–3** (voice question → spoken reply) · **Decisions:** [DECISIONS.md](./DECISIONS.md) D-004-001–003

**Relay**

- [x] End-to-end pipeline: STT final → ContextManager → AgentRuntime → TTS → WebRTC out (§6.1)
- [x] `TextToSpeechProvider` (Deepgram Flux v2 WS + mock); PCM → Pipecat `AgentAudioOutputProcessor` → SmallWebRTC out
- [x] PlaybackTracker: `SPEECH_STARTED`, `SPEECH_PROGRESS`, `SPEECH_STOPPED`; playout cursor + `generated_text`
- [x] TurnManager `AGENT_SPEAKING`; `TURN_COMPLETED` after playout when voice transport connected
- [x] `generated_text` on `RESPONSE_COMPLETED`; `TurnCancellation` + cancel model/TTS hooks
- [x] Web SDK `on("agent_activity")` + `SPEECH_*` aliases
- [x] Metrics: `model.ttft_ms`, `voice.first_tts_byte_ms`, `voice.user_stop_to_first_audio_ms`

**Mortgage**

- [x] Agent speaking indicator; text mirror via existing `RESPONSE_*` handlers
- [x] Spoken answer to simple mortgage question (no tools) @ :3000

**Validation (tests → exit)**

- [x] P04-TC-001 — browser voice @ :3000 (spoken reply + assistant transcript)
- [x] P04-TC-002 — text regression (live Docker WS + pytest `test_text_turn_integration`)
- [x] P04-TC-003 — mid-TTS cancel (`test_p04_tc_003_cancel_agent_playback`)
- [x] P04-TC-004 — latency metrics (`test_p04_tc_004_latency_metrics_logged`; live `generated_text` on WS)
- [x] **Exit:** low-latency spoken happy path; generated vs playout separated; FSM includes AGENT_SPEAKING

---

### Phase 5 — Typed actions + shared state

**Plan:** [phase-05-typed-actions-shared-state.md](./phase-05-typed-actions-shared-state.md) · **Depends on:** Phase 4 · **Demo:** **§12.1 step 4** (search + open case)

**Relay**

- [x] ActionRouter: `ACTION_REQUESTED` → client → `ACTION_APPLIED` / `ACTION_FAILED`
- [x] State sync: `STATE_SNAPSHOT`, `STATE_VERSION_ADVANCED`; monotonic `state_version` (`STATE_DELTA` catalog only — patches in Phase 8)
- [x] Web SDK: `registerAction`, `sendState`, `sendEvent` (§10.2)
- [x] Generic action envelope; EventStore persists action/state events
- [x] AgentAdapter emits structured action intents (tool calls or workflow)
- [x] ToolExecutor calls mortgage HTTP tool URLs from config (no domain in `runtime/`)

**Mortgage**

- [x] Read tools API: `search_customer`, `get_mortgage` + in-memory seeds (HTTP service; Postgres optional post-POC)
- [x] UI: case screen, search results, `OPEN_ENTITY` handler
- [x] Shared state shape per §10.1 (`screen`, `selected_entity`, `workflow`, …)
- [x] Voice/text: “Find Rajesh Sharma” → open MORT-2931
- [x] Playwright: text path open Rajesh mortgage (`PLAYWRIGHT_E2E=1 pnpm test:e2e`)

**Validation (tests → exit)**

- [x] P05-TC-001–004 pass (search, open case, state panel, unknown action)
- [x] **Exit:** typed UI actions over RP; semantic state in ContextManager; demo step 4; no EMI/rate types in protocol

**Manual UAT (2026-09-25, operator @ :3000 + Docker gateway)**

- [x] “Find Rajesh Sharma” → assistant confirms match; Application view **MORT-2931** (Rajesh Sharma, active)
- [x] Shared state panel includes `screen: mortgage_case` and selected entity (full JSON also retains `search_results` with both Rajesh mortgages — expected)
- [x] Follow-ups (“Okay”, “Can you explain the mock page?”) grounded in current case/state with live LLM
- [x] RP `ready`, gateway `/health` ok, session WebSocket active (DevTools)

---

### Phase 6 — Parallel / async tools

**Plan:** [phase-06-parallel-async-tools.md](./phase-06-parallel-async-tools.md) · **Depends on:** Phase 5 · **Demo:** **§12.1 steps 5–6** (payment + rate investigation)

**Relay**

- [x] ToolRegistry: schemas, read-only / draft / side-effecting metadata (§11.1)
- [x] ToolExecutor: async parallel calls, timeout, retry (`RegistryToolExecutor`)
- [x] Progress RP events: `TOOL_CALL_*`, `ACTIVITY_*`
- [x] ContextManager merges results; drops stale results if turn superseded (§6.3, §7.3)
- [x] TraceManager correlates `tool_call_id`
- [x] `commit_correction` classified side-effecting — blocked until Phase 9

**Mortgage**

- [x] Tools: `get_payments`, `get_rate_history`, `get_audit_history`, `calculate_adjustment` (deterministic)
- [x] Agent: parallel payment + rate investigation with spoken progress
- [x] UI activity indicators from RP events (parallel bundle only; see D-006-002)

**Validation (tests → exit)**

- [x] P06-TC-001–004 pass (Playwright text payment compare + parallel activity; pytest timeout + stale result; voice uses same agent paths as text)
- [x] **Exit:** parallel tools without blocking conversation (§14.3); demo steps 5–6; commit not callable without HITL

**Manual UAT (2026-09-25, operator @ :3000 + Docker gateway)**

- [x] “Find Rajesh Sharma” → MORT-2931 case; follow-ups via LLM with shared state (Phase 5 regression)
- [x] “Compare last 3 months payments” → deterministic payment summary (`TOOL_CALL_*`; no activity row — expected per D-006-002)
- [x] “Compare payments and rate history…” → activity panel + rate history view + parallel tool RP events
- [x] Playwright: `PLAYWRIGHT_E2E=1` → `e2e/phase-06-tools.spec.ts` (2/2)

---

### Phase 7 — Interruption + heard-truth

**Plan:** [phase-07-interruption-heard-truth.md](./phase-07-interruption-heard-truth.md) · **Depends on:** Phase 4 (+ Phase 6 recommended) · **Demo:** **§12.1 steps 7–9** (barge-in, rate history) · **Lifecycle:** [VOICE_LIFECYCLE.md](./VOICE_LIFECYCLE.md)

**Relay**

- [x] InterruptionManager: VAD during `AGENT_SPEAKING` → interrupt flow (§7.1; `notify_voice_speech_started` fast path)
- [x] PlaybackTracker finalizes heard prefix; `generated_text` vs `heard_text` (§7.2)
- [x] RP: `INTERRUPTION_DETECTED`, `RESPONSE_INTERRUPTED`, `HEARD_TEXT_COMMITTED`, `RESPONSE_CANCELLED`
- [x] Cancellation: TTS immediate; LLM cancel; tool policy per §7.3 (`TurnCancellation`, `RegistryToolExecutor`)
- [x] TurnManager: barge-in `AGENT_SPEAKING` → `USER_SPEAKING` (§6.2)
- [x] ContextManager uses heard_text for subsequent turns (`commit_assistant_heard`)
- [x] Runtime-driven interrupt (not frontend-only)

**Mortgage**

- [x] Real barge-in during TTS (runtime P07-TC-001; not button-only)
- [x] Post-interrupt rate history UI path (Playwright P07-TC-003 — text follow-up; same agent/context as voice interrupt)
- [ ] **Manual UAT:** full §12.1 steps 7–9 by voice @ :3000 (interrupt long EMI → ask rate history) — Phase 11 ([UAT-004](./UAT_VOICE_SCRIPT.md#uat-004))

**Manual UAT log (2026-09-25 @ :3000, session `f20c94f8-5ca6-4bbb-b7c0-003bf8a8c67c`)** — detail: [UAT_VOICE_SCRIPT.md](./UAT_VOICE_SCRIPT.md#run-log--2026-09-25-session-f20c94f8-5ca6-4bbb-b7c0-003bf8a8c67c)

- [x] Voice loop + Rajesh search + email + payments tool + barge-in (events: `SPEECH_STARTED` all turns; TTS after interrupt OK)
- [ ] EMI history uses seeded/honest data ([UAT-001](./UAT_VOICE_SCRIPT.md#uat-001))
- [ ] Parallel payments + rate compare in one voice turn ([UAT-003](./UAT_VOICE_SCRIPT.md#uat-003))
- [ ] Rate history view + §12.1 steps 7–9 script complete ([UAT-004](./UAT_VOICE_SCRIPT.md#uat-004))

**Validation (tests → exit)**

- [x] P07-TC-001–004 pass (pytest `test_phase07_*`, `test_interruption_manager`; 2026-09-25 local venv)
- [x] P07-TC-003 Playwright spec present (`e2e/phase-07-interruption.spec.ts`; run with `PLAYWRIGHT_E2E=1` + stack @ :3000)
- [x] **Exit:** §14.3 heard-only commit on interrupt; event log preserves generated vs heard; runtime gates green

---

### Phase 8 — State versioning + conflicts

**Plan:** [phase-08-state-versioning-conflicts.md](./phase-08-state-versioning-conflicts.md) · **Depends on:** Phases 5–6 ✓ (Phase 7 not required) · **Demo:** **§12.1 steps 10–12** (draft, human edit, recompute) · **Start:** OK — open voice/agent UAT items ([UAT_VOICE_SCRIPT.md](./UAT_VOICE_SCRIPT.md)) do not block this phase

**Relay**

- [x] StateVersionEngine: `based_on_version` validation; monotonic `state_version` (§10.1, §3.3)
- [x] Stale agent mutations → `STATE_CONFLICT`; human edits win (inline client state/actions during turns)
- [x] Web SDK surfaces `state_conflict` + `onStateConflict` (§10.2)
- [x] AgentAdapter `handle_runtime_event` → recompute after conflict (draft-only patch; preserves screen on rate history)
- [x] EventStore persists conflicts for audit (PostgreSQL `relay_events`)

**Mortgage**

- [x] `prepare_correction` / `recalculate_correction_draft` (draft only)
- [x] Editable draft fields (effective date) + agent routed date updates (voice/text; no LLM-only “done”)
- [x] Client advances `state_version` immediately on human edit (§10.3)
- [x] Agent recalculates adjustment from latest state after conflict
- [x] User-facing guard rails: no runtime/handler leak in replies; LLM stream sanitizer + draft month/date routing ([UAT-006](./UAT_VOICE_SCRIPT.md#uat-006))

**Validation (tests → exit)**

- [x] P08-TC-004 pass (pytest); P08-TC-001 pass (Playwright manual edit); P08-TC-001b agent date sync (Playwright)
- [x] P08-TC-002–003 Playwright (`phase-08-state-versioning.spec.ts`; needs `PLAYWRIGHT_E2E=1` + stack @ :8080/:3000)
- [x] Pytest slow-tool race (`test_client_snapshot_applies_during_slow_tool`) — agent pins `based_on_version` before async `prepare_correction`
- [x] [UAT-006](./UAT_VOICE_SCRIPT.md#uat-006) automated: Playwright row #11 + `test_march_voice_phrase_updates_draft_state`
- [ ] **Exit:** Run full Playwright phase-08 + uat-mortgage-script with Docker up; optional voice re-pass §12.1 steps 10–12; then sign off

---

### Phase 9 — HITL commit + verify

**Plan:** [phase-09-hitl-commit-verify.md](./phase-09-hitl-commit-verify.md) · **Depends on:** Phase 8 · **Demo:** **§12.1 steps 13–15** (approve, commit, verify)

**Relay**

- [x] HITLManager: lifecycle stages on RP payloads (`READY_FOR_REVIEW` → … → `VERIFY`)
- [x] RegistryToolExecutor blocks side-effecting tools without granted `approval_id`
- [x] Events: `APPROVAL_*`, `COMMIT_STARTED`, `COMMIT_VERIFIED` (+ tool RP events on commit path)
- [x] Web SDK `onApprovalRequested` / `grantApproval` / `rejectApproval`
- [x] Approval + commit events persisted via `PersistingEventGateway` (PostgreSQL when configured)
- [x] Post-commit `verify_correction` + ContextManager snapshot refresh (§11.3)
- [x] `approval.grant` / `reject` processed immediately (not queued behind long turns)

**Mortgage**

- [x] `commit_correction` (token + idempotency), `verify_correction` on tools API :8090
- [x] Approval modal @ :3000; `RELAY_DEV_APPROVER_TOKEN` auth proof (default `dev-approver`)
- [x] Authoritative store mutated only in `logic.commit_correction`

**Validation (tests → exit)**

- [x] P09-TC-003 — `runtime/tests/test_phase09_hitl.py`
- [x] P09-TC-001/002/004 — `e2e/phase-09-hitl.spec.ts` (with stack running)
- [x] Gateway WS — `services/gateway/tests/test_p09_hitl_ws.py`
- [ ] **Exit:** operator voice UAT steps 13–15 ([UAT_VOICE_SCRIPT.md](./UAT_VOICE_SCRIPT.md)); then sign off with Phase 8 if still open

---

### Phase 10 — Observability + evals

**Plan:** [phase-10-observability-evals.md](./phase-10-observability-evals.md) · **Depends on:** Phase 9 (+ voice stack 2–4) · **Demo:** run full **§12.1** with exportable trace timeline

**Relay**

- [x] `trace_id` on session metadata; `correlation_id` on tool/HITL/commit spans
- [x] RP `TRACE_LINK` stages (`relay.stage.*`) + existing `METRIC` waterfall
- [x] `GET /dev/sessions/{id}/timeline` + `scripts/export_session_timeline.py`
- [x] [OBSERVABILITY_EVAL.md](./OBSERVABILITY_EVAL.md) eval procedure
- [x] CI: `test_phase10_observability.py` on every PR
- [ ] Optional OTLP collector wired (stub in [infra/otel/README.md](../infra/otel/README.md))

**Mortgage**

- [ ] Stakeholder trace export from live §12.1 run — **Pending** operator session

**Validation (tests → exit)**

- [x] P10-TC-001–004 — `runtime/tests/test_phase10_observability.py`
- [ ] **Exit:** export timeline from production-like voice demo; compare waterfall baselines

---

### Phase 11 — Hardening + deterministic UAT

**Plan:** [phase-11-hardening-uat.md](./phase-11-hardening-uat.md) · **Depends on:** Phases 0–10 · **Demo:** **full §12.1 voice-first UAT** (steps 1–15, Rajesh / MORT-2931 narrative)

**Relay**

- [x] Failure injection env: `RELAY_INJECT_MODEL_TIMEOUT`, `RELAY_INJECT_TOOL_TIMEOUT_SEC`, `RELAY_INJECT_TRANSPORT_DISCONNECT`, …
- [x] Transport disconnect metric + inject on SmallWebRTC connect
- [ ] Cancellation race suite under load — **Pending**
- [x] LiveKit stub compiles (`test_p11_tc_004_livekit_stub_imports`)
- [x] import-linter in CI (public package boundaries)
- [x] CI Phase 10–11 pytest; Playwright staged UAT spec
- [ ] Full voice operator UAT + demo artifact — **Pending**

**Mortgage**

- [x] In-memory seeds (Rajesh / MORT-2931); stable `data-testid`s
- [x] `e2e/phase-11-uat-demo.spec.ts` (text-staged §12.1)

**Validation (tests → exit)**

- [x] P11-TC-002–005 subset — `runtime/tests/test_phase11_hardening.py`
- [ ] P11-TC-001 voice-first — manual [UAT_VOICE_SCRIPT.md](./UAT_VOICE_SCRIPT.md)
- [ ] **Exit:** [ACCEPTANCE_TRACKER.md](./ACCEPTANCE_TRACKER.md) pending queue cleared; §14.3 DoD signed

---

## POC definition of done (PRD §14.3)

- [ ] Core mortgage journey completable primarily by voice (§12.1)
- [x] Interruption commits **heard/delivered** content only (§7, PlaybackTracker) — Phase 7 gates
- [x] No Pipecat/framework types in public RP or SDK contracts (§5, §9) — import-linter + contract tests
- [x] Model and speech providers swappable via adapters (§9.2) — P11-TC-004 pattern
- [x] Manual UI edits block stale agent mutations (§10, §8) — P08-TC-002/004 + conflict banner
- [x] Parallel read-only investigations without blocking conversation (§6, §11.1) — Phase 6 gates
- [x] Financial correction draft-only until explicit approval (§11.2) — Phase 9 gates
- [x] Commit via protected application backend + post-commit verify (§12.2 tools) — Phase 9 gates
- [x] Full session reconstructable from events/traces (§14.2) — P10-TC-004 + timeline API
- [x] LiveKit can replace SmallWebRTC without domain/runtime API changes (§5.3) — stub + port boundary

## Risks (track mitigations — PRD §15.2)

| Risk | Mitigation | Status |
|------|------------|--------|
| Pipecat leaks into product API | Ports/adapters + contract tests | |
| SmallWebRTC limits production | Explicit LiveKit adapter path | |
| Unnatural turn detection | Instrument endpointing; replaceable TurnDetector | |
| Interrupt races | Central cancellation tokens | Mitigated (Phase 7) |
| Generated vs heard text | PlaybackTracker + HEARD_TEXT_COMMITTED | Mitigated (Phase 7) |
| Human/agent state race | Optimistic versioning + STATE_CONFLICT | |
| Agent framework lock-in | AgentAdapter boundary | |
| Over-engineering | Vertical phases; defer control plane | |
