# Relay POC — testing strategy

Aligned with **PRD §14.2–§14.3** and per-phase test cases in `phase-*.md`. Phase **exit** criteria and milestone checklists live in [STATUS.md](./STATUS.md). **Pass/pending status:** [ACCEPTANCE_TRACKER.md](./ACCEPTANCE_TRACKER.md).

## Principles

1. **Contract-first:** RP event schemas and adapter port signatures are tested without mortgage domain knowledge.
2. **Deterministic core:** TurnManager, InterruptionManager, and StateVersionEngine get state-machine and race tests independent of LLM nondeterminism.
3. **Mortgage as validation surface:** Playwright E2E lives under `examples/mortgage-servicing/frontend/e2e/` and exercises the public Web SDK only.
4. **Real providers in integration/E2E:** Use live OpenAI/Deepgram (or configured adapters) behind env-gated CI secrets—no fake transcript injection that bypasses STT (PRD §6.1 auditability).
5. **Trace completeness:** Every user turn must be reconstructable from correlated `event_id`, `turn_id`, `trace_id` (PRD §14.2).

## Test pyramid

| Layer | Location (target) | Scope |
|-------|---------------------|--------|
| Unit | `packages/protocol/`, `runtime/tests/`, `packages/web-sdk/` | Schema validation, version engine, turn FSM transitions |
| Contract | `packages/protocol/tests/`, `adapters/*/tests/` | Adapter boundaries; no Pipecat types in RP exports |
| Integration | `runtime/tests/integration/`, `services/gateway/tests/` | Session actor serialization, EventGateway, tool registry |
| E2E | `examples/mortgage-servicing/frontend/e2e/specs/` | Phase-tagged Playwright specs (`phase-NN-*.spec.ts`) |
| UAT | Manual + Phase 11 seeded demo | Full §12.1 scenario with failure injection |

---

## POC acceptance criteria (PRD §14.3)

These are the **program-level** gates. Phase 11 UAT and regression smoke must evidence each item; track completion in [STATUS.md](./STATUS.md) § POC definition of done.

| Criterion | How testing proves it | Primary tests / phases |
|-----------|------------------------|-------------------------|
| Core mortgage journey completable primarily by voice (§12.1) | Full seeded UAT script; voice path for investigation → interrupt → draft → approve | P11-TC-001; phases 3–9 E2E |
| Interruption commits heard/delivered content only (§7) | `HEARD_TEXT_COMMITTED`: heard ⊆ generated; context after interrupt excludes unplayed tail | P07-TC-002, P07-TC-003; unit FSM |
| No Pipecat/framework types in public RP or SDK contracts (§5, §9) | Import-linter + contract tests on `packages/protocol`, `packages/web-sdk` | P00-TC-002; P02 contract; P11-TC-004 |
| Model and speech providers swappable via adapters (§9.2) | Mock `ModelProvider` / STT / TTS behind ports; mortgage app unchanged | P02-TC-002; P11-TC-004 |
| Manual UI edits block stale agent mutations (§10) | Stale `based_on_version` → `STATE_CONFLICT`; human field wins | P08-TC-002, P08-TC-004 |
| Parallel read-only investigations without blocking conversation (§6, §11.1) | Parallel tool spans; user can speak while tools run; stale results dropped | P06-TC-002, P06-TC-004; P10-TC-002 |
| Financial correction draft-only until explicit approval (§11.2) | Commit blocked without `APPROVAL_GRANTED`; reject path leaves draft | P09-TC-002, P09-TC-003 |
| Commit via protected backend + post-commit verify (§12.2) | Backend mutation only on approved commit; verify matches authoritative store | P09-TC-001, P09-TC-004 |
| Full session reconstructable from events/traces (§14.2) | Event log + OTel join reproduces turn narrative | P01-TC-004; P10-TC-004 |
| LiveKit can replace SmallWebRTC without domain/runtime API changes (§5.3) | `RealtimeTransport` swap; LiveKit stub compiles; session logic unchanged | P02-TC-002; Phase 11 contract |

**Sign-off:** All rows satisfied + P11-TC-005 green + operator-repeatable UAT script (Phase 11 acceptance).

---

## Phase acceptance criteria

A phase is **done** when every bullet below holds **and** its gate tests pass. Detailed milestones: [STATUS.md](./STATUS.md).

### Phase 0 — Foundation

| Acceptance | Gate tests |
|------------|------------|
| Repo layout matches PRD §13.2; no mortgage logic under `runtime/` or `packages/protocol` | Review + CI layout checks |
| RP versioned; §8.1 event names and §8.2 metadata enforced in schema tests | P00-TC-001, P00-TC-002 |
| All §5.2 adapter ports defined and documented | Review + import boundaries |
| Health and session connection demonstrable from mortgage frontend shell | P00-TC-003, P00-TC-004 |
| CI runs protocol contract tests on every change | CI workflow |

### Phase 1 — Text session loop

