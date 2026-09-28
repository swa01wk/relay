# Relay — Phase 8: State versioning + conflicts

## Summary

Implement **StateVersionEngine** with optimistic concurrency: mutations require `based_on_version`; stale agent updates emit `STATE_CONFLICT` and human edits win.

**PRD:** §10.1, §8.1 (STATE_CONFLICT), §3.3 (optimistic concurrency), §15.1 phase 8.

## Depends on

- [Phase 5: Typed actions + shared state](./phase-05-typed-actions-shared-state.md) ✓
- [Phase 6: Parallel tools](./phase-06-parallel-async-tools.md) (draft workflow context) ✓

Phase 7 voice/interrupt is **not** a hard dependency. Open voice UAT agent items ([UAT_VOICE_SCRIPT.md](./UAT_VOICE_SCRIPT.md) UAT-001–004) may be handled in parallel or before Phase 11 demo sign-off.

## Relay deliverables

| Area | Target artifact |
|------|-----------------|
| StateVersionEngine | Validate `based_on_version`; monotonic `state_version` |
| ActionRouter / state commands | Reject or recompute stale agent mutations |
| Web SDK | Surface `state_conflict` to UI (§10.2) |
| AgentAdapter | `handle_runtime_event` for conflict → recompute path |
| EventStore | Persist conflicts for audit |

## Mortgage deliverables

| Area | Target artifact |
|------|-----------------|
| Tools | `prepare_correction` (draft only) |
| UI | Editable draft fields (e.g. effective date) |
| Demo | Steps 10–12: draft → manual edit → agent recompute (§12.1) |

## Key RP events

`STATE_VERSION_ADVANCED`, `STATE_CONFLICT`, updated `STATE_SNAPSHOT` / `STATE_DELTA`.

## Tasks

- [x] Client advances `state_version` immediately on human edit (§10.3).
- [x] Agent state/actions include `based_on_version`; stale → `STATE_CONFLICT`.
- [x] Agent detects conflict and recalculates adjustment from latest state.
- [x] Unit tests: commit with version N-1 fails; human wins.
- [x] Playwright: edit date while agent processing (hook or controlled timing).

## Test cases

| ID | Type | Description | Expected |
|----|------|-------------|----------|
| P08-TC-001 | E2E | Edit draft effective date | Version increments; numbers update |
| P08-TC-002 | E2E | Stale agent update | Conflict UI; date unchanged |
| P08-TC-003 | E2E | Agent recalculates post-conflict | Matches edited date |
| P08-TC-004 | Unit | based_on_version mismatch | STATE_CONFLICT event |

## Acceptance criteria

- [x] PRD §14.3: manual UI edits block stale agent mutations.
- [ ] Demo steps 10–12 complete (§12.1) — voice date change must use routed tool + `STATE_SNAPSHOT` (not LLM-only).
- [x] Conflict pattern documented for future domains ([DECISIONS.md](./DECISIONS.md) D-008-001, D-008-002).

## Out of scope

HITL approval UI and protected commit (Phase 9).

## Risk mitigation

Human/agent race → versioning + STATE_CONFLICT (§15.2).
