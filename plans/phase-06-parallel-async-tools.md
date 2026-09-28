# Relay — Phase 6: Parallel / async tools

## Summary

Implement **ToolRegistry** with read-only and long-running tools, parallel execution, progress events, and stale-result suppression after turn changes.

**PRD:** §11.1, §8.1 (TOOL_*, ACTIVITY_*), §15.1 phase 6.

## Depends on

- [Phase 5: Typed actions + shared state](./phase-05-typed-actions-shared-state.md)

## Relay deliverables

| Area | Target artifact |
|------|-----------------|
| ToolRegistry | Schemas, classification (read-only / draft / side-effecting metadata) |
| ToolExecutor | Async parallel calls with timeout, retry policy |
| Progress | `TOOL_CALL_PROGRESS`, `ACTIVITY_STARTED` / `ACTIVITY_PROGRESS` / `ACTIVITY_COMPLETED` |
| ContextManager | Merge tool results; drop stale results if turn superseded (§6.3, §7.3) |
| TraceManager | `tool_call_id` correlation |

## Mortgage deliverables

| Area | Target artifact |
|------|-----------------|
| Tools | `get_payments`, `get_rate_history`, `get_audit_history`, `calculate_adjustment` (deterministic) |
| Agent | Parallel payment + rate investigation with spoken progress updates |
| UI | Activity/progress indicators from RP events |

## Key RP events

`TOOL_CALL_STARTED`, `TOOL_CALL_PROGRESS`, `TOOL_CALL_COMPLETED`, `TOOL_CALL_FAILED`, activity family.

## Tasks

- [ ] Register mortgage read tools with JSON schemas; validate I/O at runtime boundary.
- [ ] Run payment + rate checks in parallel during demo step 5 (§12.1).
- [ ] Classify side-effecting tools (`commit_correction`) as blocked until Phase 9 policy.
- [ ] Session remains interactive while tools run (§14.3).
- [ ] Integration tests: timeout, partial failure, one tool slow.

## Test cases

| ID | Type | Description | Expected |
|----|------|-------------|----------|
| P06-TC-001 | E2E | Voice: compare last 3 months payments | Progress events; spoken summary |
| P06-TC-002 | E2E | Parallel rate + payment fetch | Both complete; UI activity updates |
| P06-TC-003 | Integration | Tool timeout | `TOOL_CALL_FAILED`; agent recovers |
| P06-TC-004 | Unit | Result arrives after new turn started | Stale result ignored |

## Acceptance criteria

- [ ] Parallel investigations without blocking conversation (§14.3).
- [ ] Tool governance metadata on registry entries (§11.1).
- [ ] Demo steps 5–6 supported (§12.1).
- [ ] Side-effecting commit not callable without HITL (Phase 9).

## Out of scope

MCP adapter, production policy marketplace, commit/verify tools execution.
