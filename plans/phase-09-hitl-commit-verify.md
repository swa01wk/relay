# Relay — Phase 9: HITL commit + verify

## Summary

Implement **HITLManager** and mortgage **protected commit** path: draft → approval → application-backend commit → authoritative verify—without the runtime silently crossing financial boundaries.

**PRD:** §11.2–§11.3, §8.1 (HITL events), §12.2 tools, §15.1 phase 9.

## Depends on

- [Phase 8: State versioning](./phase-08-state-versioning-conflicts.md)

## Relay deliverables

| Area | Target artifact |
|------|-----------------|
| HITLManager | Lifecycle INTENT→…→VERIFY mapped to generic RP events |
| Policy | ToolRegistry blocks side-effecting execution without `APPROVAL_GRANTED` |
| Events | `APPROVAL_REQUESTED`, `APPROVAL_GRANTED`, `APPROVAL_REJECTED`, `COMMIT_STARTED`, `COMMIT_VERIFIED` |
| Web SDK | `on("approval_requested")` — app renders approval UI |
| Audit | Durable correlated approval + commit events in PostgreSQL |

## Mortgage deliverables

| Area | Target artifact |
|------|-----------------|
| Tools | `commit_correction` (protected API + auth), `verify_correction` |
| UI | Application-owned approval modal; authenticated user action |
| Backend | Authoritative mortgage store updated only via commit endpoint |
| Demo | Steps 13–15 (§12.1) |

## HITL lifecycle (generic)

INTENT → INVESTIGATE → DRAFT → VALIDATE → RESOLVE AMBIGUITY → READY_FOR_REVIEW → HUMAN APPROVAL → COMMIT → VERIFY (§11.2).

POC maps stages on RP payloads as `lifecycle_stage`: `READY_FOR_REVIEW` → `HUMAN_APPROVAL` → `COMMIT` → `VERIFY`.

## Tasks

- [x] Classify `commit_correction` as side-effecting in ToolRegistry.
- [x] Runtime emits approval request; does not call commit until client signals grant with auth proof.
- [x] Mortgage backend performs commit; runtime invokes `verify_correction` read.
- [x] Re-read authoritative state into ContextManager post-commit (§11.3).
- [x] Integration tests: reject commit without approval; idempotent commit key.

## Test cases

| ID | Type | Description | Expected |
|----|------|-------------|----------|
| P09-TC-001 | E2E | Approve correction | Backend state updated |
| P09-TC-002 | E2E | Reject approval | No commit; draft remains |
| P09-TC-003 | Integration | Commit without APPROVAL_GRANTED | Blocked at registry |
| P09-TC-004 | E2E | Verify after commit | COMMIT_VERIFIED + UI matches backend |

## Acceptance criteria

- [x] PRD §14.3: draft-only until explicit approval; protected backend commit + verify.
- [x] Audit trail for approval/commit/verify (§11.3) — append-only event store + correlated `commit_id`.
- [x] Agent cannot silently commit (§11.2).
- [x] Full demo narrative completable through step 15 (§12.1) — text path + Playwright.

## Out of scope

Production OIDC control plane, core banking, real money movement.
