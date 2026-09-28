# Relay — Phase 11: Hardening + deterministic UAT

## Summary

Production-readiness for **POC/UAT**: seeded fixtures, failure injection, deterministic demo script, and verification of **§14.3** acceptance criteria end-to-end—including voice-first §12.1 journey.

**PRD:** §12.1, §14.2–§14.3, §15.1 phase 11, §15.2 risks.

## Depends on

- All prior phases 0–10

## Relay deliverables

| Area | Target artifact |
|------|-----------------|
| Failure injection | Configurable STT/TTS/model/tool timeouts and transport disconnect |
| Resilience | Reconnect path for SmallWebRTC; session resumability where feasible |
| Deterministic seeds | Fixed Postgres fixtures + expected correction outcome |
| UAT script | Step-by-step operator guide matching §12.1 utterances |
| CI smoke | Short E2E subset; full demo marked manual/nightly |
| Documentation | [ACCEPTANCE_TRACKER.md](./ACCEPTANCE_TRACKER.md) + STATUS.md |

## Mortgage deliverables

| Area | Target artifact |
|------|-----------------|
| Fixtures | Rajesh Sharma, MORT-2931, repricing audit scenario data |
| Frontend | Stable `data-testid`s for UAT automation |
| Playwright | `phase-11-uat-demo.spec.ts` — full or staged scenario |

## Primary demo scenario (acceptance anchor)

Operator prompt (§12.1): open Rajesh Sharma mortgage, investigate EMI increase, compare three months, rate change, prepare correction—plus interrupt, edit, approve, commit, verify (steps 1–15).

## Tasks

- [x] Seed database with reproducible audit/rate discrepancy narrative (in-memory seeds + tools API).
- [x] Implement failure toggles via env for each adapter (§14.2 failure injection).
- [ ] Run cancellation race suite (TTS, model, tools) under load (§14.2) — **Pending** load harness.
- [x] Verify LiveKit adapter compiles but is not required for UAT (§14.3 transport swap).
- [x] Contract test: public packages import-clean of Pipecat/LangGraph types (CI import-linter).
- [ ] Sign off checklist in [STATUS.md](./STATUS.md) §14.3 — **Pending** voice UAT + pending E2E.
- [ ] Record demo video or trace bundle for stakeholder UAT — **Pending** operator.

## Test cases

| ID | Type | Description | Expected |
|----|------|-------------|----------|
| P11-TC-001 | UAT | Full §12.1 voice-first journey | All steps pass with seeded data |
| P11-TC-002 | E2E | STT timeout injection | Graceful error; session recoverable |
| P11-TC-003 | E2E | Transport disconnect mid-session | Reconnect or clean failure UX |
| P11-TC-004 | Contract | Swap ModelProvider mock in runtime | Mortgage app unchanged |
| P11-TC-005 | Regression | Phase 0–9 smoke suite | Green |

## Acceptance criteria

- [ ] All [STATUS.md](./STATUS.md) POC definition-of-done boxes checked.
- [ ] Deterministic UAT demo repeatable by third operator using script only.
- [ ] Known risks from §15.2 have verified mitigations or documented gaps.
- [x] Relay demonstrably reusable without mortgage code path in core packages.

## Out of scope

Kubernetes deploy, multi-region, telephony, LiveKit production rollout ([POST_POC_BOUNDARIES.md](./POST_POC_BOUNDARIES.md)).

## Post-POC handoff

Capture lessons for LiveKit migration, second domain reference app, and control-plane backlog (§15.3).
