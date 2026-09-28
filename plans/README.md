# Relay POC — phase-by-phase implementation plans

Authoritative product spec: [`Relay_Final_PRD_16_Pages.docx`](../Relay_Final_PRD_16_Pages.docx) (September 2026).

These documents translate **PRD §15.1 (vertical implementation sequence)** into implementable slices. Each phase delivers **Relay platform** capability first, then proves it through the **mortgage reference app** as an external consumer—never by embedding mortgage concepts in the runtime core.

## Product boundary (invariants)

- **Relay** is domain-agnostic: session, turn, action, state, approval, conflict—not EMI, rate history, or refunds.
- **Pipecat** is an implementation substrate (frames, SmallWebRTC); it is **not** the public contract.
- **Relay Protocol (RP)** is the canonical interaction contract; RTVI/AG-UI are optional adapters (PRD §8.3).
- **Mortgage backend** is authoritative for committed business state after HITL commit (PRD §11.3).
- **Transport evolution**: POC = Pipecat + SmallWebRTC → post-POC = LiveKit adapter without changing RP/runtime APIs (PRD §5).

## Repository baseline (this workspace)

As of plan authoring, the repo contains only the Final PRD and git metadata—**no application or runtime code**. All paths below are **targets** from PRD §13.2.

```text
relay/
├── packages/
│   ├── protocol/          # RP schemas, IDs, validation
│   ├── web-sdk/             # Thin client: session, transport, events, state
│   └── python-sdk/
├── runtime/                 # SessionManager, TurnManager, … (Python + FastAPI)
├── adapters/
│   ├── realtime/pipecat/    # small_webrtc.py, livekit.py (stub post-POC)
│   ├── models/ speech/ agents/ persistence/
├── services/
│   ├── gateway/
│   └── observability/
├── examples/mortgage-servicing/
│   ├── frontend/ agent/ tools/ fixtures/
└── infra/
    ├── docker/
    └── otel/
```

## Implementation phases (PRD §15.1)

| Phase | Plan | Relay capability | Mortgage proof |
|-------|------|------------------|----------------|
| 0 | [phase-00-foundation.md](./phase-00-foundation.md) | Repo, RP IDs/schemas, adapter ports | Health + session connection |
| 1 | [phase-01-text-session-loop.md](./phase-01-text-session-loop.md) | SessionManager + text loop | Text-only mortgage turn |
| 2 | [phase-02-pipecat-small-webrtc.md](./phase-02-pipecat-small-webrtc.md) | Pipecat SmallWebRTC transport | Realtime audio connection |
| 3 | [phase-03-vad-stt-turn-manager.md](./phase-03-vad-stt-turn-manager.md) | VAD/STT + TurnManager | Stable voice turns |
| 4 | [phase-04-llm-streaming-tts.md](./phase-04-llm-streaming-tts.md) | LLM + streaming TTS | Low-latency spoken response |
| 5 | [phase-05-typed-actions-shared-state.md](./phase-05-typed-actions-shared-state.md) | Typed actions + shared state | Open mortgage case; UI sync |
| 6 | [phase-06-parallel-async-tools.md](./phase-06-parallel-async-tools.md) | Parallel/async tools | Payment + rate checks w/ progress |
| 7 | [phase-07-interruption-heard-truth.md](./phase-07-interruption-heard-truth.md) | Interruption + heard-truth | Barge-in; correct memory |
| 8 | [phase-08-state-versioning-conflicts.md](./phase-08-state-versioning-conflicts.md) | State versions + conflicts | Human edit wins |
| 9 | [phase-09-hitl-commit-verify.md](./phase-09-hitl-commit-verify.md) | HITL commit + verify | Draft → approve → commit → verify |
| 10 | [phase-10-observability-evals.md](./phase-10-observability-evals.md) | Observability + evals | Latency waterfall; trace timeline |
| 11 | [phase-11-hardening-uat.md](./phase-11-hardening-uat.md) | Hardening | Failure injection; deterministic UAT |

**Progress:** [STATUS.md](./STATUS.md)

## How the plan docs work together

| Doc | When to use it |
|-----|----------------|
| **This README** | Orientation: boundaries, repo layout, phase index, §12.1 mapping |
| **[STATUS.md](./STATUS.md)** | Track each phase (status, milestones, POC §14.3 DoD, risks). Check milestones during implementation. |
| **[ACCEPTANCE_TRACKER.md](./ACCEPTANCE_TRACKER.md)** | Gate test pass/pending matrix and pending action queue |
| **[TESTING.md](./TESTING.md)** | Prove a phase is done: acceptance criteria + gate tests (P00-TC-001, …). Same criteria for program-level DoD. |
| **[UAT_VOICE_SCRIPT.md](./UAT_VOICE_SCRIPT.md)** | Voice @ :3000 operator script, run logs, open issues (UAT-001…). |
| **[DECISIONS.md](./DECISIONS.md)** | Locked choices that implementation should follow unless superseded here |
| **`phase-NN-*.md`** | Full scope, tasks, and authoritative test-case tables for that phase |

**Phase sign-off:** A phase is complete on STATUS only when **implementation milestones**, **TESTING.md acceptance**, and **gate tests** for that phase all pass—not when code is merged alone. Phase 11 + STATUS §14.3 checkboxes close the POC.

## Supporting docs

| Doc | Purpose |
|-----|---------|
| [STATUS.md](./STATUS.md) | Live tracker: phase status, milestones, POC definition of done (PRD §14.3) |
| [TESTING.md](./TESTING.md) | Acceptance criteria, gate tests, pyramid, CI (PRD §14.2–§14.3) |
| [UAT_VOICE_SCRIPT.md](./UAT_VOICE_SCRIPT.md) | Manual voice UAT script, session run logs, tracked gaps (agent/demo) |
| [VOICE_LIFECYCLE.md](./VOICE_LIFECYCLE.md) | Mic→speaker debug reference (ingress, TTS, barge-in) |
| [MODELS_AND_KEYS.md](./MODELS_AND_KEYS.md) | Provider defaults behind adapters (PRD §13.1) |
| [DECISIONS.md](./DECISIONS.md) | Accepted POC choices (VAD, adapters, env)—update as phases progress |
| [POST_POC_BOUNDARIES.md](./POST_POC_BOUNDARIES.md) | Explicit non-goals and post-POC roadmap (PRD §2.2, §15.3) |
| [GUARDRAILS_AND_SANITIZATION.md](./GUARDRAILS_AND_SANITIZATION.md) | User-facing leak prevention: routing, prompts, streaming sanitizer; strategic placement options |

## Architecture planes (quick reference)

| Plane | PRD | Owned by |
|-------|-----|----------|
| Realtime / media | §4.1, §5, §6 | Pipecat adapters + PlaybackTracker plumbing |
| Conversation / agent | §6, §9 | TurnManager, ContextManager, AgentRuntime, ModelRouter |
| UI / event | §8, §10 | EventGateway, ActionRouter, StateVersionEngine |
| Control | §11.3 | Session tokens, project/agent config |
| Persistence / observability | §14 | EventStore, TraceManager, PostgreSQL/Redis |

## Primary demo scenario

End-state validation follows PRD §12.1 (Rajesh Sharma EMI investigation → interrupt → draft → human edit → approve → commit → verify). Phases 5–9 map directly to steps 4–15; phases 0–4 enable steps 1–3; phases 10–11 prove §14.3 acceptance and operational readiness.