| Acceptance | Gate tests |
|------------|------------|
| Text-only mortgage turn completes through public Web SDK | P01-TC-001 |
| One session owner; concurrent events serialized (§6.3) | P01-TC-002 |
| Turn FSM rejects illegal transitions | P01-TC-003 |
| Turn reconstructable from append-only event log | P01-TC-004 |
| No Pipecat/LangGraph types in RP or web-sdk public API | Contract suite |
| Provider keys server-side only (§11.3) | Config / security review |

### Phase 2 — Pipecat SmallWebRTC

| Acceptance | Gate tests |
|------------|------------|
| Browser establishes SmallWebRTC audio path to runtime | P02-TC-001 |
| `RealtimeTransport` mock swap leaves session logic unchanged | P02-TC-002 |
| Session end closes WebRTC cleanly | P02-TC-003 |
| LiveKit stub present; no mortgage code in Pipecat adapter | Contract + review |
| Connection setup latency logged (aggregated in Phase 10) | Manual / metric hook |

### Phase 3 — VAD/STT + voice turns

| Acceptance | Gate tests |
|------------|------------|
| Stable voice turns with explicit endpointing events (§6.3) | P03-TC-001, P03-TC-002 |
| Voice Turn FSM matches §6.2 | P03-TC-003 |
| Mid-utterance cancel without duplicate turns | P03-TC-004 |
| STT swappable via adapter (§14.3) | Adapter contract |
| One active turn owner per session | P01-TC-002 pattern + voice |
| Mortgage UI shows streaming and final transcript | P03-TC-001 (UI assertion) |

### Phase 4 — LLM + streaming TTS

| Acceptance | Gate tests |
|------------|------------|
| Voice question → spoken reply with consistent RP events | P04-TC-001 |
| Phase 1 text path still works (regression) | P04-TC-002 |
| TTS cancel mid-playback; events consistent | P04-TC-003 |
| TTFT and first TTS byte present in traces | P04-TC-004 |
| `generated_text` persisted separately from playout progress | Integration assertion |
| TTS/model swappable via adapters | Adapter contract |
| Turn FSM includes AGENT_SPEAKING (§6.2) | FSM unit tests |

### Phase 5 — Typed actions + shared state

| Acceptance | Gate tests |
|------------|------------|
| Typed UI actions over RP; app owns rendering (§10.3) | P05-TC-001, P05-TC-002 |
| Semantic state visible to agent via ContextManager | P05-TC-003 |
| Unknown action → `ACTION_FAILED` with reason | P05-TC-004 |
| Demo §12.1 step 4: search + open case | P05-TC-001, P05-TC-002 |
| No EMI/rate domain types in `packages/protocol` | Contract / import scan |

### Phase 6 — Parallel / async tools

| Acceptance | Gate tests |
|------------|------------|
| Parallel investigations without blocking conversation (§14.3) | P06-TC-002 |
| Tool governance metadata on registry entries (§11.1) | Registry unit tests |
| Demo §12.1 steps 5–6 (payment + rate with progress) | P06-TC-001, P06-TC-002 |
| Tool timeout → `TOOL_CALL_FAILED`; agent recovers | P06-TC-003 |
| Stale tool result ignored after new turn | P06-TC-004 |
| Side-effecting commit not callable without HITL | P09-TC-003 (forward dependency) |

### Phase 7 — Interruption + heard-truth

| Acceptance | Gate tests |
|------------|------------|
| Barge-in stops agent audio quickly | P07-TC-001 |
| §14.3: interruption commits heard/delivered content only | P07-TC-002 |
| Post-interrupt context and UI correct (e.g. rate history) | P07-TC-003 |
| Side-effecting tool in flight does not commit on interrupt | P07-TC-004 |
| TTS speaks on turn after barge-in cancel | `test_mock_tts_speaks_after_cancel` ([D-004-004](./DECISIONS.md#d-004-004-tts-cancel-vs-next-utterance)) |
| Event history preserves generated vs heard | P07-TC-002 + log audit |
| Demo §12.1 steps 7–9 achievable by voice | P07-TC-003 |
| Interrupt is runtime state change, not frontend-only | Architecture review + E2E |
| Post-interrupt TTS on next turn | `test_mock_tts_speaks_after_cancel` ([D-004-004](./DECISIONS.md#d-004-004-tts-cancel-vs-next-utterance)) |

**Manual voice UAT (operator):** [UAT_VOICE_SCRIPT.md](./UAT_VOICE_SCRIPT.md). Agent-quality gaps (EMI history wording, parallel compare phrasing) are **not** Phase 7 exit blockers; track as UAT-001–004 until Phase 11.

### Phase 8 — State versioning + conflicts

| Acceptance | Gate tests |
|------------|------------|
| Human edit advances version; numbers/UI update | P08-TC-001 |
| Agent/voice “change date to …” updates draft via tools + RP state (not LLM-only) | P08-TC-001b (Playwright) + `test_mortgage_agent_correction_date` |
| §14.3: stale agent mutation blocked; human edit wins | P08-TC-002 (Playwright slow race or manual banner) |
| Agent recalculates from latest state after conflict | P08-TC-003 |
| `based_on_version` mismatch emits `STATE_CONFLICT` | P08-TC-004 |
| Demo §12.1 steps 10–12 complete | P08-TC-001–001b + manual voice @ :3000 |

### Phase 9 — HITL commit + verify

| Acceptance | Gate tests |
|------------|------------|
| Approve → backend updated | P09-TC-001 |
| Reject → no commit; draft remains | P09-TC-002 |
| Commit without `APPROVAL_GRANTED` blocked at registry | P09-TC-003 |
| Post-commit verify: `COMMIT_VERIFIED` + UI matches backend | P09-TC-004 |
| Audit trail for approval / commit / verify (§11.3) | Event log assertions |
| Agent cannot silently commit (§11.2) | P09-TC-003 + E2E |
| Full demo narrative through §12.1 step 15 | P09-TC-001, P09-TC-004 |

### Phase 10 — Observability + evals

| Acceptance | Gate tests |
|------------|------------|
| Single voice turn: spans for STT, model, TTS | P10-TC-001 |
| Parallel tools: child spans per `tool_call_id` | P10-TC-002 |
| HITL path: approval + commit spans linked | P10-TC-003 |
| §14.3: full turn reconstructable from event log + traces | P10-TC-004 |
| Latency waterfall visible for POC tuning (§14.1) | Metrics dashboard / export |
| Failures and interruptions observable as product metrics | Phase 7/11 injection runs |

### Phase 11 — Hardening + UAT

| Acceptance | Gate tests |
|------------|------------|
| Full §12.1 voice-first journey on seeded data | P11-TC-001 |
| STT timeout injection: graceful error, recoverable session | P11-TC-002 |
| Transport disconnect: reconnect or clean failure UX | P11-TC-003 |
| Provider swap at adapter boundary; mortgage app unchanged | P11-TC-004 |
| Regression smoke phases 0–9 green | P11-TC-005 |
| All [STATUS.md](./STATUS.md) §14.3 DoD boxes checked | UAT sign-off |
| Deterministic UAT repeatable by third operator from script only | Manual UAT |
| §15.2 risk mitigations verified or gaps documented | Review checklist |

---

## PRD-mandated test themes

| Theme | PRD | Primary phases | Acceptance hook |
|-------|-----|----------------|-----------------|
| RP schema contract tests | §14.2 | 0 | P00-TC-002 |
| TurnManager + interruption FSM | §14.2 | 3, 7 | P03-TC-003; P07-TC-001–004 |
| Cancellation races (TTS, model, tools) | §14.2 | 4, 6, 7 | P04-TC-003; P06-TC-004; Phase 11 load suite |
| State-version conflict | §14.2 | 8 | P08-TC-002, P08-TC-004 |
| Tool idempotency + approval boundary | §14.2 | 6, 9 | P09-TC-003 |
| Seeded mortgage E2E | §14.2 | 11 | P11-TC-001 |
| Failure injection (timeout, reconnect) | §14.2 | 11 | P11-TC-002, P11-TC-003 |
| Trace reconstruction | §14.2 | 10, 11 | P10-TC-004; P01-TC-004 |

## Latency waterfall (PRD §14.1)

Instrument and assert (soft budgets in dev; hard gates in Phase 10):

| Stage | Metrics | Phase 10 acceptance |
|-------|---------|---------------------|
| Transport | Connection setup, reconnects | Span present; P11-TC-003 |
| Turn detection | Endpointing delay, false endpoints | Span + optional budget |
| STT | First partial, final transcript latency | P10-TC-001 |
| Model | TTFT, total latency, cancel latency | P04-TC-004 |
| Tools | Parallel latency, stale-result suppression | P10-TC-002; P06-TC-004 |
| TTS | First-audio latency, cancel on interrupt | P04-TC-004; P07-TC-001 |
| E2E | User stop-speaking → agent first audio | P04-TC-004 |
| UX | Interruptions, conflicts, failed actions | P07-*, P08-*, P05-TC-004 |

## Playwright conventions

- One spec file per phase where UI validation applies (phases 1, 5–9, 11).
- Voice phases (3–4, 7): use fixture audio as mic input where supported; still route through WebRTC → STT.
- `data-testid` hooks on mortgage UI for selected entity, draft fields, approval controls.
- Timeouts generous for real API latency; mark smoke vs full demo in CI workflow.
- Map spec files to gate IDs where practical (e.g. `phase-05-actions.spec.ts` covers P05-TC-001–003).

## CI outline (target)

1. Lint + unit + contract tests on every PR.
2. Integration tests with stub adapters where secrets absent.
3. Nightly or manual workflow with `OPENAI_API_KEY`, `DEEPGRAM_API_KEY` for voice E2E.
4. Phase gate: do not mark a phase complete in [STATUS.md](./STATUS.md) until that phase’s acceptance table rows and gate tests pass.

See [MODELS_AND_KEYS.md](./MODELS_AND_KEYS.md) for env configuration.
